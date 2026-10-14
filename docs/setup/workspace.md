# Cloud setup runbook (Databricks only)

The project runs entirely in one serverless Databricks workspace on AWS (us-east-1) with
Databricks-managed storage. No customer AWS account is used (owner decision,
2026-10-14). Never commit hosts, account IDs, or emails; they live in
`~/.databrickscfg` only.

Cost rule for this demo: smallest sizes, and run
`uv run python scripts/stop_all.py` at the end of every session.

## 1. Workspace (owner, done once)

1. Sign up at databricks.com/try-databricks and take the serverless or express setup:
   region us-east-1, Premium tier.
2. Install the Databricks CLI and sign in:

```sh
databricks auth login --host <workspace URL> --profile edip
databricks auth login --host https://accounts.cloud.databricks.com \
  --account-id <account id> --profile edip-account   # budgets only
```

## 2. Catalog, schemas, volume, Lakebase, app, job

```sh
uv run python scripts/create_catalog.py --profile edip   # SQL CREATE CATALOG on default storage
databricks bundle deploy -t dev -p edip
uv run python scripts/apply_lakebase_ddl.py --profile edip
databricks bundle run edip_hello -t dev -p edip
```

Check the app: open its URL in a browser and visit `/whoami`; it returns
`{"authenticated": true, ...}`. Without signing in, the proxy redirects to login.

## 3. Model preflight

```sh
DATABRICKS_CONFIG_PROFILE=edip uv run python scripts/preflight.py --profile edip
```

## 4. Cost controls

```sh
BUDGET_ALERT_EMAIL=<you> uv run python scripts/set_cost_controls.py --profile edip \
  --auto-stop-mins 5 --account-profile edip-account --monthly-usd 5
```

The budget policy step needs the account **billing admin** role. Budget alerts are
notifications, not hard caps.

## 5. Verify and stop

```sh
uv run python scripts/verify_gate0.py --profile edip   # writes gate0_resources.json
uv run python scripts/stop_all.py --profile edip
```
