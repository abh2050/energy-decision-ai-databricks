"""Download Delta tables to local parquet for local runs (validation tuning).

Uses the first SQL warehouse (2X-Small, auto stop 5 minutes). Output goes to a local
folder outside the repo; nothing here is committed.
Usage: uv run python scripts/fetch_tables.py OUT_DIR [--profile edip]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format

TABLES = {
    "load_observations": (
        "SELECT hour_start, kw_mean, split, dataset_sha256 FROM edip.curated.load_observations"
    ),
    "load_intervals_15min": "SELECT interval_end, kw FROM edip.curated.load_intervals_15min",
    "forecast_predictions": (
        "SELECT target_hour, split, actual, seasonal, point, p10, p50, p90, model_version "
        "FROM edip.curated.forecast_predictions"
    ),
}


def fetch(ws: WorkspaceClient, warehouse_id: str, sql: str) -> pd.DataFrame:
    resp = ws.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
        wait_timeout="50s",
    )
    sid = resp.statement_id
    while resp.status.state.value in ("PENDING", "RUNNING"):
        resp = ws.statement_execution.get_statement(sid)
    if resp.status.state.value != "SUCCEEDED":
        raise RuntimeError(resp.status.error)
    cols = [c.name for c in resp.manifest.schema.columns]
    rows = list(resp.result.data_array or [])
    chunk = resp.result
    while chunk.next_chunk_index is not None:
        chunk = ws.statement_execution.get_statement_result_chunk_n(sid, chunk.next_chunk_index)
        rows += chunk.data_array or []
    return pd.DataFrame(rows, columns=cols)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)
    warehouse = next(iter(ws.warehouses.list()))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in TABLES.items():
        df = fetch(ws, warehouse.id, sql)
        for col in df.columns:
            if col in ("hour_start", "interval_end", "target_hour"):
                df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(None)
            elif col not in ("split", "dataset_sha256", "model_version"):
                df[col] = pd.to_numeric(df[col])
        df.to_parquet(out / f"{name}.parquet")
        print(name, df.shape)
    ws.warehouses.stop(warehouse.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
