# Energy Decision Intelligence Platform PRD

Oct 13, 2026 · Owner: project owner

## 1. Problem and business question

The product tells a facility energy manager when a battery should charge, discharge, or hold, and whether forecast driven scheduling beats simpler scheduling by enough to justify a controlled pilot. The headline output is the boundary where the recommendation flips between proceed, revise, and withhold across tariff spread, battery size, and demand charge rate.

| Role | Person | What they need |
|---|---|---|
| Primary user | Facility energy or operations manager | A daily schedule they can approve, revise, or reject, with the reasoning visible |
| Economic sponsor | Finance or sustainability leader | Incremental savings net of battery wear, cloud, and review costs |
| Product owner | AI product or program lead | Evidence that each added capability earns its cost, plus pilot criteria |

The application recommends schedules and records operator decisions. It does not control equipment, trade electricity, or execute payments.

## 2. Goals, non goals, and success metrics

The project succeeds when it produces a defensible proceed, revise, or withhold recommendation backed by measured evidence, whatever that recommendation turns out to be.

Goals

1. Measure the incremental value of optimization, ML forecasting, and uncertainty aware planning separately.
2. Locate the tariff and battery conditions under which forecast driven dispatch pays off.
3. Show that bounded agents improve recommendation quality on a scripted evaluation set without inventing evidence.
4. Ship an authenticated Databricks App plus two public GitHub Pages experiences that keep working after the cloud resources are torn down.

Non goals

1. Equipment control, grid export, energy trading, or payments.
2. Weather inputs, multiple sites, multiple batteries, or multiple organizations.
3. A study with real operators. The project uses a scripted scenario set instead.

| Metric | Target set before testing |
|---|---|
| Accepted physical constraint violations | 0 |
| ML dispatch savings over fixed schedule | Reported with the tariff spread at which it turns positive |
| Quantile interval coverage (P10 to P90) | Within 5 points of 80 percent on the test period |
| Agent claims supported by cited evidence | At least 95 percent |
| Correct recommendation on the 30 scenario set | Agent assisted beats numbers only |
| Public pages working after teardown | Both pages verified |

## 3. Functional requirements

Every numerical result is computed deterministically and persisted before any agent reads it.

### 3.1 Data

1. FR1. Ingest UCI ElectricityLoadDiagrams20112014 into a dated snapshot in a Unity Catalog volume (Databricks-managed storage) with attribution and SHA256 hashes; Delta versioning keeps every table version.
2. FR2. Select one client by training period completeness and record the selection rule.
3. FR3. Convert each 15 minute reading (average kW) to interval energy by dividing by 4, then aggregate to hourly kW and kWh.
4. FR4. Remove zero placeholder rows on March daylight saving days, handle the collapsed October hour, and exclude pre activation zeros.
5. FR5. Split chronologically into train, validation, and test partitions. No feature may use information after its decision time.
6. FR6. Load three tariffs. Primary anchored tariff: PG&E Schedule B-19, secondary voltage. Low spread case: Portland General Electric Schedule 85 (201 to 4,000 kW), secondary voltage, Cost of Service Option, with every adjustment schedule that Schedule 100 applies to Schedule 85. Stress case: a labelled synthetic tariff that holds B-19 off-peak fixed and multiplies the summer peak to off-peak gap, in both seasons multiplies the peak and part-peak gaps to off-peak (off-peak fixed), swept over multipliers 1.0, 1.5, 2.0, and 3.0. For each real tariff and adjustment schedule, record from the official sheet the source URL, SHA256, sheet number, advice letter number, effective date, seasons, period definitions, energy rates, and demand charges. Savings include every per kWh and per kW charge, plus PGE Schedule 108 as a 1.015 multiplier on modeled variable charges, and exclude only fixed monthly customer charges and percentage taxes or franchise fees; all savings are reported before tax, and the provenance panel lists the exclusions. Load is stored and optimized in UTC; tariff periods are assigned from the Europe/Lisbon wall-clock hour.
7. FR7. Display that the load comes from Portuguese clients between 2011 and 2014, that the tariffs are American, and that tariff hours follow the Lisbon wall clock.

### 3.2 Forecasting

1. FR8. Build a previous week seasonal baseline.
2. FR9. Train a LightGBM point model on lagged load, shifted rolling features, hour, and day of week.
3. FR10. Train LightGBM quantile models at P10, P50, and P90.
4. FR11. Produce a 24 hour forecast at each decision time. Report error by forecast hour, peak hour error, and interval coverage.
5. FR12. Register models in Unity Catalog through MLflow and pin one version per replay.
6. FR13. Export models to ONNX and record a parity check against the Python model in MLflow.

### 3.3 Dispatch

