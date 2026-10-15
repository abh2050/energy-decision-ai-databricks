"""Export every EDIP table before teardown (Gate 7 task 7).

Writes /Volumes/edip/ml/artifacts/export/<schema>/<table>.parquet for every table in the
curated, ml, and eval schemas (raw holds only the source snapshot volume, exported as a
file) and manifest.json with row counts, Delta versions, and SHA256 per file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--out", default="/Volumes/edip/ml/artifacts/export")
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    out = Path(args.out)
    tables = []
    for schema in ("curated", "ml", "eval"):
        (out / schema).mkdir(parents=True, exist_ok=True)
        for row in spark.sql(f"SHOW TABLES IN {args.catalog}.{schema}").collect():
            name = f"{args.catalog}.{schema}.{row['tableName']}"
            version = spark.sql(f"DESCRIBE HISTORY {name} LIMIT 1").collect()[0]["version"]
            df = spark.table(name).toPandas()
            df.attrs = {}
            for col in df.columns:  # nested values as JSON text for portable parquet
                if (
                    df[col].dtype == object
                    and df[col].map(lambda v: isinstance(v, list | dict)).any()
                ):
                    df[col] = df[col].apply(lambda v: json.dumps(v, default=str))
            path = out / schema / f"{row['tableName']}.parquet"
            df.to_parquet(path, index=False)
            tables.append(
                {
                    "table": name,
                    "delta_version": int(version),
                    "rows": len(df),
                    "file": str(path.relative_to(out)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
            print(json.dumps(tables[-1]))
    raw = Path(f"/Volumes/{args.catalog}/raw/snapshots")
    if raw.exists():
        shutil.copytree(raw, out / "raw_snapshots", dirs_exist_ok=True)
    manifest = {"exported_at": datetime.now(UTC).isoformat(timespec="seconds"), "tables": tables}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
