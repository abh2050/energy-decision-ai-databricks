"""Verify Gate 0 resources exist and write docs/gates/gate0_resources.json.

The output holds names, states, and pass/fail only: no IDs, hosts, ARNs, or users.
Usage: uv run python scripts/verify_gate0.py --profile edip
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

from edip.core.gate0_checks import Gate0Snapshot, evaluate
from edip.store.lakebase import PROJECT as LAKEBASE
from edip.store.lakebase import connect

CATALOG = "edip"
RAW_VOLUME = f"{CATALOG}.raw.snapshots"
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
        ws.postgres.get_project(f"projects/{LAKEBASE}")
    except NotFound:
        return False, set()
    # Connecting wakes a suspended endpoint; it suspends again after the idle timeout.
    with connect(ws) as conn:
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
        ws.apps.get(APP)
        # A stopped app hides active_deployment, so check the deployment history.
        app_exists = True
        app_deployed = any(
            d.status and d.status.state and d.status.state.value == "SUCCEEDED"
            for d in ws.apps.list_deployments(APP)
        )
    except NotFound:
        app_exists, app_deployed = False, False

    snapshot = Gate0Snapshot(
        catalog_exists=catalog_exists,
        schemas=schemas,
        raw_volume_exists=_exists(ws.volumes.read, RAW_VOLUME),
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
