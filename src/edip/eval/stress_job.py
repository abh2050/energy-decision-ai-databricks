"""Run the predefined stress tests on the 2014 replay and persist them (Gate 5).

Writes Delta edip.eval.stress_results, stress_excess_months, stress_peak_moments, and
decision_verdicts (base case: frozen rule and amendment A1), plus stress_results.json in
the artifacts volume.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd
import yaml

from edip.core.labels import REVISED
from edip.core.metrics import coverage
from edip.replay.grid_job import read_inputs
from edip.replay.stress import run_all
from edip.workflow.verdicts import base_inputs, verdict_record

LABEL = REVISED


def _records(df: pd.DataFrame) -> list[dict]:
    """Rows with NaN written as null (valid JSON)."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def build(
    cdir: Path, obs: pd.DataFrame, hourly: pd.DataFrame, load15: pd.Series, coverage_pct: float
) -> dict[str, pd.DataFrame | list | None]:
    with tempfile.TemporaryDirectory() as tmp:
        run = run_all(cdir, obs, hourly, load15, Path(tmp))
    tariffs = yaml.safe_load((cdir / "stress_tests.yaml").read_text())["tariffs"]
    frame, excess, moments = run.results, run.excess, run.moments
    window = frame.attrs.get("heat_week_window")
    for df in (frame, excess, moments):
        df["label"] = LABEL
    excess["guard_month_start_determinants"] = excess["guard_month_start_determinants"].apply(
        json.dumps
    )
    for col in ("interval_start_utc", "interval_start_local"):
        moments[col] = moments[col].astype(str)
    inputs = base_inputs(run.base.annual, run.base.checks, frame, coverage_pct, tariffs)
    verdicts = pd.DataFrame([verdict_record(inputs)])
    return {
        "stress_results": frame,
        "stress_excess_months": excess,
        "stress_peak_moments": moments,
        "decision_verdicts": verdicts,
        "window": window,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--out", default="/Volumes/edip/ml/artifacts/gate5")
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    cdir = Path(args.config_dir)
    obs, hourly, load15 = read_inputs(spark, args.catalog, cdir)
    pinned = yaml.safe_load((cdir / "model_versions.yaml").read_text())["load_forecaster"]
    p = spark.table(f"{args.catalog}.curated.forecast_predictions").toPandas()
    p = p[(p.model_version == pinned["version"]) & (p.split == "test")]
    cov = coverage(p.actual.astype(float), p.p10.astype(float), p.p90.astype(float))
    built = build(cdir, obs, hourly, load15, cov)
    for name, df in built.items():
        if name == "window":
            continue
        spark.createDataFrame(df).write.mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(f"{args.catalog}.eval.{name}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "heat_week_window": built["window"],
        "coverage_pct": cov,
        "verdicts": _records(built["decision_verdicts"]),
        "rows": _records(built["stress_results"]),
        "excess_months": _records(built["stress_excess_months"]),
        "peak_moments": _records(built["stress_peak_moments"]),
    }
    (out / "stress_results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {"rows": len(built["stress_results"]), "verdicts": payload["verdicts"]}, default=str
        )
    )
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
