"""Stop everything that bills while idle: EDIP apps, the Lakebase instance, SQL warehouses.

Run at the end of every working session. Budget alerts are not hard caps; this is.
Usage: uv run python scripts/stop_all.py --profile edip
"""

from __future__ import annotations

import argparse

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.sql import State

APPS = ["edip-hello"]
LAKEBASE = "edip-lakebase"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)

    apps = {a.name: a for a in ws.apps.list()}
    for name in APPS:
        app = apps.get(name)
        state = app.compute_status.state.value if app and app.compute_status else None
        if state in ("ACTIVE", "STARTING", "UPDATING"):
            ws.apps.stop(name)
            print(f"app {name}: stop requested")
        else:
            print(f"app {name}: {state or 'not found'}")

    # Lakebase Autoscaling suspends itself after 5 idle minutes; report its state only.
    try:
        project = f"projects/{LAKEBASE}"
        for branch in ws.postgres.list_branches(project):
            for ep in ws.postgres.list_endpoints(branch.name):
                state = ep.status.current_state if ep.status else None
                print(f"lakebase endpoint {ep.name.rsplit('/', 1)[-1]}: {state}")
    except NotFound:
        print(f"lakebase {LAKEBASE}: not found")

    for wh in ws.warehouses.list():
        if wh.state not in (State.STOPPED, State.STOPPING, State.DELETED):
            ws.warehouses.stop(wh.id)
            print(f"warehouse {wh.name}: stop requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