1. FR14. Solve a 24 step mixed integer program (24 UTC hours per horizon) with SciPy milp and HiGHS.
2. FR15. Enforce state of charge bounds, power limits, no simultaneous charge and discharge, efficiency losses, a terminal reserve, and no export.
3. FR16. Compute six strategies under equal physical constraints: no battery, fixed schedule, seasonal forecast dispatch, ML forecast dispatch, robust quantile dispatch (P90 load in peak hours), and hindsight optimum.
4. FR17. Include time of use energy charges and, when configured, monthly demand charges over complete billing periods with a running peak.

### 3.4 Settlement

1. FR18. Replay each plan against actual load after each planning day.
2. FR19. Clip any planned discharge that exceeds actual load in that hour.
3. FR20. Carry the settled state of charge into the next day and update the monthly peak from realized grid draw. Billing demand uses each utility's interval (15 minutes for B-19, 30 minutes for PGE), built from 15 minute actual load minus the hourly battery output held flat within the hour. PGE Facility Capacity gets 12 months of history by seeding the months before the first billed month with no-battery Demand.
4. FR21. Compute bill, peak, throughput, degradation cost, and regret against hindsight from settled values only.

### 3.5 Sensitivity

1. FR22. Run the full replay across a grid of tariff spread, battery size (25, 50, and 100 percent of observed peak kW), duration (2 and 4 hours), demand charge rate, and degradation cost.
2. FR23. Write results to the Delta table sensitivity_grid and compute the boundary where each strategy starts to win.

### 3.6 Agents

The three agents share one Foundation Model API endpoint. Each agent makes at most one model call per workflow, receives a limited evidence packet, and returns a Pydantic validated response.

| Agent | Work it performs | Allowed tools |
|---|---|---|
| Planning | Translates a plain language objective into a typed scenario change for operator confirmation | Read settings; propose change; request allowlisted comparison after confirmation |
| Risk | Chooses stress tests (forecast error injection, heat week replay, reserve floor raise), reads results, and lists unresolved risks | Inspect validated plans; run predefined stress tests |
| Business decision | Reads the sensitivity grid and stress results and drafts proceed, revise, or withhold with row citations | Read verified economics, assumptions, and pilot criteria |

1. FR24. The workflow runs in this order: operator request, planning proposal, operator confirmation, forecast, optimization, settlement and validation, risk challenge, business recommendation, operator decision.
2. FR25. Agents cannot change hard constraints, invent numbers, approve recommendations, or operate equipment.
3. FR26. A failed or invalid agent response falls back to a deterministic template summary. Numerical results stay usable.
4. FR27. MLflow tracing records every agent call, tool request, prompt version, latency, token usage, and failure.

## 4. Experience

One React component tree serves three surfaces through three data adapters, and every surface shows its mode label, data provenance, units, evaluation period, and which values are measured versus assumed.

### 4.1 Live app (Databricks Apps, authenticated)

| View | Contents |
|---|---|
| Operating workspace | Load forecast with P10 to P90 band, battery state of charge, proposed schedule, approve or revise controls |
| Strategy comparison | Bill, peak, throughput, degradation, regret, and constraint checks for all six strategies |
| Agent decision brief | Planning interpretation, risk findings, business recommendation, linked evidence rows |
| Pilot business case | Sensitivity map with flip boundaries, assumptions, stress results, final recommendation |

The server enforces operator and viewer roles. Approvals, revisions, and checkpoints persist in Lakebase.

### 4.2 Public page one: working sandbox (GitHub Pages)

The sandbox runs the real forecasting and optimization in the browser with no backend.

1. A frozen 90 day slice of the selected client's real load ships as static JSON. A seeded synthetic generator adds unlimited extra days and is labeled synthetic.
2. onnxruntime web runs the exported LightGBM quantile models.
3. highs js, the WebAssembly build of HiGHS, solves the battery schedule live when the user changes battery size, tariff, or reserve.
4. Agent responses come from traces recorded on the live Databricks system, keyed by scenario. Scenarios without a recording show the deterministic template summary, labeled as a template.
5. A permanent banner states: "Sandbox mode: model and optimizer run locally in your browser; agent responses are recorded from the live system."

### 4.3 Public page two: system explainer (GitHub Pages)

1. The three to four minute demo video sits at the top.
2. A clickable architecture diagram explains what runs in each layer and why.
3. An animated walkthrough steps through one decision run from operator request to operator decision.
4. Real screenshots and MLflow trace excerpts come from the live app.
5. Strategy results, the sensitivity map, agent evaluation scores, and the final pilot recommendation close the page.

## 5. Architecture and technology stack

