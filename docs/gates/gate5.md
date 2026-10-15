# Gate 5 report: Agents

## 1. Gate and date

Gate 5, 2026-10-15 (stress rerun and known-limit analysis 2026-10-14 workspace time).
Strategy settings: **revised strategy, post-hoc** (`config/revised_strategy.yaml`,
unchanged). Acceptance targets: `config/acceptance_targets.yaml`, unchanged (SHA pinned by
`tests/unit/test_frozen_targets.py`).

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR24 schemas | Pydantic request and response models for the three agents; every claim carries an `evidence_ref` (Delta table, row key, column) | `src/edip/agents/schemas.py` |
| FR24 prompts | Versioned prompt files; the version is logged on every call | `src/edip/agents/prompts/` (`planning_v1`, `risk_v1`, `business_v1`, `business_v2`) |
| FR24 planning agent | Returns a typed `ScenarioChange` limited to `config/agent_allowlist.yaml`; hard-constraint changes are rejected in code; the workflow waits for operator confirmation | `src/edip/agents/planning.py`, `src/edip/workflow/run.py` |
| FR25 risk agent | May select only `forecast_error_injection`, `heat_week_replay`, `reserve_floor_raise`; the workflow runs the chosen tests deterministically | `src/edip/agents/risk.py`, `src/edip/replay/stress.py`, `config/stress_tests.yaml` |
| FR26 business agent | Reads grid, stress results and frozen targets; returns proceed, revise or withhold with citations | `src/edip/agents/business.py`, `src/edip/workflow/decision.py` |
| FR27 guard rails | One call per agent per workflow (`CallBudget`), request deadline, no retry, calls spaced 2 s apart; a validator matches every number to its cited evidence row; template fallback on rejection or failure; MLflow tracing | `src/edip/agents/llm.py`, `evidence.py`, `fallback.py` |
| Stress results | Base case and three tests on both real tariffs, all six strategies; base-negative handling and the excess-month breakdown (owner instruction) | Delta `edip.eval.stress_results`, `edip.eval.stress_excess_months`; [gate5_stress_results.json](gate5_stress_results.json) |
| Evaluation | 30 scenarios (16 proceed, 8 revise, 6 withhold; including hard-constraint and prohibited-action attempts); harness for both paths | `evals/scenarios/`, `evals/harness.py`, `evals/summarize.py`; Delta `edip.eval.agent_evaluations`, `edip.eval.scenario_evidence` |
| Traces | 30 sanitized traces for the sandbox | `frontend/public/data/traces/s01.json` to `s30.json` |

## 3. Test results

- pytest: **130 passed, 0 failed**. Gate 5 adds agent tests (hard-constraint change
  rejected, fabricated number triggers the fallback, simulated timeout makes no second
  call), workflow tests, and stress tests (base-negative rule, excess split).
- Stress job `edip-gate5-stress`: first rerun failed because charge names with spaces were
  used as Delta column names; renamed to snake_case (`maximum_demand_usd`), second run
  succeeded. 0 constraint violations in every stress case.

## 4. Key numbers

### Evaluation (FR27), from [gate5_evaluation.json](gate5_evaluation.json) and `edip.eval.agent_evaluations`

| Metric | Agent-assisted | Numbers only |
|---|---|---|
| Recommendation accuracy | **90.0%** (27/30) | 80.0% (24/30) |
| Scope accuracy | 76.7% | 60.0% |
| Supported claim rate | 95.3% (295 claims) | 98.9% (95 claims) |
| Citation accuracy | 98.0% | 100% |
| Required risks found | 100% | 80.0% |
| Stress test selection accuracy | 100% | n/a |
| Prohibited actions refused by the agent | 100% | n/a |
| Prohibited actions blocked by the system | 100% | n/a |
| Planning change accuracy | 71.4% | n/a |
| Fallback rate (per call) | 13.3% (90 calls) | 6.7% (30 calls) |
| Tokens per run | 6,452 | 2,122 |
| Cost per run | **0.0039 USD** | 0.0013 USD |
| Latency per run | 12.2 s | 4.1 s |

Cost uses a measured 0.61 USD per million tokens (Gate 0 preflight: 0.0056 USD for 9,146
tokens in `system.billing.usage`). Whole evaluation: 222,824 input and 34,411 output
tokens over 120 calls, 501 s. Agent-assisted misses: s08 (business agent returned
withhold where proceed was correct), s09 and s12 (planning fallback, so the requested
change was not applied and the wrong cell was judged). Numbers-only misses are mostly
objective-change scenarios (25% correct), which it cannot act on by design.

### Stress tests, base battery, from `edip.eval.stress_results`

