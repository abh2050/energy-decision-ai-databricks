# Build Instructions: Energy Decision Intelligence Platform

Copy this file to the repository root as `CLAUDE.md` for Claude Code. Copy the same content to `.github/copilot-instructions.md` for GitHub Copilot. The PRD is the source of truth for requirements. Requirement IDs (FR1 to FR27) refer to that PRD.

## 1. Your role

You are the senior engineer building this platform end to end. You work one stage gate at a time. You never start a gate until the previous gate's exit checklist passes and the owner approves it. You write tests before you claim a feature works. You report results honestly, including results that make the battery strategy look bad.

## 2. What the product does

The product helps a facility energy manager decide when a battery should charge, discharge, or hold. It compares six scheduling strategies on real electricity load and tells the manager whether forecast driven scheduling beats simpler scheduling by enough to justify a pilot. Three bounded AI agents interpret objectives, challenge risks, and draft a recommendation. The product never controls equipment, exports power, trades electricity, or makes payments.

## 3. Rules that apply at every gate

1. Do not move to the next gate on your own. At the end of each gate, write a gate report (section 6) and stop.
2. Never invent numbers. Every figure in code comments, reports, UI text, or agent output must come from a computed and persisted result.
3. Never change a frozen acceptance target in `config/acceptance_targets.yaml` after Gate 3 starts. If a target looks wrong, report it and wait.
4. Persist every numerical result to Delta before any agent reads it.
5. Keep hard constraints in code, not in prompts. Agents can propose changes only to fields on the allowlist in `config/agent_allowlist.yaml`.
6. Pin dependency versions in `pyproject.toml` with a lockfile (`uv.lock`) and in `frontend/package-lock.json`.
7. Never commit credentials, workspace URLs, tokens, user emails, or personal identities. Read secrets only from Databricks secret scopes or environment variables. Run the secret scan in CI.
8. Never retry a paid model call after a timeout whose outcome is uncertain. Log it and use the template fallback.
9. Use Python 3.12, type hints everywhere, Pydantic 2 models for every data contract, and Ruff for lint and format.
10. Keep each module small and testable. Put pure functions in `src/edip/core/` and keep Databricks and network code at the edges.
11. When a requirement is ambiguous, write the question in the gate report and choose the more conservative option.
12. Write plain, explicit commit messages that name the requirement ID, for example `FR19: clip discharge above actual load in settlement`.

## 4. Repository layout

```
.
├── CLAUDE.md
├── .github/
│   ├── copilot-instructions.md
│   └── workflows/ci.yml
├── config/
│   ├── acceptance_targets.yaml
│   ├── agent_allowlist.yaml
│   ├── battery.yaml
│   ├── tariffs/
│   │   ├── anchored_tou.yaml
│   │   └── synthetic_high_spread.yaml
│   └── sensitivity_grid.yaml
├── databricks.yml                # Databricks Asset Bundle
├── resources/                    # bundle job, app, and pipeline definitions
├── src/edip/
│   ├── core/
│   │   ├── units.py
│   │   ├── features.py
│   │   ├── tariff.py
│   │   ├── optimizer.py
│   │   ├── settlement.py
│   │   ├── strategies.py
│   │   └── metrics.py
│   ├── data/                     # ingestion and cleaning jobs
│   ├── forecasting/              # training, quantiles, ONNX export
│   ├── replay/                   # rolling replay and sensitivity jobs
│   ├── agents/
│   │   ├── schemas.py
│   │   ├── prompts/              # versioned prompt files
│   │   ├── planning.py
│   │   ├── risk.py
│   │   ├── business.py
│   │   ├── tools.py
│   │   └── fallback.py
│   ├── workflow/                 # deterministic orchestration
│   ├── store/                    # Delta and Lakebase access
│   └── api/                      # FastAPI app
├── frontend/
│   ├── src/
│   │   ├── adapters/
│   │   │   ├── live.ts
│   │   │   ├── replay.ts
│   │   │   └── sandbox.ts
│   │   ├── views/
│   │   ├── components/
│   │   └── wasm/                 # onnxruntime web and highs js wrappers
│   └── public/data/              # frozen JSON for public builds
├── explainer/                    # public page two
├── evals/
│   ├── scenarios/                # 30 scripted agent scenarios
│   └── harness.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docs/
    ├── gates/                    # one report per gate
    └── architecture.drawio
```

## 5. Stage gates

Each gate lists its tasks, its required tests, and its exit checklist. Complete every checklist item before writing the gate report.

### Gate 0: Platform preflight

Tasks:
1. Create the Databricks Asset Bundle with dev and prod targets.
2. Create the Unity Catalog catalog `edip` with schemas `raw`, `curated`, `ml`, and `eval`.
3. Create an S3 bucket with versioning on, an IAM role, and a Unity Catalog storage credential and external location.
4. Provision a Lakebase instance and create the tables `scenarios`, `decision_runs`, `checkpoints`, `approvals`, and `agent_calls`.
5. Write `scripts/preflight.py`. The script calls the Foundation Model API endpoint `databricks-meta-llama-3-3-70b-instruct` with a sample Pydantic schema 20 times and records the valid JSON rate, median latency, and tokens.
6. Deploy a hello world Databricks App with FastAPI and OAuth and confirm that an authenticated request reaches it.
7. Set a workspace budget policy, auto stop on all SQL warehouses, and budget notifications.
8. Set up CI with Ruff, pytest, and a secret scan.

