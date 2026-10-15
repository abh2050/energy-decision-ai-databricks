"""Run the predefined stress tests on the 2014 replay and persist them (Gate 5).

Writes Delta edip.eval.stress_results and stress_results.json in the artifacts volume.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from edip.replay.grid_job import read_inputs
from edip.replay.stress import run_all


def _records(df) -> list[dict]:  # noqa: ANN001
    """Rows with NaN written as null (valid JSON)."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


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
    with tempfile.TemporaryDirectory() as tmp:
        frame, excess = run_all(cdir, obs, hourly, load15, Path(tmp))
    window = frame.attrs.get("heat_week_window")
    frame["label"] = "revised strategy, post-hoc"
    excess["label"] = "revised strategy, post-hoc"
    excess["guard_month_start_determinants"] = excess["guard_month_start_determinants"].apply(
        json.dumps
    )
    for df, name in ((frame, "stress_results"), (excess, "stress_excess_months")):
        spark.createDataFrame(df).write.mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(f"{args.catalog}.eval.{name}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "heat_week_window": window,
        "rows": _records(frame),
        "excess_months": _records(excess),
    }
    (out / "stress_results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(json.dumps({"rows": len(frame), "passed": int(frame.passed.sum())}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
