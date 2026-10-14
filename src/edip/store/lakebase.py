"""Connect to the Lakebase Autoscaling project with a short-lived OAuth credential."""

from __future__ import annotations

import psycopg
from databricks.sdk import WorkspaceClient

PROJECT = "edip-lakebase"
DATABASE = "databricks_postgres"


def primary_endpoint(ws: WorkspaceClient, project: str = PROJECT) -> tuple[str, str]:
    """Return (endpoint resource name, host) of the default branch's read-write endpoint."""
    branches = list(ws.postgres.list_branches(f"projects/{project}"))
    default = next((b for b in branches if b.status and b.status.default), branches[0])
    for ep in ws.postgres.list_endpoints(default.name):
        if ep.status and "READ_WRITE" in str(ep.status.endpoint_type):
            return ep.name, ep.status.hosts.host
    raise LookupError(f"no read-write endpoint in {default.name}")


def connect(ws: WorkspaceClient, project: str = PROJECT) -> psycopg.Connection:
    endpoint, host = primary_endpoint(ws, project)
    token = ws.postgres.generate_database_credential(endpoint=endpoint).token
    return psycopg.connect(
        host=host,
        dbname=DATABASE,
        user=ws.current_user.me().user_name,
        password=token,
        sslmode="require",
    )
