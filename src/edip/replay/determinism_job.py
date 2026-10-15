"""Determinism check (Gate 4 follow-up): rerun the base cell and record annual bills.

Base cell: revised strategy settings, base battery (50 percent of the training peak, 2
hours, 90 percent efficiency, 0.03 USD per kWh), demand rates x1.0, on B-19 and PGE.
Run locally (from fetched tables) and on Databricks; the two outputs must agree within
10 USD per bill. Writes JSON only; no table is changed.
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import pandas as pd
import scipy
import yaml

from edip.replay.replay import RevisedSettings
from edip.replay.replay_job import compute

TARIFFS = ["pge_b19_secondary", "pgn_sched85_secondary"]


def base_cell(cdir: Path, obs: pd.DataFrame, hourly: pd.DataFrame, load15: pd.Series) -> dict:
    settings = yaml.safe_load((cdir / "revised_strategy.yaml").read_text())["settings"]
    out = compute(cdir, obs, hourly, load15, TARIFFS, RevisedSettings(**settings))
    return {
        "platform": f"{platform.system()} {platform.machine()} python {platform.python_version()}",
        "scipy": scipy.__version__,
        "bills": {
            f"{r['tariff_id']}|{r['strategy']}": r["bill_usd"]
            for r in out.annual.to_dict("records")
        },
        "net_benefit": {
            f"{r['tariff_id']}|{r['strategy']}": r["net_benefit_usd"]
            for r in out.annual.to_dict("records")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--catalog", default="edip")
    parser.add_argument(
        "--out", default="/Volumes/edip/ml/artifacts/gate4/determinism_databricks.json"
    )
    args = parser.parse_args()
    cdir = Path(args.config_dir)
    from pyspark.sql import SparkSession

    from edip.replay.grid_job import read_inputs

    spark = SparkSession.builder.getOrCreate()
    obs, hourly, load15 = read_inputs(spark, args.catalog, cdir)
    result = base_cell(cdir, obs, hourly, load15)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"platform": result["platform"], "scipy": result["scipy"]}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