Exit checklist:
1. Every resource above exists and the preflight script output is saved in `docs/gates/gate0_preflight.json`.
2. The model returns valid structured output in at least 19 of 20 calls. If it does not, propose a replacement model and stop.
3. Lockfiles are committed and CI passes.

### Gate 1: Data (FR1 to FR7)

Tasks:
1. Download the UCI ElectricityLoadDiagrams20112014 file, store it in S3 under a dated prefix, and record its SHA256 hash and attribution.
2. Parse the semicolon separated file with comma decimals.
3. In `core/units.py`, convert each 15 minute reading (average kW) to interval kWh by dividing by 4. Aggregate to hourly mean kW and hourly kWh.
4. Detect and remove the zero placeholder rows on the March daylight saving days. Handle the collapsed October hour. Exclude each client's leading zeros before activation.
5. Select one client using a written completeness rule over the training period and record the rule and result.
6. Write chronological train, validation, and test partitions to Delta and record the boundary dates.
7. Encode the anchored tariff in `config/tariffs/anchored_tou.yaml` with the utility name, schedule name, effective date, source URL, energy rates by period, and demand charge. Encode the synthetic tariff and label it `synthetic: true`.

Required tests:
1. A unit test proves that four readings of 100 kW produce 100 kWh for the hour.
2. A unit test proves the daylight saving handling on a known March and October date.
3. A test proves that no timestamp in the test partition appears in train or validation.

Exit checklist:
1. `load_observations` exists in Delta with documented columns and units.
2. The data quality report lists row counts, removed rows, and the selected client.

### Gate 2: Forecasting (FR8 to FR13)

Tasks:
1. Build features in `core/features.py` using only data available before each decision time. Lags of 24 and 168 hours, rolling means shifted by at least 24 hours, hour of day, and day of week.
2. Implement the previous week seasonal baseline.
3. Train a LightGBM point model and three LightGBM quantile models (alpha 0.1, 0.5, 0.9), tuning only on the validation partition.
4. Produce 24 hour forecasts at each daily decision time across the test period.
5. Log all runs, parameters, and metrics to MLflow and register the models in Unity Catalog. Pin one version in `config/model_versions.yaml`.
6. Export each LightGBM model to ONNX and run a parity test on 1,000 rows.

Required tests:
1. A leakage test shifts the target forward and confirms that no feature correlates with future values beyond the decision time.
2. An ONNX parity test confirms a maximum absolute difference below 0.01 kW.

Exit checklist:
1. A forecast comparison table reports MAE and MAPE by forecast hour, peak hour error, P10 to P90 coverage, and pinball loss for all three forecasters.
2. ONNX files are saved for the public build.

### Gate 3: Dispatch and settlement (FR14 to FR21)

Before starting, write the acceptance targets into `config/acceptance_targets.yaml`, commit them, and stop for owner approval. Do not change them afterward.

Tasks:
1. In `core/optimizer.py`, build the mixed integer program with `scipy.optimize.milp` (HiGHS). Decision variables per hour: charge kW, discharge kW, state of charge kWh, grid import kW, a binary charge mode flag, and a peak variable for demand charge.
2. Enforce state of charge bounds, power limits, the binary that prevents simultaneous charge and discharge, round trip efficiency split between charge and discharge, terminal state of charge at or above the reserve, grid import at or above zero, and no export.
3. Objective: energy cost plus incremental demand charge above the running monthly peak plus degradation cost per kWh of throughput.
4. Implement the six strategies in `core/strategies.py`. The robust strategy plans on the P90 forecast during peak tariff hours and the P50 forecast otherwise. The hindsight strategy plans on actual load.
5. In `core/settlement.py`, replay each plan against actual load. Clip discharge to actual load in each hour, recompute state of charge, compute grid import, update the monthly peak, and carry the settled state of charge into the next day.
6. Run the rolling replay across complete billing periods in the test partition and write `dispatch_schedules`, `settlement_outcomes`, and `replay_outcomes`.

Required tests:
1. Property tests (Hypothesis) confirm that no settled schedule violates any physical constraint.
2. A test confirms that settlement clips a planned discharge of 50 kW against an actual load of 30 kW.
3. A test confirms that the no battery strategy bill equals the tariff applied to raw load.
4. A test confirms that hindsight regret is never negative.

Exit checklist:
1. A strategy comparison table shows settled bill, peak, throughput, degradation cost, violations, and regret for all six strategies.
2. Accepted constraint violations equal zero.

### Gate 4: Sensitivity (FR22 to FR23)

