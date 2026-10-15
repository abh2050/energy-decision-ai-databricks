"""Gate 4 Databricks job (FR22, FR23).

Task mode (--tariff, --power-fraction): runs that slice of the grid and writes a parquet
file to the edip.ml.artifacts volume. Aggregate mode (--aggregate): reads every slice,
writes Delta edip.eval.sensitivity_grid, the flip boundaries JSON, and the PNG chart.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from edip.core.sensitivity import flip_boundaries
from edip.replay.charts import flip_chart
from edip.replay.grid import run_task

OUT = "/Volumes/edip/ml/artifacts/gate4"


def read_inputs(spark, catalog: str, cdir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:  # noqa: ANN001
    pinned = yaml.safe_load((cdir / "model_versions.yaml").read_text())["load_forecaster"]
    obs = spark.table(f"{catalog}.curated.load_observations").toPandas()
    preds = spark.table(f"{catalog}.curated.forecast_predictions").toPandas()
    preds = preds[(preds.model_version == pinned["version"]) & (preds.split == "test")]
    hourly = (
        preds.set_index("target_hour")[["actual", "seasonal", "point", "p50", "p90"]]
        .sort_index()
        .astype(float)
    )
    iv = spark.table(f"{catalog}.curated.load_intervals_15min").toPandas()
    load15 = iv.set_index("interval_end")["kw"].sort_index().astype(float)
    return obs, hourly, load15


def aggregate(grid: pd.DataFrame, cdir: Path, out: Path) -> dict:
    cfg = yaml.safe_load((cdir / "sensitivity_grid.yaml").read_text())
    battery = yaml.safe_load((cdir / "battery.yaml").read_text())["base_case"]
    boundaries = pd.DataFrame([b.model_dump() for b in flip_boundaries(grid)])
    spreads = sorted(float(m) for m in cfg["tariffs"]["spread_family"])
    flip_chart(
        boundaries,
        out / "flip_boundary.png",
        efficiency=battery["round_trip_efficiency"],
        degradation=battery["degradation_cost_usd_per_kwh_discharged"],
        demand_multiplier=1.0,
        spreads=spreads,
    )
    payload = {
        "label": str(grid["result_label"].iloc[0]),
        "cells": int(len(grid) / grid["strategy"].nunique()),
        "violations": int(grid["violations"].sum()),
        "flip_boundaries": boundaries.astype(object)
        .where(boundaries.notna(), None)
        .to_dict("records"),
    }
    (out / "flip_boundary.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--tariff")
    parser.add_argument("--power-fraction", type=float)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    cdir = Path(args.config_dir)
    out = Path(OUT)
    (out / "cells").mkdir(parents=True, exist_ok=True)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    if not args.aggregate:
        obs, hourly, load15 = read_inputs(spark, args.catalog, cdir)
        df = run_task(cdir, obs, hourly, load15, args.tariff, args.power_fraction)
        name = f"{args.tariff}_pf{args.power_fraction:g}".replace(".", "_")
        df.to_parquet(out / "cells" / f"{name}.parquet")
        print(json.dumps({"slice": name, "rows": len(df), "violations": int(df.violations.sum())}))
        return 0

    grid = pd.concat(
        [pd.read_parquet(p) for p in sorted((out / "cells").glob("*.parquet"))], ignore_index=True
    )
    spark.createDataFrame(grid).write.mode("overwrite").option(
        "overwriteSchema", "true"
    ).saveAsTable(f"{args.catalog}.eval.sensitivity_grid")
    payload = aggregate(grid, cdir, out)

    import mlflow

    mlflow.set_experiment("/Shared/edip/gate4_sensitivity")
    with mlflow.start_run(run_name="gate4-grid"):
        mlflow.set_tags(
            {"gate": "4", "label": payload["label"], "mlflow_version": mlflow.__version__}
        )
        mlflow.log_metric("cells", payload["cells"])
        mlflow.log_metric("violations", payload["violations"])
        mlflow.log_artifact(str(out / "flip_boundary.png"))
        mlflow.log_artifact(str(out / "flip_boundary.json"))
    print(json.dumps({"cells": payload["cells"], "violations": payload["violations"]}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
