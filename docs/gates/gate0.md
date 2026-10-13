# Gate 0 report: Platform preflight

## 1. Gate and date

Gate 0, 2026-10-13. Status: **local half complete; cloud half not yet run** (it needs
workspace and AWS credentials).

## 2. What was built

Gate 0 has no FR IDs; items map to the Gate 0 tasks (T1 to T8) in `CLAUDE.md`.

| Task | Built | Files |
|---|---|---|
| T1 Asset Bundle, dev + prod | Bundle with both targets, `project=edip` tags, wheel artifact | `databricks.yml`, `resources/` |
| T2 Catalog and schemas | Schemas `raw`, `curated`, `ml`, `eval` in the bundle; catalog via SQL | `resources/schemas.yml`, `scripts/setup_uc.sql` |
| T3 S3, IAM, credential, location | CloudFormation: versioned, encrypted, TLS-only, public access blocked bucket with lifecycle rules; self-assuming UC role | `infra/aws/uc_storage.yaml`, `scripts/setup_uc.sql` |
| T4 Lakebase + 5 tables | CU_1 instance in bundle; DDL with lineage columns; Pydantic row models; OAuth-credential apply script | `resources/lakebase.yml`, `src/edip/store/`, `scripts/apply_lakebase_ddl.py` |
| T5 Preflight script | 20 calls, json_schema response format, 30 s deadline, `max_retries=0`, MLflow run tagged with config hash and prompt version; also a bundle job | `scripts/preflight.py`, `src/edip/core/preflight_stats.py`, `resources/gate0_jobs.yml` |
| T6 Hello world app | FastAPI `/healthz` and `/whoami`, which returns 401 without forwarded identity and never echoes it | `src/edip/api/main.py`, `src/app.yaml`, `resources/app.yml` |
| T7 Cost controls | Warehouse auto stop; account budget policy and monthly budget email alert; one-command stop | `scripts/set_cost_controls.py`, `scripts/stop_all.py` |
| T8 CI | Ruff check and format, pytest, repo scan for workspace URLs, tokens, and emails, `npm ci`, gitleaks | `.github/workflows/ci.yml`, `scripts/scan_public_bundle.py` |
| Exit 1 evidence | Resource verifier that writes names and states only | `scripts/verify_gate0.py`, `src/edip/core/gate0_checks.py` |
| Exit 3 lockfiles | `uv.lock`, exact pins in `pyproject.toml`; `frontend/package-lock.json` with exact pins | |

Also: `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/PRD.md`,
`config/agent_allowlist.yaml` (empty until Gate 5), and the cloud runbook
`docs/setup/workspace.md`.

## 3. Test results

- pytest: **23 passed, 0 failed** (preflight scoring 5, secret scan 7, hello app 3,
  Lakebase models 3, Gate 0 checks 5).
- Ruff check: all checks passed. Ruff format: 23 files already formatted.
- Repo scan (`scan_public_bundle.py .`): 0 findings.
- `npm ci` in `frontend/`: 84 packages installed from the lockfile.
- Not run locally: gitleaks (not installed here; runs in CI) and
  `databricks bundle validate` (CLI not installed, no workspace yet).

## 4. Key numbers

None yet. The preflight valid rate, latency, and tokens will be in
`docs/gates/gate0_preflight.json` and the resource checks in
`docs/gates/gate0_resources.json` once the cloud half runs.

## 5. Deviations and why

1. Extra folders not in the section 4 layout: `scripts/` (named by task 5),
   `infra/aws/` (CloudFormation), `docs/setup/` (runbook).
2. App entry files `src/app.yaml` and `src/requirements.txt` sit in `src/` because the
   bundle deploys `src/` as the app source.
3. `mlflow-skinny` instead of full `mlflow` for the client (logging and tracing, smaller
   install). The full server package is not needed locally.
4. The PRD byline was replaced with "Owner: project owner" because rule 7 bans personal
   identities in the repo. Git commits use the GitHub noreply address.
5. Dev target uses `name_prefix: ""` so schemas and the app keep their exact names in the
   single demo workspace. Dev and prod therefore share names; only dev is deployed.

## 6. Open questions for the owner

1. **Monthly budget alert amount** for `set_cost_controls.py --monthly-usd`. I have not
   set a number (rule 2). The SDK also offers a `BLOCK_USAGE` budget action; should we
   test whether it gives a real cap?
2. **Region**: us-east-1 assumed. Confirm, or name another region where Apps, Lakebase,
   and the Llama 3.3 70B pay-per-token endpoint are all available.
3. **GitHub repo name** (public, for Pages at Gate 7).
4. **Anchored tariff for Gate 1**: which published US commercial time of use tariff
   should be used? If you have no preference, I'll propose one with its source document.
5. **Unity Catalog master role ARN** in the template is the Databricks-published default;
   confirm it matches the value in the storage credential dialog.

## 7. Exit checklist

| Item | Status |
|---|---|
| Every resource above exists | **Pending**: cloud half not run (runbook steps 1 to 7) |
| `docs/gates/gate0_preflight.json` saved | **Pending**: runbook step 5 |
| Valid structured output in at least 19 of 20 calls | **Pending**: runbook step 5 |
| Lockfiles committed | **Pass** |
| CI passes | **Pending**: no GitHub repo yet (runbook step 8); all CI steps except gitleaks pass locally |

Gate 0 is not complete. Next: you run runbook steps 1 and 2, then I run the rest and
update this report.

Awaiting approval to start Gate 1.
