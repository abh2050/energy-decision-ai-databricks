# Energy Decision Intelligence Platform

Should a facility run a forecast-driven battery schedule? This project compares six battery
scheduling strategies on a year of real electricity load. Three bounded AI agents
interpret the operator's objective, challenge the risks, and draft the brief, and the
operator decides. It was built on Databricks, then exported and torn down; the two public
pages below run without any cloud backend.

- **Working sandbox:** <https://abh2050.github.io/energy-decision-ai-databricks/sandbox/>. The pinned forecaster (ONNX in onnxruntime web) and the battery optimizer (HiGHS in highs js) run in your browser on 90 days of the real load; agent responses are recorded from the live system.
- **System explainer:** <https://abh2050.github.io/energy-decision-ai-databricks/explainer/>. It includes the demo video, a clickable architecture diagram, a decision walkthrough, screenshots, MLflow trace excerpts, and results.
- **Demo video:** a three-minute captioned recording of the live app: [frontend/public/media/demo.webm](frontend/public/media/demo.webm).
- **Results export:** every Delta table and the live app's operational state ([release `results-2026-10-15`](https://github.com/abh2050/energy-decision-ai-databricks/releases/tag/results-2026-10-15)).

## Headline finding

**Do not buy a battery for this load profile.** On PG&E B-19 at published rates, the
guarded robust strategy (planning peaks on the P90 forecast) beats having no battery at
every battery size tested, from +3,198 to +37,363 USD per year before capital cost. No
size recovers its installed cost within 15 years at the mid NREL ATB cost; the best case
is a 30.8 year payback with an NPV of −829,491 USD. On PGE Schedule 85, nothing
forecast-driven beats no battery at base costs. Every battery size breaches at least one
stress limit.

**If a battery already exists, run robust dispatch and fix the maximum demand guard
before a pilot.** For the base battery (50 percent of the 751.8 kW training peak, 2
hours), the deterministic verdicts are: frozen rule **revise**; with amendment A1 (dated,
stricter) **revise**. Sources: [docs/business_case.md](docs/business_case.md),
[docs/gates/](docs/gates/).

## What it does

1. **Data:** real load for one client (UCI ElectricityLoadDiagrams20112014, client MT_189),
   billed on PG&E B-19 and PGE Schedule 85 tariffs encoded from the official sheets.
2. **Forecasting:** LightGBM point and P10, P50, P90 quantile models with conformal
   calibration (test P10 to P90 coverage 80.5 percent).
3. **Dispatch and settlement:** a daily mixed integer program per strategy (no battery,
   fixed schedule, seasonal forecast, ML forecast, robust quantile, hindsight), settled
   against actual 15 minute load with tariff billing demand and a charge guard.
4. **Sensitivity and stress:** 540 grid cells and three predefined stress tests.
5. **Agents:** planning (typed scenario change, quoting the operator), risk (chooses stress
   tests), business (restates the deterministic verdict). One call each, every number
   and comparison validated against evidence rows, template fallback.
6. **Live app:** FastAPI and React on Databricks Apps, with operator and viewer roles and
   Lakebase state. It was deployed, tested end to end, and then torn down.

## Assumptions

All assumed values are labelled "assumed" in the UI:
- **Battery:** size is set relative to the training peak; 90 percent round-trip efficiency,
  a 10 to 90 percent state of charge window, and a 50 percent terminal reserve.
- **Costs:** degradation 0.03 USD per kWh discharged; operating cost 4,868 USD per year.
- **Capital:** NREL ATB 2025 installed cost, a 15 year life, and an 8 percent discount
  rate.
- **Stress tests:** forecast errors doubled, a heat week of 1.10 times load, and a 30
  percent reserve floor.
- **Tariffs:** savings are before tax; PGE Schedule 108 is applied as a 1.015 multiplier;
  fixed charges and percentage taxes are excluded.

## Limitations

- **One client, one test year (2014),** with no weather data. The forecasters are trained
  once and not refit.
- **The revised strategy is post-hoc.**
  - It was designed after the pre-registered strategies lost money; its settings were
    tuned on 2013 under a charge-guard defect that has since been corrected, and they
    were not retuned.
  - Charging can still set a new monthly maximum demand under the guard's month-start
    limit (business case note 10).
- **Agents.** On 10 held-out scenarios, the agent-assisted path tied the numbers-only
  baseline at 90 percent recommendation accuracy, and supported claims were 92.9 percent
  against the 95 percent target. The live app's MLflow traces did not upload from
  Databricks Apps (network), although call records were kept in Lakebase.
- **Scenario evidence for the agent evaluation is scripted** (labelled), partly from the
  corrected replay.
- **The sandbox's own schedules are simplified:** they are settled hourly in the browser,
  without 15 minute billing or the charge guard. The results views show the full
  replay.

## Repository

- [docs/PRD.md](docs/PRD.md): requirements.
- [CLAUDE.md](CLAUDE.md): build instructions.
- [docs/gates/](docs/gates/): one report per stage gate.
- [src/edip/](src/edip/): Python (core, data, forecasting, replay, agents, workflow, store, API).
- [frontend/](frontend/): the React app (live, sandbox, explainer), with Playwright tests in `e2e` and `e2e-public`.
- [evals/](evals/): 30 development and 10 held-out agent scenarios, with the harness.

Data: Trindade, A. (2015). ElectricityLoadDiagrams20112014. UCI Machine Learning
Repository. https://doi.org/10.24432/C58C86 (CC BY 4.0).
