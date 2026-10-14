"""Tune the revised strategy settings on validation only (July to December 2013).

Local run allowed by owner decision (2026-10-14); every trial is logged to the Databricks
MLflow experiment /Shared/edip/gate3_revised_tuning. Test data (2014) is never read.

Step 1: guard margin in {0, 0.02, 0.05} with the robust charge band k = 1 (plain P90).
Step 2: robust charge band k in {0, 0.5, 1.0, 1.5} with the chosen margin.
Objective for both: net benefit of ml_forecast plus robust_quantile, summed over
pge_b19_secondary and pgn_sched85_secondary. Ties: smaller margin, then k closest to 1.

Usage: uv run python scripts/tune_revised.py TABLES_DIR [--profile edip]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from edip.replay.replay import RevisedSettings
from edip.replay.replay_job import compute

TARIFFS = ["pge_b19_secondary", "pgn_sched85_secondary"]
OBJECTIVE_STRATEGIES = ["ml_forecast", "robust_quantile"]
MARGINS = [0.0, 0.02, 0.05]
BANDS = [0.0, 0.5, 1.0, 1.5]


def objective(annual: pd.DataFrame) -> float:
    rows = annual[annual.strategy.isin(OBJECTIVE_STRATEGIES)]
    return float(rows.net_benefit_usd.sum())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tables")
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    tables = Path(args.tables)
    obs = pd.read_parquet(tables / "load_observations.parquet")
    preds = pd.read_parquet(tables / "forecast_predictions.parquet")
    preds = preds[(preds.split == "validation") & (preds.model_version == "2")]
    assert preds.target_hour.max() < pd.Timestamp("2014-01-01"), "test data must not be used"
    hourly = (
        preds.set_index("target_hour")[["actual", "seasonal", "point", "p50", "p90"]]
        .sort_index()
        .astype(float)
    )
    iv = pd.read_parquet(tables / "load_intervals_15min.parquet")
    load15 = iv.set_index("interval_end")["kw"].sort_index().astype(float)
    load15 = load15[load15.index <= pd.Timestamp("2014-01-01")]

    import mlflow

    os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment("/Shared/edip/gate3_revised_tuning")

    def trial(margin: float, k: float, step: int) -> dict:
        settings = RevisedSettings(guard_margin_fraction=margin, robust_charge_band_k=k)
        out = compute(Path("config"), obs, hourly, load15, TARIFFS, settings)
        score = objective(out.annual)
        record = {
            "step": step,
            "guard_margin_fraction": margin,
            "robust_charge_band_k": k,
            "objective_usd": score,
            "annual": out.annual[
                [
                    "tariff_id",
                    "strategy",
                    "net_benefit_usd",
                    "guard_clipped_kwh",
                    "guard_shortfall_days",
                    "violations",
                ]
            ].to_dict("records"),
        }
        with mlflow.start_run(run_name=f"step{step}-margin{margin}-k{k}"):
            mlflow.set_tags({"period": "2013-07-01 to 2013-12-31 (validation)", "step": str(step)})
            mlflow.log_params({"guard_margin_fraction": margin, "robust_charge_band_k": k})
            mlflow.log_metric("objective_usd", score)
            for r in record["annual"]:
                mlflow.log_metric(
                    f"{r['tariff_id']}.{r['strategy']}.net_benefit_usd", r["net_benefit_usd"]
                )
            mlflow.log_dict(record, "trial.json")
        print(json.dumps({k_: v for k_, v in record.items() if k_ != "annual"}))
        return record

    step1 = [trial(m, 1.0, 1) for m in MARGINS]
    best_margin = max(step1, key=lambda r: (r["objective_usd"], -r["guard_margin_fraction"]))
    margin = best_margin["guard_margin_fraction"]
    step2 = [trial(margin, k, 2) for k in BANDS]
    best = max(step2, key=lambda r: (r["objective_usd"], -abs(r["robust_charge_band_k"] - 1)))
    result = {
        "chosen": {
            "guard_margin_fraction": margin,
            "robust_charge_band_k": best["robust_charge_band_k"],
        },
        "trials": step1 + step2,
    }
    Path(tables / "tuning_result.json").write_text(json.dumps(result, indent=2, default=str))
    print("CHOSEN", json.dumps(result["chosen"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
