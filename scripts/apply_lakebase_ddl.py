"""Apply src/edip/store/lakebase_schema.sql to the Lakebase instance.

Authenticates with a short-lived Databricks-issued database credential (OAuth), so no
static password exists. Usage: uv run python scripts/apply_lakebase_ddl.py --profile edip
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

import psycopg
from databricks.sdk import WorkspaceClient

from edip.store.models import TABLE_MODELS

INSTANCE = "edip-lakebase"
DATABASE = "databricks_postgres"
DDL = Path(__file__).resolve().parents[1] / "src" / "edip" / "store" / "lakebase_schema.sql"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)

    inst = ws.database.get_database_instance(INSTANCE)
    cred = ws.database.generate_database_credential(
        request_id=str(uuid.uuid4()), instance_names=[INSTANCE]
    )
    user = ws.current_user.me().user_name
    with psycopg.connect(
        host=inst.read_write_dns,
        dbname=DATABASE,
        user=user,
        password=cred.token,
        sslmode="require",
    ) as conn:
        conn.execute(DDL.read_text())
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'edip'"
        ).fetchall()
    found = sorted(r[0] for r in rows)
    missing = sorted(set(TABLE_MODELS) - set(found))
    print(f"tables in edip schema: {found}")
    if missing:
        print(f"missing: {missing}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
