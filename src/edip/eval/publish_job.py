"""Publish the live app's read-only snapshot from Delta (Gate 6).

Writes /Volumes/edip/ml/artifacts/app/<table>.parquet for every table the app shows, the
configuration files it labels as assumptions, and manifest.json with each table's source,
Delta version, row count, and SHA256, plus run provenance (dataset hash, model version,
evaluation period, solver settings, config hashes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

from edip.core.labels import REVISED
from edip.replay.replay_job import file_hash

CELL_TABLES = (
    "cell_annual",
    "cell_stress_results",
    "cell_verdicts",
    "cell_evidence",
    "cell_schedules",
    "cell_excess_months",
)
CONFIGS = (
    "agent_allowlist.yaml",
    "acceptance_targets.yaml",
    "battery.yaml",
    "revised_strategy.yaml",
    "model_versions.yaml",
    "stress_tests.yaml",
)
SOLVER = {
    "library": "scipy.optimize.milp (HiGHS)",
    "threads": 1,
    "random_seed": 0,
    "mip_rel_gap": 1e-6,
    "throughput_tie_break_usd_per_kwh": 1e-7,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--root", required=True, help="bundle workspace file path")
    parser.add_argument("--out", default="/Volumes/edip/ml/artifacts/app")
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    root, out = Path(args.root), Path(args.out)
    (out / "config").mkdir(parents=True, exist_ok=True)
    pinned = yaml.safe_load((root / "config" / "model_versions.yaml").read_text())[
        "load_forecaster"
    ]
    sources = {t: f"{args.catalog}.eval.{t}" for t in CELL_TABLES}
    sources["sensitivity_grid"] = f"{args.catalog}.eval.sensitivity_grid"
    sources["forecasts"] = f"{args.catalog}.curated.forecast_predictions"
    tables = {}
    for name, source in sources.items():
        version = spark.sql(f"DESCRIBE HISTORY {source} LIMIT 1").collect()[0]["version"]
        df = spark.table(source).toPandas()
        df.attrs = {}  # Spark Connect plan metrics are not parquet metadata
        if name == "forecasts":
            df = df[(df.split == "test") & (df.model_version == pinned["version"])]
            df = df[["target_hour", "actual", "point", "seasonal", "p10", "p50", "p90"]].copy()
            df.attrs = {}
        path = out / f"{name}.parquet"
        df.to_parquet(path, index=False)
        tables[name] = {
            "source": source,
            "delta_version": int(version),
            "rows": len(df),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    for c in CONFIGS:
        shutil.copyfile(root / "config" / c, out / "config" / c)
    shutil.copyfile(
        "/Volumes/edip/ml/artifacts/gate4/flip_boundary.json", out / "flip_boundary.json"
    )
    shutil.copyfile(root / "docs" / "business_case_capital.json", out / "capital.json")
    obs = spark.table(f"{args.catalog}.curated.load_observations").select("dataset_sha256")
    manifest = {
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "result_label": REVISED,
        "dataset_sha256": obs.first()["dataset_sha256"],
        "model_version": f"{pinned['model_name']} v{pinned['version']}",
        "evaluation_period": "2014-01-01 to 2014-12-31 UTC (test partition)",
        "client": "MT_189",
        "solver": SOLVER,
        "config_hashes": {
            "tariffs": file_hash(list((root / "config" / "tariffs").glob("*.yaml"))),
            "battery": file_hash([root / "config" / "battery.yaml"]),
            "revised_strategy": file_hash([root / "config" / "revised_strategy.yaml"]),
        },
        "tables": tables,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v["rows"] for k, v in tables.items()}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
