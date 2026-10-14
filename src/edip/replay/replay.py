"""Rolling replay of one strategy on one tariff across the test period (FR18 to FR21).

Day by day: plan on the strategy's load (24 UTC hours), settle against actual load,
carry the settled state of charge, and update each demand charge's running monthly peak
from settled hourly grid draw. Bills come from settled values only. No Databricks code.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from edip.core.battery import BatterySpec
from edip.core.billing_demand import local_month
from edip.core.optimizer import DemandTerm, solve_day
from edip.core.settlement import MonthBill, bill_months, count_violations, settle_day
from edip.core.strategies import OPTIMIZED, FixedRule, fixed_plan, planning_load
from edip.core.tariff import Tariff


class StrategyResult(BaseModel):
    tariff_id: str
    strategy: str
    days: int
    bill_usd: float
    energy_usd: float
    demand_usd: float
    facility_capacity_usd: float
    degradation_usd: float
    throughput_kwh: float
    discharge_clipped_kwh: float
    peak_grid_kw: float
    max_billing_demand_kw: float
    violations: int
    months: list[MonthBill]
    solver_failures: int


def demand_terms(
    tariff: Tariff,
    hours: pd.DatetimeIndex,
    running: dict[tuple[str, str], float],
) -> list[DemandTerm]:
    months = local_month(hours, tariff.clock)
    terms = []
    for charge in tariff.demand_charges:
        window = tariff.in_demand_window(charge, hours).to_numpy()
        for month in sorted(set(months)):
            mask = window & (months == month)
            if not mask.any():
                continue
            rate = charge.rates_usd_per_kw.get(tariff.season_of(month.month), 0.0)
            terms.append(
                DemandTerm(
                    name=f"{charge.name}|{month}",
                    mask=mask.tolist(),
                    rate_usd_per_kw=tariff.multiplier * rate,
                    running_peak_kw=running.get((charge.name, str(month)), 0.0),
                )
            )
    return terms


def update_running(
    tariff: Tariff,
    hours: pd.DatetimeIndex,
    grid_kw: np.ndarray,
    running: dict[tuple[str, str], float],
) -> None:
    months = local_month(hours, tariff.clock)
    for charge in tariff.demand_charges:
        window = tariff.in_demand_window(charge, hours).to_numpy()
        for month in sorted(set(months)):
            mask = window & (months == month)
            if mask.any():
                key = (charge.name, str(month))
                running[key] = max(running.get(key, 0.0), float(np.max(grid_kw[mask])))


def run(
    tariff: Tariff,
    strategy: str,
    hourly: pd.DataFrame,
    load15: pd.Series,
    spec: BatterySpec,
    *,
    protected_periods: list[str],
    fixed: FixedRule | None,
    seed_monthly_demand_kw: pd.Series | None,
) -> tuple[StrategyResult, pd.DataFrame]:
    """`hourly`: test hours (UTC index) with actual, seasonal, point, p50, p90."""
    days = sorted(set(hourly.index.normalize()))
    soc = spec.initial_soc_kwh
    running: dict[tuple[str, str], float] = {}
    rows: list[dict[str, Any]] = []
    failures = 0
    for day in days:
        block = hourly.loc[day : day + pd.Timedelta(hours=23)]
        hours = block.index
        actual = block["actual"].to_numpy()
        if strategy == "no_battery":
            c_plan = d_plan = np.zeros(24)
            fc = np.full(24, np.nan)
        elif strategy == "fixed_schedule":
            c_plan, d_plan = fixed_plan(hours, tariff, fixed, spec, soc)
            fc = np.full(24, np.nan)
        elif strategy in OPTIMIZED:
            fc = planning_load(strategy, block, tariff, protected_periods)
            try:
                plan = solve_day(
                    fc,
                    tariff.energy_rate(hours).to_numpy(),
                    demand_terms(tariff, hours, running),
                    spec,
                    soc,
                    spec.terminal_reserve_kwh,
                )
                c_plan, d_plan = np.array(plan.charge_kw), np.array(plan.discharge_kw)
            except RuntimeError:
                failures += 1
                c_plan = d_plan = np.zeros(24)
        else:
            raise ValueError(strategy)
        settled = settle_day(c_plan, d_plan, actual, spec, soc)
        soc = settled.soc_end_kwh
        update_running(tariff, hours, np.array(settled.grid_kw), running)
        for t, h in enumerate(hours):
            rows.append(
                {
                    "hour_start": h,
                    "forecast_kw": float(fc[t]),
                    "actual_kw": float(actual[t]),
                    "planned_charge_kw": float(c_plan[t]),
                    "planned_discharge_kw": float(d_plan[t]),
                    "charge_kw": settled.charge_kw[t],
                    "discharge_kw": settled.discharge_kw[t],
                    "discharge_clipped_kw": settled.discharge_clipped_kw[t],
                    "soc_kwh": settled.soc_kwh[t],
                    "grid_kw": settled.grid_kw[t],
                }
            )
    frame = pd.DataFrame(rows).set_index("hour_start")
    battery = frame["discharge_kw"] - frame["charge_kw"]
    l15 = load15[
        (load15.index > frame.index[0]) & (load15.index <= frame.index[-1] + pd.Timedelta(hours=1))
    ]
    months = bill_months(
        tariff, frame.index, frame["grid_kw"].to_numpy(), l15, battery, seed_monthly_demand_kw
    )
    frame["energy_usd"] = frame["grid_kw"] * tariff.energy_rate(frame.index)
    throughput = float(frame["discharge_kw"].sum())
    billing_peaks = [max(m.billing_demand_kw.values(), default=0.0) for m in months]
    result = StrategyResult(
        tariff_id=tariff.id,
        strategy=strategy,
        days=len(days),
        bill_usd=sum(m.total_usd for m in months),
        energy_usd=sum(m.energy_usd for m in months),
        demand_usd=sum(sum(m.demand_usd.values()) for m in months),
        facility_capacity_usd=sum(m.facility_capacity_usd for m in months),
        degradation_usd=spec.degradation_usd_per_kwh * throughput,
        throughput_kwh=throughput,
        discharge_clipped_kwh=float(frame["discharge_clipped_kw"].sum()),
        peak_grid_kw=float(frame["grid_kw"].max()),
        max_billing_demand_kw=float(max(billing_peaks, default=0.0)),
        violations=count_violations(
            frame["charge_kw"], frame["discharge_kw"], frame["soc_kwh"], frame["grid_kw"], spec
        ),
        months=months,
        solver_failures=failures,
    )
    return result, frame
