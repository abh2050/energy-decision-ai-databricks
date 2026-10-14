# Gate 0 report: Platform preflight

## 1. Gate and date

Gate 0, started 2026-10-13, cloud steps completed 2026-10-14.

## 2. What was built

Gate 0 has no FR IDs; items map to the Gate 0 tasks (T1 to T8) in `CLAUDE.md`.

| Task | Built | Files |
|---|---|---|
| T1 Asset Bundle, dev + prod | Bundle with both targets, `project=edip` tags, wheel artifact; deployed to dev | `databricks.yml`, `resources/` |
| T2 Catalog and schemas | Catalog `edip` (SQL `CREATE CATALOG` on default storage); schemas `raw`, `curated`, `ml`, `eval`; volume `raw.snapshots` for FR1 | `scripts/create_catalog.py`, `resources/schemas.yml` |
| T3 Storage | Databricks-managed storage instead of a customer S3 bucket and IAM role (deviation 1) | — |
| T4 Lakebase + 5 tables | Lakebase Autoscaling project `edip-lakebase` (0.5 to 1 CU, suspends after 5 idle minutes); tables `scenarios`, `decision_runs`, `checkpoints`, `approvals`, `agent_calls` with lineage columns and matching Pydantic models | `resources/lakebase.yml`, `src/edip/store/`, `scripts/apply_lakebase_ddl.py` |
| T5 Preflight script | 20 calls, json_schema response format, 30 s deadline, `max_retries=0`, 2 s spacing; MLflow run tagged with config hash and prompt version; also a bundle job | `scripts/preflight.py`, `src/edip/core/preflight_stats.py`, `src/edip/core/wire_schema.py`, `resources/gate0_jobs.yml` |
| T6 Hello world app | FastAPI `/healthz` and `/whoami` deployed to Databricks Apps; authenticated request verified, unauthenticated request redirected to login | `src/edip/api/main.py`, `src/app.yaml`, `resources/app.yml` |
| T7 Cost controls | Warehouse 2X-Small with 5 minute auto stop; $5 monthly budget with email alert; budget policy blocked on a role (open question 1); one-command stop | `scripts/set_cost_controls.py`, `scripts/stop_all.py` |
| T8 CI | Ruff check and format, pytest, repo scan for workspace URLs, tokens, and emails, `npm ci`, gitleaks | `.github/workflows/ci.yml`, `scripts/scan_public_bundle.py` |
| Exit evidence | Resource verifier writing names and states only | `scripts/verify_gate0.py`, `src/edip/core/gate0_checks.py` |

Also: `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/PRD.md` (FR1, FR6, FR7, and
section 5 updated), `config/agent_allowlist.yaml` (empty until Gate 5), and the runbook
`docs/setup/workspace.md`.

## 3. Test results

- pytest: **26 passed, 0 failed** (preflight scoring 5, secret scan 7, hello app 3,
  Lakebase models 3, Gate 0 checks 6, wire schema 2).
- Ruff check and Ruff format: clean.
- Repo scan (`scan_public_bundle.py .`): 0 findings.
- `npm ci` in `frontend/`: installs from the lockfile.
- `databricks bundle validate` and `deploy -t dev`: succeeded.
- Resource verifier: 7 of 7 checks pass.
- App: unauthenticated `GET /whoami` returned HTTP 302 to the workspace login; an
  OAuth-authenticated `GET /whoami` returned HTTP 200 with `authenticated: true`.
- gitleaks: runs in CI only (not installed locally).

## 4. Key numbers

| Number | Value | Source |
|---|---|---|
| Structured output preflight | 20 of 20 valid (rate 1.0) | `docs/gates/gate0_preflight.json` |
| Median latency | 1.10 s | same |
| Tokens, 20 calls | 8,060 prompt, 1,047 completion | same |
| Resource checks | 7 of 7 pass | `docs/gates/gate0_resources.json` |
| Warehouse auto stop | 5 minutes | same |

The first preflight run failed 20 of 20 before reaching the model: 16 calls returned
400 because the endpoint rejects the JSON Schema `pattern` keyword, and 4 returned 429
because calls were back to back. Neither consumed tokens. The fix sends a schema without
unsupported constraint keywords (`src/edip/core/wire_schema.py`) while validating every
response locally against the full Pydantic model, and spaces calls 2 s apart.

## 5. Deviations and why

1. **No customer AWS account (owner decision, 2026-10-14).** The owner's AWS account is a
   member of an AWS Organization whose policies allow only us-east-2 and blocked
   Databricks from assuming the Unity Catalog IAM role. The owner chose to run everything
   in the serverless Databricks workspace with Databricks-managed storage. FR1 now uses
   the volume `edip.raw.snapshots`; PRD section 5 and Gate 0 task 3 are updated. The
   bucket, IAM role, and storage credential created during the attempt were deleted.
2. **Lakebase Autoscaling instead of a provisioned instance**: it suspends to zero when
   idle. The 2 day history retention is the minimum the API accepts.
3. **Dev target without development mode**: development mode prefixed schema names with
   the user name; the PRD needs exact names. Jobs have no schedules.
4. Extra folders not in the section 4 layout: `scripts/` and `docs/setup/`. App entry
   files `src/app.yaml` and `src/requirements.txt` sit in `src/`, the app source root.
5. `mlflow-skinny` instead of full `mlflow` for the client.
6. The PRD byline reads "Owner: project owner" (rule 7); commits use the GitHub noreply
   address.
7. Gate 5 will reuse `wire_schema` because the endpoint rejects some JSON Schema keywords.

## 6. Open questions for the owner

1. **Budget policy**: creating it needs the account **billing admin** role. In the
   account console, open User management, select your user, and add the Billing admin
   role; then I rerun `set_cost_controls.py`. The $5 budget alert already exists.
2. The SDK offers a `BLOCK_USAGE` budget action. Should I test whether it gives a real
   spending cap?

## 7. Exit checklist

| Item | Status |
|---|---|
| Every resource above exists | **Pass** for the catalog, schemas, volume, Lakebase and tables, app, warehouse auto stop, and budget alert. **Fail** for the budget policy (needs a role; open question 1) |
| `docs/gates/gate0_preflight.json` saved | **Pass** |
| Valid structured output in at least 19 of 20 calls | **Pass** (20 of 20) |
| Lockfiles committed | **Pass** |
| CI passes | See the CI run on `main` |

Awaiting approval to start Gate 1.