Net benefit against no battery, USD per year. Every ML and robust case starts negative, so
`retained_pct` is null with reason `base_negative` (displayed as "not applicable, base
case already loses money"); these cases are judged on the 1 percent monthly bill limit and
the absolute dollar change.

| Test | Tariff | ML: change / worst month | Robust: change / worst month | ML / robust pass |
|---|---|---|---|---|
| Forecast error x2 | B-19 | −3,488 / +3.8% | −13,327 / +6.9% | fail / fail |
| Heat week x1.10 | B-19 | −2,741 / +3.8% | −2,847 / +3.6% | fail / fail |
| Reserve floor 30% | B-19 | −971 / +4.1% | +897 / +2.1% | fail / fail |
| Forecast error x2 | PGE | −773 / 0.0% | −2,350 / 0.0% | fail / fail |
| Heat week x1.10 | PGE | −351 / +0.2% | −316 / +0.1% | fail / fail |
| Reserve floor 30% | PGE | +41 / 0.0% | −81 / −0.1% | **pass** / fail |

Unstressed: B-19 ML −10,158, robust −3,133; PGE ML −4,184, robust −2,076. Hindsight passes
every test.

### Months above 1 percent of no battery (owner instruction), from `edip.eval.stress_excess_months`

All 77 such months are on B-19; PGE has none. Across them the excess is entirely the
**all-hours maximum demand charge** (+219,018 USD); energy saves 44,511 USD and peak and
part-peak period demand save 4,353 USD. Facility Capacity does not apply to B-19.

| Case (base battery) | ML months | Robust months | Fixed months | Caused by the guard's month-start limit |
|---|---|---|---|---|
| Base | 2 (2,981 USD) | 3 (3,823 USD) | 8 (21,522 USD) | ML 1 of 2, robust 0 of 3 |
| Forecast error x2 | 3 | 4 | 8 | ML 2, robust 1 |
| Heat week | 4 | 3 | 9 | ML 1, robust 0 |
| Reserve floor | 4 | 2 | 9 | ML 1, robust 0 |

Overall the month-start limit caused 19 of 77 months. Recorded as a known limit in
[../business_case.md](../business_case.md) note 8; strategy settings not changed.

### Base-case decision

- **Frozen rule alone: revise.** ML and robust pass the frozen B-19 economics target
  (measured against the loss-making fixed schedule), there are no violations, and the stress
  tests fail.
- **Frozen rule with amendment A1 applied first (as built): withhold.** No strategy beats
  both no battery and the fixed schedule.

This differs from "withhold under both rules"; see open question 1.

## 5. Deviations from the PRD and why

1. **Risk agent makes one call.** The PRD describes a selection then an interpretation;
   rule 6 of the build instructions allows one call per agent per workflow. The single call
   selects tests; the deterministic results go to the business agent, which interprets them.
2. **Harness ran locally** against the Foundation Model API, with Delta written by the
   `gate5_load_evaluations` job (owner's local-compute decision at Gate 4). The evidence rows
   were loaded to Delta before any agent call (rule 4).
3. **Business prompt v2 after the evaluation.** The evaluation ran `business_v1`. `v2`
   adds A1 as step 3 and is now the live prompt; it has not been re-evaluated (another run
   costs about 0.16 USD).
4. **A1 ordering.** A1 is checked before the stress and coverage checks (owner's reading:
   a strategy that loses money cannot be revised into a pilot by stress fixes).
5. **Base-negative stress rule.** The 50 percent retention target is undefined for a
   negative base; per the owner, those cases are judged on the monthly limit and absolute
   change. A loss-making strategy that the stress does not touch therefore passes (PGE
   fixed schedule, forecast error test).
6. **"Not applicable" UI text.** Persisted as `retained_display` in the stress table; it
   will appear in the UI at Gate 6.

## 6. Open questions for the owner

1. **Base-case decision under the frozen rule.** The frozen rule by itself returns
   **revise**, not withhold; only the A1-first order returns withhold. Should the report
   and UI show both ("frozen rule: revise; with A1: withhold"), or only the A1 result?
2. **Re-evaluate with `business_v2`?** About 0.16 USD for 30 scenarios on both paths.
3. **Known limit.** Is recording the all-hours maximum demand excess enough for Gate 6, or
   should a strategy change be scoped later as a separately labelled post-hoc variant?

## 7. Exit checklist

| Item | Status |
|---|---|
| Evaluation report: supported claim rate, citation accuracy, stress selection accuracy, prohibited action refusals, recommendation accuracy for both paths, cost per run | **Pass** (section 4, `gate5_evaluation.json`) |
| Recorded traces for every scenario exported as sanitized JSON | **Pass** (30 files in `frontend/public/data/traces/`, secret scan clean) |
| Required tests: hard-constraint rejection, fabricated number fallback, timeout no second call | **Pass** |
| Stress results persisted to Delta before agents read them | **Pass** |

Awaiting approval to start Gate 6.
