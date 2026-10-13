# Gate 0 cloud setup runbook

Run these in order. Steps marked **owner** need your accounts; everything else is
scripted. Never commit hosts, account IDs, ARNs, or emails: keep them in your CLI
profiles or shell environment.

Cost rule for this demo: smallest size for everything, and run
`uv run python scripts/stop_all.py` at the end of every session.

## 1. Create the workspace (owner)

1. Sign in to the Databricks account console for AWS.
2. Create a workspace on the **Premium** tier (needed for Unity Catalog, Apps, and
   Lakebase) in **us-east-1**.
3. Choose the **serverless** workspace option if it's offered: no customer VPC and no
   NAT gateway charges. If not, use the AWS Quickstart (CloudFormation) and note the stack
   name so Gate 7 can delete it.
4. Attach the workspace to a Unity Catalog metastore in the same region (new accounts
   usually get one automatically).
5. In the workspace, confirm these are enabled: Serverless compute, Databricks Apps,
   Lakebase (Database instances), and Foundation Model APIs pay-per-token with
   `databricks-meta-llama-3-3-70b-instruct` listed under Serving.

## 2. Sign in from this machine (owner)

```sh
aws login
brew install databricks/tap/databricks
databricks auth login --profile edip            # workspace profile
databricks auth login --profile edip-account \  # account profile, for budgets only
  --host https://accounts.cloud.databricks.com --account-id <your account id>
```

## 3. S3, IAM, and Unity Catalog storage

```sh
aws cloudformation deploy --stack-name edip-uc-storage \
  --template-file infra/aws/uc_storage.yaml --capabilities CAPABILITY_NAMED_IAM \
  --tags project=edip
aws cloudformation describe-stacks --stack-name edip-uc-storage \
  --query 'Stacks[0].Outputs'                     # BucketName, RoleArn

databricks --profile edip storage-credentials create \
  --json '{"name":"edip_s3","aws_iam_role":{"role_arn":"<RoleArn>"}}'
databricks --profile edip storage-credentials get edip_s3   # read external_id

aws cloudformation deploy --stack-name edip-uc-storage \
  --template-file infra/aws/uc_storage.yaml --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides ExternalId=<external_id>
```

Copy `scripts/setup_uc.sql` to `scripts/setup_uc.local.sql` (git-ignored), substitute
the bucket name, and run it on a serverless 2X-Small SQL warehouse.

## 4. Bundle: schemas, Lakebase, app, preflight job

```sh
databricks bundle validate -t dev --profile edip
databricks bundle deploy -t dev --profile edip
uv run python scripts/apply_lakebase_ddl.py --profile edip
databricks bundle run edip_hello -t dev --profile edip
```

Open the app URL in a browser and visit `/whoami`: it must return
`{"authenticated": true, ...}`. Without signing in, the proxy redirects to login.

## 5. Model preflight

```sh
uv run python scripts/preflight.py --profile edip
```

This writes `docs/gates/gate0_preflight.json`. A pass needs at least 19 of 20 valid
responses.

## 6. Cost controls

```sh
uv run python scripts/set_cost_controls.py --profile edip --auto-stop-mins 5
BUDGET_ALERT_EMAIL=<you> uv run python scripts/set_cost_controls.py --profile edip \
  --account-profile edip-account --monthly-usd <amount you approve>
```

Budget alerts are notifications, not hard caps.

## 7. Verify and stop

```sh
uv run python scripts/verify_gate0.py --profile edip   # writes gate0_resources.json
uv run python scripts/stop_all.py --profile edip
```

## 8. CI

```sh
gh repo create <repo name> --public --source . --push
gh run watch
```
