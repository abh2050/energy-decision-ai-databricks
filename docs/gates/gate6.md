# Gate 6 report: Live app

> **Superseded numbers (2026-10-15).** Revised-strategy results in this report were produced with the charge guard defect and are now labelled "revised strategy, post-hoc (guard defect)". The corrected results are in [gate6_review.md](gate6_review.md).

## 1. Gate and date

Gate 6, 2026-10-15. Strategy settings: **revised strategy, post-hoc** (unchanged).
Acceptance targets unchanged. Live business prompt: `business-v2`.

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FastAPI backend (Gate 6 task 1) | Endpoints for scenarios, decision runs (start, confirm, decide), strategy results, operating schedule and forecast, sensitivity, business case, and run detail (agent brief). Operator and viewer roles enforced on the server; signed-in identity from the Databricks Apps OAuth proxy headers; operators are listed as salted SHA256 hashes in the secret scope `edip/operator_hashes`, so no email is in the repository or the database | `src/edip/api/main.py`, `src/edip/api/auth.py` |
| FR24 live workflow | Request, planning proposal (one call), operator confirmation, forecast, optimization, and settlement (the persisted 2014 replay of the confirmed battery cell), risk challenge (one call; the chosen tests read from persisted stress results), business recommendation (one call), operator decision. Both deterministic verdicts are stored next to the agent's recommendation, and any disagreement is flagged in the UI | `src/edip/workflow/live.py` |
| Lakebase persistence (task 2) | Runs, checkpoints (one per step), approvals (identity hash only), and agent call records with prompt version, latency, tokens, and MLflow trace ID. The table's unique key enforces one call per agent per run. One reused connection with OAuth credential refresh | `src/edip/store/repo.py` (`LakebaseRepo`, `MemoryRepo` for tests) |
| Evidence for every selectable battery | For each of the 6 allowlisted cells (25, 50, 100 percent of peak; 2 and 4 hours): full replay of six strategies on both tariffs, three stress tests, excess-month trace, both verdicts, and agent evidence rows. Run locally (owner decision 2026-10-14) and loaded to Delta | `src/edip/eval/cells_job.py`; Delta `edip.eval.cell_annual`, `cell_stress_results`, `cell_verdicts`, `cell_evidence`, `cell_schedules`, `cell_excess_months`, `cell_peak_moments` |
| App snapshot | Job `edip-gate6-publish` copies each table the app shows from Delta to the volume `edip.ml.artifacts/app`, with a manifest of source table, Delta version, rows, and SHA256; the app reads only this snapshot (no SQL warehouse) | `src/edip/eval/publish_job.py`, `src/edip/api/data.py`, `resources/gate6_jobs.yml` |
| React app (task 3) | Four views from PRD 4.1: operating workspace (forecast with P10 to P90 band, state of charge, planned and settled schedule, decision controls), strategy comparison (bill, net benefit, billed peak, throughput, degradation, regret, violations, frozen target), agent decision brief (planning interpretation, risk findings, recommendation, linked evidence rows, call records), pilot business case (verdicts, sensitivity map, flip boundaries, stress results, known limit, assumptions, capital layer). `live` adapter; `replay` and `sandbox` adapters are placeholders for Gate 7 | `frontend/src/` |
| Labels (task 4) | Every view shows mode, result label, evaluation period, client, model version, dataset hash, publish time, units, and the measured and assumed lists; every card names its source table and Delta version; assumed values carry an "assumed" badge, synthetic tariffs a "synthetic" badge, template answers a "template" badge | `frontend/src/components/ProvenanceBar.tsx`, `ui.tsx` |
| Deployment (task 5) | `edip-live` on Databricks Apps through the bundle, with secret, serving endpoint, and Lakebase resources; grants limited to READ VOLUME on the snapshot, CAN_EDIT on the trace experiment, and SELECT, INSERT, UPDATE on the five Lakebase tables. Replaces the Gate 0 hello app | `resources/app.yml`, `app.yaml`, `requirements.txt`, `scripts/grant_app.py` |

## 3. Test results

- pytest: **140 passed, 0 failed** (Gate 6 adds 6 API tests: sign-in required, viewer
  cannot write, settings outside the allowlist rejected, full flow with persistence and
  one call per agent, repository uniqueness, provenance on every view).
- Playwright (`frontend/e2e/live_app.spec.ts`, 6 tests), three ways:

| Run | Store and model | Result |
|---|---|---|
| CI and local, synthetic snapshot | in-memory store, template fallback (no model calls) | **6 passed** |
| Local, real snapshot | Lakebase and the Foundation Model API | **6 passed** (first run: 4 failed; fixes below) |
| **Deployed app on Databricks Apps** | Lakebase and the Foundation Model API, OAuth token | **4 passed, 2 skipped** |

  The two tests skipped on the deployed app are: login (there the Apps proxy handles
  OAuth sign-in before the app; checked separately, an unauthenticated request returns
  401) and viewer blocked (it needs a second identity on the workspace; the server-side
  403 is covered locally and in CI).
