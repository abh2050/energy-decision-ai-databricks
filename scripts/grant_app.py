"""Grant the live app's service principal what it needs, and nothing more (Gate 6).

- Unity Catalog: USE CATALOG edip, USE SCHEMA edip.ml, READ VOLUME edip.ml.artifacts
  (the published snapshot; the app reads no Delta table directly).
- MLflow: CAN_EDIT on /Shared/edip/live_app (agent traces).
- Lakebase: a Postgres role for the service principal with SELECT, INSERT, UPDATE on the
  five operational tables (no DELETE, no DDL).

Usage: uv run python scripts/grant_app.py --profile edip --app edip-live
"""

from __future__ import annotations

import argparse

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import PermissionsChange, Privilege, SecurableType
from databricks.sdk.service.ml import ExperimentAccessControlRequest, ExperimentPermissionLevel

from edip.store import lakebase

EXPERIMENT = "/Shared/edip/live_app"
TABLES = ("scenarios", "decision_runs", "checkpoints", "approvals", "agent_calls")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    parser.add_argument("--app", default="edip-live")
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)
    sp = ws.apps.get(args.app).service_principal_client_id

    for kind, name, privs in (
        (SecurableType.CATALOG, "edip", [Privilege.USE_CATALOG]),
        (SecurableType.SCHEMA, "edip.ml", [Privilege.USE_SCHEMA]),
        (SecurableType.VOLUME, "edip.ml.artifacts", [Privilege.READ_VOLUME]),
    ):
        ws.grants.update(
            securable_type=kind.value,
            full_name=name,
            changes=[PermissionsChange(principal=sp, add=privs)],
        )
        print(f"granted {[p.value for p in privs]} on {name}")

    try:
        exp_id = ws.experiments.get_by_name(EXPERIMENT).experiment.experiment_id
    except Exception:
        exp_id = ws.experiments.create_experiment(EXPERIMENT).experiment_id
    ws.experiments.update_permissions(
        exp_id,
        access_control_list=[
            ExperimentAccessControlRequest(
                service_principal_name=sp, permission_level=ExperimentPermissionLevel.CAN_EDIT
            )
        ],
    )
    print(f"granted CAN_EDIT on {EXPERIMENT}")

    with lakebase.connect(ws) as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (sp,))
        if not cur.fetchone():
            cur.execute("SELECT databricks_create_role(%s, 'SERVICE_PRINCIPAL')", (sp,))
        cur.execute(f'GRANT USAGE ON SCHEMA edip TO "{sp}"')
        tables = ", ".join(f"edip.{t}" for t in TABLES)
        cur.execute(f'GRANT SELECT, INSERT, UPDATE ON {tables} TO "{sp}"')
        conn.commit()
    print("granted Lakebase role and table privileges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
