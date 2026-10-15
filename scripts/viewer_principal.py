"""A viewer-only service principal for the deployed app's viewer test (Gate 6 review).

It gets the workspace-access entitlement (the Apps proxy rejects a principal without it)
and CAN_USE on the app, and nothing else (no operator hash, so the app treats it as a
viewer). `--token-file` writes a short-lived OAuth token for it (client credentials)
to a local file outside the repository; the OAuth secret is deleted right after the token
is issued, so no lasting credential exists. Remove the principal at teardown (Gate 7).

Usage: uv run python scripts/viewer_principal.py --profile edip --token-file PATH
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import AppAccessControlRequest, AppPermissionLevel
from databricks.sdk.service.iam import Patch, PatchOp, PatchSchema

NAME = "edip-viewer-e2e"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    parser.add_argument("--app", default="edip-live")
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()
    ws = WorkspaceClient(profile=args.profile)
    sp = next(iter(ws.service_principals.list(filter=f'displayName eq "{NAME}"')), None)
    if sp is None:
        sp = ws.service_principals.create(display_name=NAME, active=True)
        print(f"created service principal {NAME}")
    if "workspace-access" not in [e.value for e in (sp.entitlements or [])]:
        ws.service_principals.patch(
            sp.id,
            operations=[
                Patch(op=PatchOp.ADD, path="entitlements", value=[{"value": "workspace-access"}])
            ],
            schemas=[PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP],
        )
        print("added the workspace-access entitlement")
    ws.apps.update_permissions(
        args.app,
        access_control_list=[
            AppAccessControlRequest(
                service_principal_name=sp.application_id,
                permission_level=AppPermissionLevel.CAN_USE,
            )
        ],
    )
    print(f"granted CAN_USE on {args.app} (no operator role)")
    secret = ws.service_principal_secrets_proxy.create(service_principal_id=sp.id)
    try:
        resp = requests.post(
            f"{ws.config.host}/oidc/v1/token",
            auth=(sp.application_id, secret.secret),
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            timeout=30,
        )
        resp.raise_for_status()
        args.token_file.write_text(resp.json()["access_token"])
        os.chmod(args.token_file, 0o600)
        print(f"token written ({resp.json().get('expires_in')} s lifetime)")
    finally:
        ws.service_principal_secrets_proxy.delete(service_principal_id=sp.id, secret_id=secret.id)
        print("OAuth secret deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