- Defects found and fixed during these runs:
  - YAML dates in the optimizer settings could not be written to JSONB; the in-memory
    store now round-trips through JSON like Lakebase, so tests catch this.
  - One Postgres connection per query made a confirm take 26 s; it now takes 3 s.
  - The snapshot loaded on the first request, so the first page timed out; it now warms
    up at start.
  - The sensitivity map dropped the synthetic spreads.
  - The default operating day was an idle day; it is now the day with the most discharge.
  - Apps could not install the Python 3.12 lockfile; see deviation 1.
  - The publish job wrote Spark Connect metrics into parquet metadata.

## 4. Key numbers

- **Exit run on the deployed app:** run `e0e51435ee1d42bb` passed every step from
  requested to decided. All three agent calls were valid, each with an MLflow trace ID
  (experiment `/Shared/edip/live_app`). Approval "approve" was stored in Lakebase; it
  reads back on reload. Source: Lakebase `edip.decision_runs`, `edip.agent_calls`,
  `edip.approvals`.
- **Deployed runs:** 3 runs from the Playwright suite (approve, revise, reject), all
  reached `decided` with 3 agent calls each. In the two runs inspected (`e0e51435…`,
  `3d28cd3e…`), agent latency per call was 2.0 to 8.3 s, with 1,790 to 1,968 tokens in
  and 97 to 541 out.
- **Verdicts by battery cell** (`edip.eval.cell_verdicts`; frozen rule / A1):

| Battery | 2 hours | 4 hours |
|---|---|---|
| 25% of peak | withhold / withhold | withhold / withhold |
| 50% of peak | revise / withhold | revise / revise |
| 100% of peak | revise / revise | revise / revise |

  No cell reaches proceed: every cell breaches at least one stress limit. The 50 percent,
  2 hour cell reproduces Gate 5 exactly (B-19 ML −10,158, robust −3,133 USD), and every
  cell has 0 violations.
- **Agent behaviour seen on the deployed app** (recorded, not fixed):
  - In run `3d28cd3e9f3e4c49` the business agent recommended **revise** while the live
    verdict for the battery is **withhold**. The UI flagged the disagreement.
  - In the same run the planning agent claimed "ml_forecast has a higher net savings"
    while citing 17,758 USD, which is lower than robust's 24,784 USD. The validator
    confirms each number matches its row; it cannot check a comparison between numbers.
  - Screenshots: [gate6_screens/](gate6_screens/).
- **Snapshot** (`manifest.json` in `edip.ml.artifacts/app`): 8 tables, Delta version 1
  each; `cell_schedules` 630,720 rows; `forecasts` 8,760 rows.

## 5. Deviations from the PRD and why

1. **The app runs through `uv` with Python 3.12.** The Databricks Apps image has an older
   Python, which cannot install this project's lockfile (`contourpy==1.4.0` requires
   3.12). Rather than re-resolve dependencies for an older Python (rule 6), the app
   installs only `uv==0.6.14` and runs `uv run --frozen` from the committed `uv.lock`.
   The app source is therefore the repository root, not `src/`. Start-up takes about 2
   minutes longer.
2. **Forecast, optimization, and settlement in a live run are persisted results, not a
   fresh replay.** Each confirmed cell's 2014 replay was computed in advance for all 6
   allowlisted cells; each run step's checkpoint records the source table, Delta version,
   and SHA256. A full-year replay per request would take minutes on app compute.
3. **The app reads a published snapshot of Delta, not Delta through SQL.** This avoids a
   SQL warehouse (cost); the manifest records every table's Delta version.
4. **Playwright specs live in `frontend/e2e`**, not `tests/e2e`, because Playwright
   resolves its package from `frontend/node_modules`.
5. **Login is tested with the proxy's forwarded identity header locally.** On the deployed
   app, OAuth sign-in is done by Databricks before requests reach the app; the suite runs
   there with an OAuth token.
6. **The Gate 0 hello app was removed** (replaced by `edip-live`); `verify_gate0.py`
   still names it.

## 6. Open questions for the owner

1. **Second identity for the viewer test on Databricks.** The viewer path passes locally
   and in CI. Should a workspace viewer (a second user or a service principal) be added
   so the viewer test also runs on the deployed app?
2. **Agent claims that compare numbers.** The validator checks every number but not
   comparisons ("higher", "lower"). Should Gate 7 add a check for comparisons, or should
   the sandbox show the agent's text as recorded, with the deterministic verdicts beside
   it as now?
3. **Live business prompt** (carried from Gate 5): v1 scored higher on decisions than v2.
   The disagreement flag makes wrong recommendations visible.

## 7. Exit checklist

| Item | Status |
|---|---|
| The deployed app completes one full decision run end to end | **Pass** (run `e0e51435ee1d42bb`, Databricks Apps, Lakebase, three valid agent calls with traces, approval persisted) |
| Playwright: login, full decision flow, approval persistence, viewer blocked from approving | **Pass** (6 of 6 locally and in CI; 4 of 4 runnable on the deployed app, 2 skipped there as above) |
| Operator flows from the frozen targets: view recommendation, approve, revise, reject, viewer blocked | **Pass** |
| Provenance, units, evaluation period, measured and assumed labels on every view | **Pass** (Playwright test 6) |
| Runs, checkpoints, approvals, and agent calls persisted in Lakebase | **Pass** |
| App and billed resources stopped after the session | **Pass** (`scripts/stop_all.py`; Lakebase suspends itself after 5 idle minutes) |

Awaiting approval to start Gate 7.
