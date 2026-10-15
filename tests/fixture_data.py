"""A small SYNTHETIC app snapshot for tests and offline end-to-end runs.

Same files and columns as the published snapshot (src/edip/eval/publish_job.py); every
number is made up and the manifest is labelled synthetic. Never shown as a result.

Usage: uv run python tests/fixture_data.py OUT_DIR
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from edip.agents.fallback import build_packet
from edip.workflow.decision import DecisionInputs, StrategyEvidence
from edip.workflow.verdicts import verdict_record

ROOT = Path(__file__).parents[1]
TABLE = "edip.eval.cell_evidence"
TARIFFS = ("pge_b19_secondary", "pgn_sched85_secondary")
STRATS = (
    "no_battery",
    "fixed_schedule",
    "seasonal_forecast",
    "ml_forecast",
    "robust_quantile",
    "hindsight",
)
TESTS = ("forecast_error_injection", "heat_week_replay", "reserve_floor_raise")


def _inputs(pf: float, dur: int) -> DecisionInputs:
    good = pf == 1.0 and dur == 4  # the only cell that qualifies under A1
    return DecisionInputs(
        violations=0,
        coverage_pct=80.5,
        stress_passed={t: good or t == "reserve_floor_raise" for t in TESTS},
        strategies=[
            StrategyEvidence(
                tariff_id=t,
                strategy=s,
                passes_target=t == TARIFFS[0],
                net_vs_no_battery_usd=(12000.0 if good else -3000.0) if t == TARIFFS[0] else -900.0,
                net_vs_fixed_usd=9000.0 if t == TARIFFS[0] else -100.0,
            )
            for t in TARIFFS
            for s in ("ml_forecast", "robust_quantile")
        ],
    )


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "config").mkdir(exist_ok=True)
    annual, stress, verdicts, evidence, sched, excess = [], [], [], [], [], []
    hours = pd.date_range("2014-12-30 00:00", periods=48, freq="h")
    for pf in (0.25, 0.5, 1.0):
        for dur in (2, 4):
            cell = f"{pf:g}/{dur}"
            x = _inputs(pf, dur)
            base = {"cell": cell, "power_fraction": pf, "duration_hours": dur}
            verdicts.append(base | verdict_record(x) | {"case": "cell"})
            for k, v in build_packet(TABLE, x).values.items():
                _, row_key, col = k.split("|")
                evidence.append(base | {"row_key": row_key, "column": col, "value": float(v)})
            for i, t in enumerate(TARIFFS):
                for j, s in enumerate(STRATS):
                    annual.append(
                        base
                        | {
                            "tariff_id": t,
                            "strategy": s,
                            "bill_usd": 900000.0 - 1000 * j - 100 * i,
                            "net_benefit_usd": 0.0 if s == "no_battery" else -1000.0 + 500 * j,
                            "max_billing_demand_kw": 700.0 - j,
                            "peak_grid_kw": 710.0 - j,
                            "throughput_kwh": 0.0 if s == "no_battery" else 50000.0 * pf,
                            "degradation_usd": 0.0 if s == "no_battery" else 1500.0 * pf,
                            "regret_vs_hindsight_usd": 5000.0 - 800 * j,
                            "violations": 0,
                        }
                    )
                    for n, h in enumerate(hours):
                        sched.append(
                            base
                            | {
                                "tariff_id": t,
                                "strategy": s,
                                "hour_start": str(h),
                                "forecast_kw": 420.0,
                                "planned_charge_kw": 50.0 if n % 24 < 4 else 0.0,
                                "planned_discharge_kw": 60.0 if 17 <= n % 24 < 19 else 0.0,
                                "actual_kw": 400.0 + 50 * np.sin(n / 3),
                                "charge_kw": 50.0 if n % 24 < 4 else 0.0,
                                "discharge_kw": 60.0 if 17 <= n % 24 < 19 else 0.0,
                                "discharge_clipped_kw": 0.0,
                                "guard_clipped_kw": 0.0,
                                "soc_kwh": 200.0 + 10 * (n % 24),
                                "grid_kw": 400.0,
                                "energy_usd": 40.0,
                            }
                        )
                for test in TESTS:
                    stress.append(
                        base
                        | {
                            "test": test,
                            "tariff_id": t,
                            "strategy": "robust_quantile",
                            "net_benefit_unstressed_usd": -3000.0,
                            "net_benefit_stressed_usd": -3500.0,
                            "absolute_change_usd": -500.0,
                            "retained_pct": None,
                            "retained_reason": "base_negative",
                            "retained_display": "not applicable, base case already loses money",
                            "judged_on": "monthly bill limit and absolute dollar change",
                            "worst_month_vs_no_battery_pct": 2.0,
                            "violations": 0,
                            "passed": x.stress_passed[test],
                        }
                    )
            excess.append(
                base
                | {
                    "case": "base",
                    "tariff_id": TARIFFS[0],
                    "strategy": "robust_quantile",
                    "month": "2014-12",
                    "bill_above_no_battery_pct": 3.6,
                    "excess_usd": 2000.0,
                    "energy_usd": -200.0,
                    "maximum_demand_usd": 2200.0,
                }
            )
    forecasts = pd.DataFrame(
        {
            "target_hour": hours,
            "actual": 400.0 + 50 * np.sin(np.arange(48) / 3),
            "point": 420.0,
            "seasonal": 410.0,
            "p10": 380.0,
            "p50": 420.0,
            "p90": 470.0,
        }
    )
    grid = pd.DataFrame(
        [
            {
                "tariff_id": t,
                "spread_multiplier": m,
                "power_fraction": pf,
                "duration_hours": d,
                "round_trip_efficiency": 0.9,
                "degradation_usd_per_kwh": 0.03,
                "demand_charge_multiplier": 1.0,
                "strategy": s,
                "net_benefit_usd": -1000.0 + 2000 * m,
                "beats_no_battery": m > 1,
                "beats_fixed": True,
            }
            for t, m in (("pge_b19_secondary", 1.0), ("pge_b19_secondary", 2.0))
            for pf in (0.25, 0.5, 1.0)
            for d in (2, 4)
            for s in ("ml_forecast", "robust_quantile")
        ]
    )
    frames = {
        "cell_annual": pd.DataFrame(annual),
        "cell_stress_results": pd.DataFrame(stress),
        "cell_verdicts": pd.DataFrame(verdicts),
        "cell_evidence": pd.DataFrame(evidence),
        "cell_schedules": pd.DataFrame(sched),
        "cell_excess_months": pd.DataFrame(excess),
        "forecasts": forecasts,
        "sensitivity_grid": grid,
    }
    tables = {}
    for name, df in frames.items():
        path = out / f"{name}.parquet"
        df.to_parquet(path, index=False)
        tables[name] = {
            "source": f"synthetic fixture ({name})",
            "delta_version": 0,
            "rows": len(df),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    for c in (
        "agent_allowlist.yaml",
        "acceptance_targets.yaml",
        "battery.yaml",
        "revised_strategy.yaml",
        "model_versions.yaml",
        "stress_tests.yaml",
    ):
        shutil.copyfile(ROOT / "config" / c, out / "config" / c)
    (out / "flip_boundary.json").write_text(json.dumps({"label": "synthetic", "boundaries": []}))
    (out / "capital.json").write_text(json.dumps({"label": "synthetic", "rows": []}))
    manifest = {
        "published_at": "2026-10-15T00:00:00+00:00",
        "result_label": "synthetic test fixture",
        "dataset_sha256": "synthetic",
        "model_version": "synthetic",
        "evaluation_period": "synthetic 2014-12-30 to 2014-12-31",
        "client": "synthetic",
        "solver": {"library": "none"},
        "config_hashes": {"tariffs": "synthetic"},
        "tables": tables,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
