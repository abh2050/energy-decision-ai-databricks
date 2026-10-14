"""Settlement against actual load (FR18 to FR21).

A plan is executed hour by hour against actual load. Discharge is clipped to actual load
(FR19, no export), to the power limit, and to the energy above soc_min; charge is
clipped to the power limit and the room below soc_max. The settled state of charge
carries into the next day (FR20). Bills, peaks, throughput, and degradation come from
settled values only (FR21).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from edip.core.battery import BatterySpec
from edip.core.billing_demand import (
    facility_capacity_kw,
    interval_demand,
    local_month,
    monthly_billing_demand,
    monthly_demand_all_hours,
    net_interval_load,
)
from edip.core.charge_guard import ChargeGuard
from edip.core.tariff import Tariff

TOL = 1e-6


class SettledDay(BaseModel):
    charge_kw: list[float]
    discharge_kw: list[float]
    discharge_clipped_kw: list[float]  # planned minus settled discharge
    guard_clipped_kw: list[float]  # charge removed by the charge guard
    soc_kwh: list[float]
    grid_kw: list[float]
    soc_end_kwh: float


def settle_day(
    planned_charge_kw: np.ndarray,
    planned_discharge_kw: np.ndarray,
    actual_kw: np.ndarray,
    spec: BatterySpec,
    soc0_kwh: float,
    *,
    guard: ChargeGuard | None = None,
    hours_utc: pd.DatetimeIndex | None = None,
    load15_kw: np.ndarray | None = None,
) -> SettledDay:
    """Execute a plan hour by hour. With a `guard`, `hours_utc` and `load15_kw` (24 x 4
    actual 15 minute readings) are required; the guard only ever reduces charging."""
    if guard is not None and (hours_utc is None or load15_kw is None):
        raise ValueError("the charge guard needs hours_utc and load15_kw")
    soc = soc0_kwh
    c_out, d_out, clipped, guarded, s_out, g_out = [], [], [], [], [], []
    for t, (c_plan, d_plan, load) in enumerate(
        zip(planned_charge_kw, planned_discharge_kw, actual_kw, strict=True)
    ):
        load = max(float(load), 0.0)
        d = min(
            float(d_plan),
            spec.power_kw,
            load,
            max(soc - spec.soc_min_kwh, 0.0) * spec.eta_discharge,
        )
        d = max(d, 0.0)
        c = 0.0 if d > 0 else max(float(c_plan), 0.0)
        g_clip = 0.0
        if guard is not None and c > 0:
            limited = guard.limit(hours_utc[t], c, load15_kw[t])
            g_clip, c = c - limited, limited
        c = max(min(c, spec.power_kw, max(spec.soc_max_kwh - soc, 0.0) / spec.eta_charge), 0.0)
        soc = soc + spec.eta_charge * c - d / spec.eta_discharge
        if guard is not None:
            guard.update(hours_utc[t], np.maximum(np.asarray(load15_kw[t]) - d + c, 0.0))
        c_out.append(c)
        d_out.append(d)
        clipped.append(max(float(d_plan) - d, 0.0))
        guarded.append(g_clip)
        s_out.append(soc)
        g_out.append(load - d + c)
    return SettledDay(
        charge_kw=c_out,
        discharge_kw=d_out,
        discharge_clipped_kw=clipped,
        guard_clipped_kw=guarded,
        soc_kwh=s_out,
        grid_kw=g_out,
        soc_end_kwh=soc,
    )


def count_violations(
    charge_kw: np.ndarray,
    discharge_kw: np.ndarray,
    soc_kwh: np.ndarray,
    grid_kw: np.ndarray,
    spec: BatterySpec,
) -> int:
    """Settled hours that break any physical constraint (FR15)."""
    c, d, s, g = (np.asarray(a, dtype=float) for a in (charge_kw, discharge_kw, soc_kwh, grid_kw))
    bad = (
        (c < -TOL)
        | (d < -TOL)
        | (c > spec.power_kw + TOL)
        | (d > spec.power_kw + TOL)
        | ((c > TOL) & (d > TOL))
        | (s < spec.soc_min_kwh - TOL)
        | (s > spec.soc_max_kwh + TOL)
        | (g < -TOL)
    )
    return int(bad.sum())


class MonthBill(BaseModel):
    month: str
    energy_kwh: float
    energy_usd: float
    demand_usd: dict[str, float]
    billing_demand_kw: dict[str, float]
    facility_capacity_kw: float | None
    facility_capacity_usd: float
    total_usd: float


def bill_months(
    tariff: Tariff,
    hour_start_utc: pd.DatetimeIndex,
    grid_kw: np.ndarray,
    load15_kw: pd.Series,
    battery_kw_hourly: pd.Series,
    seed_monthly_demand_kw: pd.Series | None = None,
) -> list[MonthBill]:
    """Bills per local month: hourly energy, and demand from 15 minute load minus the hourly
    battery output held flat (config/settlement.yaml). The variable charge multiplier
    applies to every modelled charge; all amounts are before tax."""
    grid = pd.Series(np.asarray(grid_kw, dtype=float), index=hour_start_utc)
    energy_usd = grid * tariff.energy_rate(hour_start_utc)
    months = local_month(hour_start_utc, tariff.clock)
    net15, _ = net_interval_load(load15_kw, battery_kw_hourly)

    demand_by_charge = {}
    for charge in tariff.demand_charges:
        demand = interval_demand(net15, charge.tariff_interval_minutes)
        demand_by_charge[charge.name] = monthly_billing_demand(tariff, charge, demand)

    fc_kw = None
    if tariff.facility_capacity is not None:
        minutes = tariff.demand_charges[0].tariff_interval_minutes
        settled = monthly_demand_all_hours(interval_demand(net15, minutes), tariff.clock)
        history = (
            settled
            if seed_monthly_demand_kw is None
            else pd.concat(
                [seed_monthly_demand_kw[~seed_monthly_demand_kw.index.isin(settled.index)], settled]
            ).sort_index()
        )
        fc_kw = facility_capacity_kw(
            history,
            pd.PeriodIndex(sorted(set(months))),
            tariff.facility_capacity.lookback_months,
            tariff.facility_capacity.top_n,
        )

    bills = []
    for month in sorted(set(months)):
        in_month = months == month
        season = tariff.season_of(month.month)
        demand_usd, demand_kw = {}, {}
        for charge in tariff.demand_charges:
            kw = float(demand_by_charge[charge.name].get(month, 0.0))
            rate = charge.rates_usd_per_kw.get(season, 0.0)
            demand_kw[charge.name] = kw
            demand_usd[charge.name] = tariff.multiplier * rate * kw
        fc_usd, fc_month = 0.0, None
        if fc_kw is not None:
            fc_month = float(fc_kw[month])
            fc_usd = tariff.multiplier * tariff.facility_capacity.monthly_charge(fc_month)
        e_usd = float(energy_usd[in_month].sum())
        bills.append(
            MonthBill(
                month=str(month),
                energy_kwh=float(grid[in_month].sum()),
                energy_usd=e_usd,
                demand_usd=demand_usd,
                billing_demand_kw=demand_kw,
                facility_capacity_kw=fc_month,
                facility_capacity_usd=fc_usd,
                total_usd=e_usd + sum(demand_usd.values()) + fc_usd,
            )
        )
    return bills
