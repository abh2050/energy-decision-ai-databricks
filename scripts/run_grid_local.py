"""Run the Gate 4 grid slices locally in parallel processes (owner decision 2026-10-14).

Inputs are the Delta tables fetched by scripts/fetch_tables.py. Each slice (tariff x
battery power fraction) is written as parquet; upload the folder to
/Volumes/edip/ml/artifacts/gate4/cells and run the edip-gate4-aggregate job.
A summary run is logged to the MLflow experiment /Shared/edip/gate4_sensitivity.

Usage: uv run python scripts/run_grid_local.py TABLES_DIR OUT_DIR [--workers 8]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import yaml

from edip.replay.grid import grid_tariff_ids, run_task


def _slice(args: tuple[str, str, str, float]) -> tuple[str, int, float]:
    tables, out, tariff, pf = args
    t0 = time.time()
    T = Path(tables)
    obs = pd.read_parquet(T / "load_observations.parquet")
    p = pd.read_parquet(T / "forecast_predictions.parquet")
    pinned = yaml.safe_load(Path("config/model_versions.yaml").read_text())["load_forecaster"]
    p = p[(p.split == "test") & (p.model_version == pinned["version"])]
    hourly = p.set_index("target_hour")[["actual", "seasonal", "point", "p50", "p90"]].sort_index()
    load15 = pd.read_parquet(T / "load_intervals_15min.parquet").set_index("interval_end")["kw"]
    df = run_task(Path("config"), obs, hourly.astype(float), load15.sort_index(), tariff, pf)
    name = f"{tariff}_pf{pf:g}".replace(".", "_")
    df.to_parquet(Path(out) / f"{name}.parquet")
    return name, len(df), time.time() - t0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tables")
    parser.add_argument("out")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    grid = yaml.safe_load(Path("config/sensitivity_grid.yaml").read_text())
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [
        (args.tables, args.out, t, float(pf))
        for t in grid_tariff_ids(grid)
        for pf in grid["battery_power_fraction_of_observed_peak"]
    ]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        done = list(pool.map(_slice, jobs))
    for name, rows, secs in done:
        print(f"{name}: {rows} rows in {secs:.0f} s")
    elapsed = time.time() - t0

    import mlflow

    os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment("/Shared/edip/gate4_sensitivity")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    with mlflow.start_run(run_name="gate4-grid-local-slices"):
        mlflow.set_tags({"gate": "4", "execution": "local processes", "git_commit": commit})
        mlflow.log_metric("slices", len(done))
        mlflow.log_metric("rows", sum(r for _, r, _ in done))
        mlflow.log_metric("wall_seconds", elapsed)
    print(f"total {elapsed:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
