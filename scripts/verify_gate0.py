"""Verify Gate 0 resources exist and write docs/gates/gate0_resources.json.

The output holds names, states, and pass/fail only: no IDs, hosts, ARNs, or users.
Usage: uv run python scripts/verify_gate0.py --profile edip
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

from edip.core.gate0_checks import Gate0Snapshot, evaluate

CATALOG = "edip"
CREDENTIAL = "edip_s3"
LOCATION = "edip_root"
LAKEBASE = "edip-lakebase"
APP = "edip-hello"
OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "gates" / "gate0_resources.json"


def _exists(fn: object, *args: object) -> bool:
    try:
        fn(*args)  # type: ignore[operator]
    except NotFound:
        return False
    return True


def _lakebase_tables(ws: WorkspaceClient) -> tuple[bool, set[str]]:
    try:
        inst = ws.database.get_database_instance(LAKEBASE)
    except NotFound:
        return False, set()
    if inst.effective_stopped:
        print("lakebase is stopped; start it to verify tables")
        return True, set()
    cred = ws.database.generate_database_credential(
        request_id=str(uuid.uuid4()), instance_names=[LAKEBASE]
    )
    with psycopg.connect(
        host=inst.read_write_dns,
        dbname="databricks_postgres",
        user=ws.current_user.me().user_name,
        password=cred.token,
        sslmode="require",
    ) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'edip'"
        ).fetchall()
    return True, {r[0] for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    parser.add_argument("--max-auto-stop-mins", type=int, default=10)
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)

    catalog_exists = _exists(ws.catalogs.get, CATALOG)
    schemas = {s.name for s in ws.schemas.list(CATALOG)} if catalog_exists else set()
    lakebase_exists, tables = _lakebase_tables(ws)
    try:
        app = ws.apps.get(APP)
        app_exists, app_deployed = True, app.active_deployment is not None
    except NotFound:
        app_exists, app_deployed = False, False

    snapshot = Gate0Snapshot(
        catalog_exists=catalog_exists,
        schemas=schemas,
        storage_credential_exists=_exists(ws.storage_credentials.get, CREDENTIAL),
        external_location_exists=_exists(ws.external_locations.get, LOCATION),
        lakebase_instance_exists=lakebase_exists,
        lakebase_tables=tables,
        app_exists=app_exists,
        app_deployed=app_deployed,
        warehouse_auto_stop_mins={w.name: w.auto_stop_mins for w in ws.warehouses.list()},
        max_auto_stop_mins=args.max_auto_stop_mins,
    )
    items = evaluate(snapshot)
    OUTPUT.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "snapshot": snapshot.model_dump(mode="json"),
                "checks": [i.model_dump() for i in items],
                "all_passed": all(i.passed for i in items),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    for i in items:
        print(f"{'PASS' if i.passed else 'FAIL'}  {i.name} {i.detail}")
    return 0 if all(i.passed for i in items) else 1


if __name__ == "__main__":
    raise SystemExit(main())
