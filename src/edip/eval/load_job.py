"""Load a parquet file from a volume into a Delta table (persist before agents read it)."""

from __future__ import annotations

import argparse
import hashlib
import json

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--table", required=True)
    args = parser.parse_args()
    df = pd.read_parquet(args.src)
    digest = hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    spark.createDataFrame(df).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        args.table
    )
    spark.sql(f"ALTER TABLE {args.table} SET TBLPROPERTIES ('edip.content_sha256' = '{digest}')")
    print(json.dumps({"table": args.table, "rows": len(df), "sha256": digest}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