A serverless Databricks workspace on AWS (us-east-1) hosts the data, models, agents, and live app, using Databricks-managed storage only; GitHub Pages hosts the two public pages that outlive the cloud resources.

| Layer | Selection |
|---|---|
| Cloud and storage | Databricks serverless on AWS; Databricks-managed storage (Unity Catalog volumes and Delta tables) |
| Access | Unity Catalog permissions and Databricks OAuth; no customer AWS account |
| Data platform | Databricks serverless on AWS, Databricks Jobs |
| Analytical storage | Delta Lake with Unity Catalog |
| Forecasting | Python 3.12, LightGBM, pandas, NumPy, scikit-learn, onnxmltools |
| Optimization | SciPy optimize.milp with HiGHS |
| Experiment lifecycle and tracing | MLflow 3 with tracing |
| Agent inference | Databricks Foundation Model APIs, initial target databricks-meta-llama-3-3-70b-instruct after a structured output preflight |
| Model client | Databricks SDK, databricks-openai |
| Backend | FastAPI, Uvicorn, Pydantic 2 |
| Operational state | Lakebase PostgreSQL, psycopg 3 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Recharts |
| Live hosting and auth | Databricks Apps with OAuth |
| Browser runtime (sandbox) | onnxruntime web, highs js |
| Testing | pytest, Ruff, Playwright |
| Public hosting | GitHub Pages, two URLs |

Delta tables: load_observations, forecast_features, forecast_predictions, dispatch_schedules, settlement_outcomes, replay_outcomes, sensitivity_grid, agent_evaluations.

Lakebase tables: scenarios, decision_runs, checkpoints, approvals, agent_calls.

Each decision links the dataset hash, model version, tariff and battery assumptions, optimizer settings, prompt versions, and MLflow run and trace IDs. No Kubernetes, vector database, separate web hosting, or agent framework is used.

## 6. Evaluation and pilot acceptance criteria

The team freezes all acceptance targets in a committed file before the first test run, and a favorable result is never assumed.

| Area | Measures |
|---|---|
| Forecasting | MAE and MAPE by forecast hour, peak hour error, P10 to P90 coverage, pinball loss |
| Operating decisions | Settled bill, monthly peak, throughput, degradation cost, constraint violations, regret against hindsight |
| Sensitivity | Flip boundary for each strategy versus fixed schedule |
| Agents | Supported claims, citation accuracy, stress test selection, prohibited action refusals, inference cost per run |

Agent evaluation set. Thirty scripted scenarios each carry a known correct recommendation and known risks. The harness runs every scenario through the numbers only interface and the agent assisted interface and compares accuracy and justification quality.

Pilot acceptance criteria

1. ML or robust dispatch beats fixed scheduling by a preset margin under the anchored real tariff.
2. Accepted physical constraint violations equal zero.
3. Downside under each predefined stress test stays within a preset limit.
4. The operator can see, override, and revise every recommendation.
5. Every agent recommendation cites supporting evidence.

The final recommendation may conclude that fixed scheduling suffices, that ML pays off only under some tariffs, or that the agents have not earned their cost.

## 7. Risks, cost controls, and stage gates

The build moves through eight gates, and no gate opens until the previous gate's exit evidence is committed.

| Risk | Mitigation |
|---|---|
| Savings driven by chosen assumptions | Real anchored tariff, battery sized to observed peak, sensitivity grid as headline |
| Forecast error hidden from savings | Settlement against actual load (FR18 to FR21) |
| Model unavailable or weak structured output | Preflight at Gate 0; record any replacement model before evaluation |
| Databricks spend | Budget policy, auto stopping compute, small scheduled jobs, dated teardown; notifications are not hard caps |
| Paid call timeouts | Explicit deadlines, no blind retry, template fallback |
| Public build leaks | No credentials, identities, or live endpoints in Pages builds; CI secret scan |

| Gate | Name | Exit evidence |
|---|---|---|
| 0 | Platform preflight | Workspace, Unity Catalog catalog and schemas, Lakebase, model structured output, and Apps verified; lockfiles committed |
| 1 | Data | Governed Delta tables, unit and daylight saving tests passing, chronological splits |
| 2 | Forecasting | Three forecasters compared in MLflow, ONNX parity passed, model version pinned |
| 3 | Dispatch and settlement | Six strategies, constraint tests, settlement tests, rolling replay complete |
| 4 | Sensitivity | sensitivity_grid populated, flip boundary chart produced |
| 5 | Agents | Tracing, fallback, allowlist tests, 30 scenario evaluation scored |
| 6 | Live app | Authenticated app, operator approval flow persisted in Lakebase, Playwright suite passing |
| 7 | Public delivery | Sandbox and explainer live, video recorded, cloud resources torn down, both pages verified after teardown |
