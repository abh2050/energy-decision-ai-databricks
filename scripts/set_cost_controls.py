"""Gate 0 task 7: SQL warehouse auto stop, budget policy, and budget notifications.

Workspace part (always): sets auto stop on every SQL warehouse and verifies it.
Account part (--account-profile): creates a serverless budget policy tagged
project=edip bound to the workspace, and a monthly budget with an email alert.
Budget alerts are notifications, not hard caps; scripts/stop_all.py is the brake.

Usage:
  uv run python scripts/set_cost_controls.py --profile edip --auto-stop-mins 5
  BUDGET_ALERT_EMAIL=... uv run python scripts/set_cost_controls.py --profile edip \
      --account-profile edip-account --monthly-usd <owner-approved amount>
"""

from __future__ import annotations

import argparse
import os

from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.service import billing, compute

POLICY_NAME = "edip"
BUDGET_NAME = "edip-monthly"


def set_warehouse_auto_stop(ws: WorkspaceClient, minutes: int) -> list[tuple[str, int | None]]:
    results = []
    for wh in ws.warehouses.list():
        if wh.auto_stop_mins != minutes:
            ws.warehouses.edit(wh.id, auto_stop_mins=minutes).result()
        results.append((wh.name, ws.warehouses.get(wh.id).auto_stop_mins))
    return results


def ensure_budget_policy(acct: AccountClient, workspace_id: int) -> str:
    for p in acct.budget_policy.list():
        if p.policy_name == POLICY_NAME:
            return p.policy_id
    policy = acct.budget_policy.create(
        policy=billing.BudgetPolicy(
            policy_name=POLICY_NAME,
            custom_tags=[compute.CustomPolicyTag(key="project", value="edip")],
            binding_workspace_ids=[workspace_id],
        )
    )
    return policy.policy_id


def ensure_budget(acct: AccountClient, workspace_id: int, monthly_usd: float, email: str) -> str:
    for b in acct.budgets.list():
        if b.display_name == BUDGET_NAME:
            return b.budget_configuration_id
    created = acct.budgets.create(
        billing.CreateBudgetConfigurationBudget(
            display_name=BUDGET_NAME,
            filter=billing.BudgetConfigurationFilter(
                workspace_id=billing.BudgetConfigurationFilterWorkspaceIdClause(
                    operator=billing.BudgetConfigurationFilterOperator.IN,
                    values=[workspace_id],
                )
            ),
            alert_configurations=[
                billing.CreateBudgetConfigurationBudgetAlertConfigurations(
                    time_period=billing.AlertConfigurationTimePeriod.MONTH,
                    trigger_type=billing.AlertConfigurationTriggerType.CUMULATIVE_SPENDING_EXCEEDED,
                    quantity_type=billing.AlertConfigurationQuantityType.LIST_PRICE_DOLLARS_USD,
                    quantity_threshold=str(monthly_usd),
                    action_configurations=[
                        billing.CreateBudgetConfigurationBudgetActionConfigurations(
                            action_type=billing.ActionConfigurationType.EMAIL_NOTIFICATION,
                            target=email,
                        )
                    ],
                )
            ],
        )
    )
    return created.budget.budget_configuration_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="edip")
    parser.add_argument("--auto-stop-mins", type=int, default=5)
    parser.add_argument("--account-profile", default=None)
    parser.add_argument("--monthly-usd", type=float, default=None)
    args = parser.parse_args()

    ws = WorkspaceClient(profile=args.profile)
    for name, mins in set_warehouse_auto_stop(ws, args.auto_stop_mins):
        print(f"warehouse {name}: auto_stop_mins={mins}")

    if not args.account_profile:
        print("account part skipped (no --account-profile)")
        return 0
    if args.monthly_usd is None:
        parser.error("--monthly-usd is required with --account-profile")
    email = os.environ.get("BUDGET_ALERT_EMAIL")
    if not email:
        parser.error("set BUDGET_ALERT_EMAIL in the environment (never commit it)")
    acct = AccountClient(profile=args.account_profile)
    workspace_id = ws.get_workspace_id()
    ensure_budget_policy(acct, workspace_id)
    ensure_budget(acct, workspace_id, args.monthly_usd, email)
    print(f"budget policy '{POLICY_NAME}' and budget '{BUDGET_NAME}' in place")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
