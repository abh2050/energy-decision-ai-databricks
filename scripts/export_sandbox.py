"""Export the public sandbox's frozen data (Gate 7, PRD 4.2).

Writes frontend/public/data/sandbox/:
- slice.json: 90 days of the selected client's real hourly load (2014-06-01 to 2014-08-29
  UTC, test partition) plus 8 days of history for the forecast features; the pinned
  model's Python forecasts for the same hours (reference for the browser's ONNX run);
  per-hour energy price, demand-charge windows, rates, and local months for both real
  tariffs; battery base case and observed peak.
- parity_cases.json: 20 saved optimizer cases (inputs and the Python HiGHS objective)
  for the browser parity test (within 0.5 percent of cost).

Inputs are the Delta tables fetched by scripts/fetch_tables.py.
Usage: uv run python scripts/export_sandbox.py TABLES_DIR
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from edip.core.battery import BatterySpec
from edip.core.billing_demand import local_month
from edip.core.labels import REVISED
from edip.core.optimizer import solve_day
from edip.core.strategies import planning_load
from edip.core.tariff import load_tariffs
from edip.replay.replay import Calendar, demand_terms

OUT = Path("frontend/public/data/sandbox")
START = pd.Timestamp("2014-06-01")
DAYS = 90
HISTORY_H = 192
TARIFFS = {"anchored_tou.yaml": "pge_b19_secondary", "low_spread_tou.yaml": "pgn_sched85_secondary"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tables", type=Path)
    args = parser.parse_args()
    cdir = Path("config")
    obs = pd.read_parquet(args.tables / "load_observations.parquet")
    hourly = obs.set_index("hour_start")["kw_mean"].sort_index().astype(float)
    pinned = yaml.safe_load((cdir / "model_versions.yaml").read_text())["load_forecaster"]
    preds = pd.read_parquet(args.tables / "forecast_predictions.parquet")
    preds = preds[(preds.split == "test") & (preds.model_version == pinned["version"])]
    fc = preds.set_index("target_hour")[["actual", "point", "p10", "p50", "p90"]].sort_index()

    end = START + pd.Timedelta(days=DAYS)
    hist_start = START - pd.Timedelta(hours=HISTORY_H)
    load = hourly[(hourly.index >= hist_start) & (hourly.index < end)]
    expected = pd.date_range(hist_start, end - pd.Timedelta(hours=1), freq="h")
    if len(load) != len(expected):
        raise ValueError("slice has gaps")
    slice_idx = pd.date_range(START, end - pd.Timedelta(hours=1), freq="h")
    ref = fc.reindex(slice_idx).astype(float)

    battery = yaml.safe_load((cdir / "battery.yaml").read_text())
    train = obs[obs.split == "train"]["kw_mean"]
    observed_peak = float(train.max())
    prot = yaml.safe_load((cdir / "forecasting.yaml").read_text())["robust_protected_periods"]

    tariffs = {}
    tariff_objs = {}
    for f, tid in TARIFFS.items():
        t = next(x for x in load_tariffs(cdir / "tariffs" / f) if x.id == tid)
        tariff_objs[tid] = t
        cal = Calendar(t, slice_idx)
        months = [str(m) for m in local_month(slice_idx, t.clock)]
        charges = []
        for c in t.demand_charges:
            rate = [
                t.multiplier * c.rates_usd_per_kw.get(t.season_of(pd.Period(m).month), 0.0)
                for m in months
            ]
            charges.append(
                {
                    "name": c.name,
                    "in_window": cal.windows[c.name].astype(int).tolist(),
                    "rate": rate,
                }
            )
        periods = cal.cls["period"].tolist()
        tariffs[tid] = {
            "name": t.name if hasattr(t, "name") else tid,
            "price_usd_per_kwh": cal.price.tolist(),
            "period": periods,
            "protected": [int(p in prot[tid]) for p in periods],
            "local_month": months,
            "demand_charges": charges,
        }
    payload = {
        "label": "real load (UCI ElectricityLoadDiagrams20112014, client MT_189), frozen slice",
        "result_set": REVISED,
        "clock": "Europe/Lisbon",
        "window_utc": [str(START), str(end)],
        "hours_utc": [str(h) for h in expected],
        "load_kw": load.round(4).tolist(),
        "slice_start_index": HISTORY_H,
        "reference_forecasts": {
            c: ref[c].round(4).tolist() for c in ("actual", "point", "p10", "p50", "p90")
        },
        "model_version": f"{pinned['model_name']} v{pinned['version']}",
        "observed_peak_kw": observed_peak,
        "battery_base_case": battery["base_case"],
        "robust_charge_band_k": yaml.safe_load((cdir / "revised_strategy.yaml").read_text())[
            "settings"
        ]["robust_charge_band_k"],
        "tariffs": tariffs,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "slice.json").write_text(json.dumps(payload))

    # 20 parity cases: both tariffs, several sizes and strategies, spread over the slice.
    rng = np.random.default_rng(20261015)
    days = sorted(rng.choice(DAYS, size=20, replace=False).tolist())
    sizes = [(0.25, 2), (0.5, 2), (0.5, 4), (1.0, 4)]
    strategies = ["ml_forecast", "robust_quantile", "hindsight"]
    cases = []
    for i, d in enumerate(days):
        tid = list(TARIFFS.values())[i % 2]
        t = tariff_objs[tid]
        pf, dur = sizes[i % len(sizes)]
        strategy = strategies[i % len(strategies)]
        spec = BatterySpec.from_config(
            battery, observed_peak, power_fraction=pf, duration_hours=dur
        )
        hours = slice_idx[d * 24 : (d + 1) * 24]
        cal = Calendar(t, slice_idx)
        day = ref.loc[hours].assign(seasonal=np.nan)
        fc_load = planning_load(
            strategy, day, t, prot[tid], periods=cal.cls["period"].to_numpy()[cal.span(hours)]
        )
        demand_load = None
        if strategy == "robust_quantile":
            k = payload["robust_charge_band_k"]
            band = day["p50"] + k * (day["p90"] - day["p50"])
            demand_load = np.maximum(fc_load, band.to_numpy())
        # Running peaks: no-battery peak so far this month in the slice (0 on the 1st).
        month_start = hours[0].normalize().replace(day=1)
        before = hourly[(hourly.index >= month_start) & (hourly.index < hours[0])]
        running = {}
        for c in t.demand_charges:
            win = t.in_demand_window(c, before.index).to_numpy() if len(before) else []
            for m in sorted(set(str(x) for x in local_month(hours, t.clock))):
                vals = before[win] if len(before) else before
                running[(c.name, m)] = float(vals.max()) if len(vals) else 0.0
        terms = demand_terms(t, hours, running, cal)
        soc0 = spec.energy_kwh * (0.3 + 0.4 * ((i * 7) % 10) / 10)
        terminal = spec.terminal_reserve_kwh
        plan = solve_day(
            fc_load,
            cal.price[cal.span(hours)],
            terms,
            spec,
            soc0,
            terminal,
            demand_load_kw=demand_load,
        )
        cases.append(
            {
                "case": i + 1,
                "tariff_id": tid,
                "strategy": strategy,
                "day_utc": str(hours[0]),
                "load_kw": [float(x) for x in fc_load],
                "demand_load_kw": None if demand_load is None else [float(x) for x in demand_load],
                "price_usd_per_kwh": cal.price[cal.span(hours)].tolist(),
                "demand_terms": [term.model_dump() for term in terms],
                "spec": spec.model_dump(),
                "soc0_kwh": soc0,
                "terminal_min_kwh": terminal,
                "python_objective_usd": plan.objective_usd,
                "python_status": plan.status,
            }
        )
    (OUT / "parity_cases.json").write_text(json.dumps({"cases": cases}, indent=1))
    print(f"slice {len(load)} hours; {len(cases)} parity cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
