"""Load parquet files from a volume into Delta tables (persist before agents read them).

--src FILE --table NAME        one file into one table
--dir DIR --schema CAT.SCHEMA  every DIR/<name>.parquet into CAT.SCHEMA.<name>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def load(spark, src: str, table: str) -> dict:  # noqa: ANN001
    df = pd.read_parquet(src)
    digest = hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()
    spark.createDataFrame(df).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        table
    )
    spark.sql(f"ALTER TABLE {table} SET TBLPROPERTIES ('edip.content_sha256' = '{digest}')")
    return {"table": table, "rows": len(df), "sha256": digest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src")
    parser.add_argument("--table")
    parser.add_argument("--dir")
    parser.add_argument("--schema")
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    pairs = []
    if args.dir:
        pairs = [
            (str(p), f"{args.schema}.{p.stem}") for p in sorted(Path(args.dir).glob("*.parquet"))
        ]
    if args.src:
        pairs.append((args.src, args.table))
    for src, table in pairs:
        print(json.dumps(load(spark, src, table)))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