Tasks:
1. Define the grid in `config/sensitivity_grid.yaml`: peak to off peak spread multipliers, battery size at 25, 50, and 100 percent of observed peak kW, durations of 2 and 4 hours, demand charge rates, and degradation costs.
2. Run the replay for every grid cell as a Databricks job that uses small job compute.
3. Write `sensitivity_grid` and compute, for each strategy, the smallest spread at which it beats the fixed schedule.

Exit checklist:
1. A flip boundary chart is saved as a PNG and a JSON file for the public pages.
2. The gate report states the headline finding in one sentence with its numbers.

### Gate 5: Agents (FR24 to FR27)

Tasks:
1. Define Pydantic request and response schemas in `agents/schemas.py`. Every claim in a response carries an `evidence_ref` that points to a Delta table, row key, and column.
2. Write versioned prompts in `agents/prompts/`, one file per agent, with a version string logged on every call.
3. Implement the planning agent. It returns a typed `ScenarioChange` restricted to allowlisted fields. The workflow shows it to the operator and waits for confirmation.
4. Implement the risk agent. It may request only the predefined stress tests `forecast_error_injection`, `heat_week_replay`, and `reserve_floor_raise`. The workflow runs the chosen tests deterministically and passes results back for one interpretation.
5. Implement the business decision agent. It reads the sensitivity grid, stress results, and frozen acceptance targets and returns proceed, revise, or withhold with citations.
6. Enforce one model call per agent per workflow, a request deadline, and the no blind retry rule.
7. Validate every response. A validator rejects any number that does not match the cited evidence row. On rejection or failure, `agents/fallback.py` produces a deterministic template summary.
8. Wrap all calls in MLflow tracing.
9. Write 30 scenarios in `evals/scenarios/`, each with inputs, the correct recommendation, and the risks that must be found. Include scenarios that try to make agents change hard constraints.
10. Run `evals/harness.py` on the numbers only path and the agent assisted path and write `agent_evaluations`.

Required tests:
1. A test confirms that a planning response that changes a hard constraint is rejected.
2. A test confirms that a fabricated number triggers the fallback.
3. A test confirms that a simulated timeout produces no second call.

Exit checklist:
1. The evaluation report shows supported claim rate, citation accuracy, stress test selection accuracy, prohibited action refusals, recommendation accuracy for both paths, and cost per run.
2. Recorded traces for every scenario are exported as sanitized JSON for the sandbox.

### Gate 6: Live app

Tasks:
1. Build the FastAPI backend with endpoints for scenarios, decision runs, approvals, strategy results, sensitivity, and agent briefs. Enforce operator and viewer roles on the server.
2. Persist runs, checkpoints, approvals, and agent call records in Lakebase.
3. Build the React app with the four views from PRD section 4.1 and the `live` adapter.
4. Show provenance, units, evaluation period, and measured versus assumed labels on every view.
5. Deploy through the bundle to Databricks Apps.

Required tests:
1. Playwright tests cover login, the full decision flow, approval persistence, and the viewer role blocked from approving.

Exit checklist:
1. The deployed app completes one full decision run end to end.

### Gate 7: Public delivery and teardown

Tasks:
1. Build the `sandbox` adapter. Load the frozen 90 day JSON and the seeded synthetic generator, run the ONNX quantile models with onnxruntime web, and solve schedules with highs js in a web worker.
2. Serve recorded agent traces by scenario key, and show the template summary labeled as a template when no recording exists.
3. Add the permanent sandbox banner from PRD section 4.2.
4. Build the explainer page with the video, clickable architecture diagram, animated decision walkthrough, screenshots, trace excerpts, results, sensitivity map, and recommendation.
5. Add a CI job that fails the build if any public bundle contains a workspace URL, token pattern, or email address.
6. Deploy both pages to GitHub Pages at separate paths.
7. Export all results, then tear down the app, Lakebase, jobs, warehouses, and S3 resources that cost money. Keep the final exports in the repository or a release asset.
8. Open both pages after teardown and confirm every feature still works.

Required tests:
1. A Playwright test runs against each public page with the network blocked except for static assets.
2. A parity test confirms that the in browser optimizer matches the Python optimizer on 20 saved cases within 0.5 percent of cost.

Exit checklist:
1. Both pages pass their tests after teardown.
2. The README states the headline finding, links both pages and the video, and lists assumptions and limitations.

## 6. Gate report format

Write each report to `docs/gates/gateN.md` with these sections:

1. Gate and date.
2. What was built, with requirement IDs.
3. Test results with counts.
4. Key numbers, each linked to the table or file that holds it.
5. Deviations from the PRD and why.
6. Open questions for the owner.
7. Exit checklist with each item marked pass or fail.

End the report with the line `Awaiting approval to start Gate N+1.` and stop.

## 7. How to work inside a gate

1. Read the PRD section and the requirement IDs for the gate.
2. Write the Pydantic schemas and tests first.
3. Implement the smallest piece that makes one test pass, then the next.
4. Run Ruff and the full test suite before each commit.
5. Run Databricks jobs through the bundle, never through manual notebook runs that leave no record.
6. Log every model, metric, and artifact to MLflow with the dataset hash and config hash as tags.
