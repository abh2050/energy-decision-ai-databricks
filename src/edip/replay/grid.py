"""Sensitivity grid (FR22, FR23): every cell reruns the 2014 replay. No Databricks code.

One task covers one tariff and one battery power fraction and loops over duration,
efficiency, degradation cost, and demand charge rate. The no-battery bill does not
depend on the battery, so it is computed once per demand charge rate.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from edip.core.battery import BatterySpec
from edip.core.billing_demand import interval_demand, monthly_demand_all_hours
from edip.core.labels import REVISED
from edip.core.strategies import STRATEGIES, fixed_rule
from edip.core.tariff import Tariff, load_tariffs, scale_demand
from edip.replay.evaluate import check_targets, economics
from edip.replay.replay import RevisedSettings, run
from edip.replay.replay_job import TARIFF_FILES, window_key


def grid_tariff_ids(grid: dict[str, Any]) -> list[str]:
    return list(grid["tariffs"]["spread_family"].values()) + list(grid["tariffs"]["other_real"])


def spread_of(grid: dict[str, Any], tariff_id: str) -> float | None:
    for m, tid in grid["tariffs"]["spread_family"].items():
        if tid == tariff_id:
            return float(m)
    return None


def run_task(
    cdir: Path,
    obs: pd.DataFrame,
    hourly: pd.DataFrame,
    load15: pd.Series,
    tariff_id: str,
    power_fraction: float,
    *,
    limit_cells: int | None = None,
) -> pd.DataFrame:
    """All cells for one tariff and power fraction: one row per cell and strategy."""
    grid = yaml.safe_load((cdir / "sensitivity_grid.yaml").read_text())
    battery_cfg = yaml.safe_load((cdir / "battery.yaml").read_text())
    targets = yaml.safe_load((cdir / "acceptance_targets.yaml").read_text())
    fc_cfg = yaml.safe_load((cdir / "forecasting.yaml").read_text())
    settings = yaml.safe_load((cdir / "revised_strategy.yaml").read_text())
    if settings["status"] != "frozen":
        raise RuntimeError("revised strategy settings must be frozen")
    revised = RevisedSettings(**settings["settings"])
    operating = float(battery_cfg["operating_cost"]["annual_usd"])

    train = obs[obs.split == "train"].set_index("hour_start")["kw_mean"].sort_index()
    observed_peak = float(train.max())
    first = hourly.index[0].normalize().replace(day=1)
    seed15 = load15[(load15.index > first - pd.DateOffset(months=11)) & (load15.index <= first)]
    base: Tariff = next(
        t for f in TARIFF_FILES for t in load_tariffs(cdir / "tariffs" / f) if t.id == tariff_id
    )
    fixed_cfg = battery_cfg["fixed_schedule"]
    key = window_key(base, fixed_cfg)
    prot = fc_cfg["robust_protected_periods"]
    protected = prot[key if key in prot else "pge_b19_secondary"]

    cells = list(
        itertools.product(
            grid["demand_charge_rate_multiplier"],
            grid["duration_hours"],
            grid["round_trip_efficiency"],
            grid["degradation_cost_usd_per_kwh_discharged"],
        )
    )
    if limit_cells is not None:
        cells = cells[:limit_cells]
    rows: list[dict[str, Any]] = []
    no_battery_cache = {}
    for dm, duration, eff, deg in cells:
        tariff = scale_demand(base, dm)
        seed = (
            monthly_demand_all_hours(
                interval_demand(seed15, tariff.demand_charges[0].tariff_interval_minutes),
                tariff.clock,
            )
            if tariff.facility_capacity is not None
            else None
        )
        spec = BatterySpec.from_config(
            battery_cfg,
            observed_peak,
            power_fraction=power_fraction,
            duration_hours=duration,
            round_trip_efficiency=eff,
            degradation_usd_per_kwh=deg,
        )
        rule = fixed_rule(tariff, fixed_cfg["demand_window"][key], train, spec)
        results = {}
        for strategy in STRATEGIES:
            if strategy == "no_battery" and dm in no_battery_cache:
                results[strategy] = no_battery_cache[dm]
                continue
            res, _ = run(
                tariff,
                strategy,
                hourly,
                load15,
                spec,
                protected_periods=protected,
                fixed=rule,
                seed_monthly_demand_kw=seed,
                revised=revised,
            )
            results[strategy] = res
            if strategy == "no_battery":
                no_battery_cache[dm] = res
        econ = {e.strategy: e for e in economics(results, operating)}
        checks = {c.strategy: c for c in check_targets(list(econ.values()), targets, operating)}
        fixed_net = econ["fixed_schedule"].net_benefit_usd
        for strategy, res in results.items():
            e = econ[strategy]
            c = checks.get(strategy)
            rows.append(
                {
                    "tariff_id": tariff_id,
                    "spread_multiplier": spread_of(grid, tariff_id),
                    "power_fraction": power_fraction,
                    "power_kw": spec.power_kw,
                    "duration_hours": duration,
                    "round_trip_efficiency": eff,
                    "degradation_usd_per_kwh": deg,
                    "demand_charge_multiplier": dm,
                    "operating_cost_usd": operating,
                    "strategy": strategy,
                    "bill_usd": res.bill_usd,
                    "net_benefit_gross_usd": e.net_benefit_gross_usd,
                    "net_benefit_usd": e.net_benefit_usd,
                    "regret_vs_hindsight_usd": e.regret_vs_hindsight_usd,
                    "beats_no_battery": e.net_benefit_usd > 0,
                    "beats_fixed": e.net_benefit_usd > fixed_net,
                    "passes_target": c.passes if c else None,
                    "passes_target_single_count": c.passes_single_count if c else None,
                    "throughput_kwh": res.throughput_kwh,
                    "violations": res.violations,
                    "guard_clipped_kwh": res.guard_clipped_kwh,
                    "guard_shortfall_days": res.guard_shortfall_days,
                    "max_billing_demand_kw": res.max_billing_demand_kw,
                    "result_label": REVISED,
                }
            )
    return pd.DataFrame(rows)
