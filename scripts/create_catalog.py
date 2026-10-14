"""Create the `edip` catalog on Databricks-managed storage (once, before bundle deploy).

The bundle manages schemas and volumes but not the catalog itself. The catalogs API
rejects default storage, so this runs SQL `CREATE CATALOG` on the first SQL warehouse
(2X-Small, auto stop 5 minutes).
Usage: uv run python scripts/create_catalog.py --profile edip
"""

from __future__ import annotations

import argparse

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

CATALOG = "edip"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)
    try:
        ws.catalogs.get(CATALOG)
        print(f"catalog {CATALOG}: exists")
    except NotFound:
        warehouse = next(iter(ws.warehouses.list()))
        resp = ws.statement_execution.execute_statement(
            statement=(
                f"CREATE CATALOG IF NOT EXISTS {CATALOG} "
                "COMMENT 'Energy Decision Intelligence Platform'"
            ),
            warehouse_id=warehouse.id,
            wait_timeout="50s",
        )
        print(f"catalog {CATALOG}: {resp.status.state.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
