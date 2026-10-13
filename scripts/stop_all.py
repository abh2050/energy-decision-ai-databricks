"""Stop everything that bills while idle: EDIP apps, the Lakebase instance, SQL warehouses.

Run at the end of every working session. Budget alerts are not hard caps; this is.
Usage: uv run python scripts/stop_all.py --profile edip
"""

from __future__ import annotations

import argparse

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.database import DatabaseInstance
from databricks.sdk.service.sql import State

APPS = ["edip-hello"]
LAKEBASE = "edip-lakebase"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)

    existing_apps = {a.name for a in ws.apps.list()}
    for name in APPS:
        if name in existing_apps:
            ws.apps.stop(name)
            print(f"app {name}: stop requested")

    try:
        inst = ws.database.get_database_instance(LAKEBASE)
    except NotFound:
        print(f"lakebase {LAKEBASE}: not found")
    else:
        if not inst.effective_stopped:
            ws.database.update_database_instance(
                LAKEBASE, DatabaseInstance(name=LAKEBASE, stopped=True), update_mask="stopped"
            )
            print(f"lakebase {LAKEBASE}: stop requested")
        else:
            print(f"lakebase {LAKEBASE}: already stopped")

    for wh in ws.warehouses.list():
        if wh.state not in (State.STOPPED, State.STOPPING, State.DELETED):
            ws.warehouses.stop(wh.id)
            print(f"warehouse {wh.name}: stop requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
