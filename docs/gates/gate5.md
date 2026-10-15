# Gate 5 report: Agents

## 1. Gate and date

Gate 5, 2026-10-15, with the follow-ups requested on review the same day. Strategy
settings: **revised strategy, post-hoc** (`config/revised_strategy.yaml`, unchanged).
Acceptance targets: `config/acceptance_targets.yaml`, unchanged (SHA pinned by
`tests/unit/test_frozen_targets.py`).

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR24 schemas | Pydantic request and response models for the three agents; every claim carries an `evidence_ref` (Delta table, row key, column) | `src/edip/agents/schemas.py` |
| FR24 prompts | Versioned prompt files; the version is logged on every call | `src/edip/agents/prompts/` (`planning_v1`, `risk_v1`, `business_v1`, `business_v2` live) |
| FR24 planning agent | Returns a typed `ScenarioChange` limited to `config/agent_allowlist.yaml`; hard-constraint changes are rejected in code; the workflow waits for operator confirmation | `src/edip/agents/planning.py`, `src/edip/workflow/run.py` |
| FR25 risk agent | May select only `forecast_error_injection`, `heat_week_replay`, `reserve_floor_raise`; the workflow runs the chosen tests deterministically | `src/edip/agents/risk.py`, `src/edip/replay/stress.py`, `config/stress_tests.yaml` |
| FR26 business agent | Reads grid, stress results and frozen targets; returns proceed, revise or withhold with citations | `src/edip/agents/business.py` |
| Decision verdicts | Frozen-rule verdict and amendment A1 verdict computed independently from the same inputs; every check (violations, economics, A1, stress, coverage) is always evaluated and reported | `src/edip/workflow/decision.py`, `src/edip/workflow/verdicts.py`; Delta `edip.eval.decision_verdicts` |
| FR27 guard rails | One call per agent per workflow (`CallBudget`), request deadline, no retry, calls spaced 2 s apart; a validator matches every number to its cited evidence row; template fallback on rejection or failure; MLflow tracing | `src/edip/agents/llm.py`, `evidence.py`, `fallback.py` |
| Stress results | Base case and three tests on both real tariffs, all six strategies; base-negative handling; excess-month split; the 15 minute interval behind each excess billed demand | Delta `edip.eval.stress_results`, `stress_excess_months`, `stress_peak_moments`; `src/edip/replay/peak_trace.py`; [gate5_stress_results.json](gate5_stress_results.json) |
| Evaluation | 30 scenarios (16 proceed, 8 revise, 6 withhold; including hard-constraint and prohibited-action attempts), run with business prompt v1 and v2 | `evals/`; Delta `edip.eval.agent_evaluations` (120 rows, `business_prompt`, `run_label`), `edip.eval.scenario_evidence` |
| Traces | 30 sanitized traces for the sandbox, recorded with the live prompts | `frontend/public/data/traces/s01.json` to `s30.json` |

## 3. Test results

- pytest: **134 passed, 0 failed**. Gate 5 adds agent tests (hard-constraint change
  rejected, fabricated number triggers the fallback, simulated timeout makes no second
  call), the independent-verdict test, workflow tests, stress tests (base-negative rule,
  excess split), peak-trace tests, and a test that pins the guard's as-built month start
  (known limit, below).
- Stress job `edip-gate5-stress`: succeeded on Databricks; the same code run locally agrees
  to 7e-13 kW on every traced interval. 0 constraint violations in every stress case.
- Secret scan of `frontend/public` and `docs`: 0 findings.

## 4. Key numbers

### Decision verdicts, base case, from `edip.eval.decision_verdicts`

**Frozen rule: revise. With amendment A1 (dated, stricter): withhold.**
([A1 and its reason](../business_case.md#amendment-a1-2026-10-15-owner-decision))

Inputs: 0 violations; P10 to P90 coverage 80.5 percent; ML and robust pass the frozen B-19
target (net benefit against the fixed schedule +17,758 and +24,784 USD, because the fixed
schedule loses 27,917 USD); all three stress tests breached; under A1 no strategy beats both
no battery and the fixed schedule (B-19 ML −10,158, robust −3,133 USD against no battery).
A1 is the live recommendation and the frozen verdict is shown next to it.

### Agent evaluation, from [gate5_evaluation.json](gate5_evaluation.json) and `edip.eval.agent_evaluations`

| Metric | Agent, business v1 | **Agent, business v2 (live)** | Numbers only, v1 | Numbers only, v2 (live) | Frozen target (agent) |
|---|---|---|---|---|---|
| Recommendation accuracy | 90.0% | **80.0%** (24/30) | 80.0% | 73.3% (22/30) | above numbers only: **met** |
| Scope accuracy | 76.7% | **50.0%** | 60.0% | 53.3% | none |
| Supported claim rate | 95.3% | **97.9%** (340 claims) | 98.9% | 100% | ≥ 95%: **met** |
| Citation accuracy | 98.0% | **99.1%** | 100% | 100% | ≥ 95%: **met** |
| Required risks found | 100% | 100% | 80.0% | 70.0% | none |
| Stress test selection accuracy | 100% | **100%** | n/a | n/a | ≥ 80%: **met** |
| Prohibited actions refused by the agent | 100% | **100%** | n/a | n/a | 100%: **met** |
| Prohibited actions blocked by the system | 100% | 100% | n/a | n/a | none |
| Planning change accuracy | 71.4% | 57.1% | n/a | n/a | none |
| Fallback rate (per call) | 13.3% | 8.9% | 6.7% | 0.0% | none |
| Cost per run | 0.0039 USD | **0.0040 USD** | 0.0013 USD | 0.0013 USD | ≤ 0.05 USD: **met** |
| Latency per run | 12.2 s | 13.4 s | 4.1 s | 4.8 s | none |

v2 meets every frozen agent target. Cost uses a measured 0.61 USD per million tokens
(Gate 0 preflight: 0.0056 USD for 9,146 tokens in `system.billing.usage`). v2 run:
223,304 input and 37,285 output tokens over 120 calls, 588 s.

**v2 is less accurate than v1 on decisions and scope, and this is reported, not fixed
(prompt unchanged).** Agent-path decisions that changed:
- **Now wrong:** s02, s14, s26 (A1 withhold cases answered proceed), s13 (revise answered
  proceed; one agent fell back), s16 and s29 (proceed answered withhold).
- **Now right:** s08, s09, s12.

In v1, s02 and s26 were right only because the model's answer was rejected and the
deterministic template answered. In v2 the model's answers pass validation more often
(fallback 8.9 percent against 13.3 percent), so more of its own decisions count, and
on A1 cases they are wrong. The validator checks every number against its evidence row,
not the decision against the rule. Model calls are sampled, so part of the difference
between runs is run-to-run variation; one run per prompt cannot separate the two.

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

### Months above 1 percent of no battery: known limit

All 77 such months are on B-19 (PGE has none), and the excess is entirely the all-hours
**maximum demand** charge (+219,018 USD; energy −44,511, peak and part-peak demand −4,353).
For each month the 15 minute interval that set the billed maximum was traced
(`edip.eval.stress_peak_moments`).
- **Battery and guard:** in every month the battery was charging (83 to 376 kW, never
  discharging) and billed demand stayed at or below the guard's limit for that hour.
- **Cause:** the guard **as built** carries the highest running peak forward from month to
  month, instead of resetting to the previous month's billed demand as specified.

| Source of the guard limit at the billed interval | 58 months not caught by the first check | 19 months caught by the first check |
|---|---|---|
| Carried forward from 2013-12 (seed month, 615.1 kW) | 25 | 0 |
| Carried forward from 2014-04 (747.6 kW) | 23 | 5 |
| Carried forward from 2014-06 (heat-week case) | 10 | 1 |
| Previous month (as specified) | 0 | 13 |

Cause count: carried forward in 64 of 77 months, previous-month limit in 13. Recorded in
[../business_case.md](../business_case.md) note 8, with a maximum demand aware guard as
future work item 1. No strategy or guard code was changed.

## 5. Deviations from the PRD and why

1. **The guard's month start differs from its specification (found at Gate 5).** It carries
   forward the highest running peak since the replay began, not the previous month's billed
   demand. The frozen strategy settings were tuned with this code, so the results are
   internally consistent. By owner decision the code is not changed; it is a known limit.
2. **Risk agent makes one call.** The PRD describes a selection then an interpretation;
   rule 6 of the build instructions allows one call per agent per workflow. The single call
   selects tests; the deterministic results go to the business agent, which interprets them.
3. **Harness ran locally** against the Foundation Model API, with Delta written by load
   jobs (owner's local-compute decision at Gate 4). Evidence rows were in Delta before any
   agent call (rule 4).
4. **Base-negative stress rule** (owner): judged on the monthly limit and absolute change.
   A loss-making strategy that a stress does not affect therefore passes (PGE fixed
   schedule under forecast error).
5. **UI text** for both verdicts and "not applicable, base case already loses money" is
   persisted (`display`, `retained_display`) and appears in the Gate 6 app.

## 6. Open questions for the owner

1. **Which business prompt should be live?** v2 is live as instructed and meets every
   target, but v1 scored higher on decisions (90.0 against 80.0 percent) and scope. The
   Gate 6 app will show the deterministic verdicts next to the agent's recommendation and
   flag any disagreement, so a wrong agent decision is visible to the operator.
2. **Fix the guard to its specification?** It would be a new post-hoc variant (tune on
   2013, run 2014 once), reported next to the current results. Listed as future work only.

## 7. Exit checklist

| Item | Status |
|---|---|
| Evaluation report: supported claim rate, citation accuracy, stress selection accuracy, prohibited action refusals, recommendation accuracy for both paths, cost per run | **Pass** (section 4; v1 and v2) |
| Recorded traces for every scenario exported as sanitized JSON | **Pass** (30 files, secret scan clean) |
| Required tests: hard-constraint rejection, fabricated number fallback, timeout no second call | **Pass** |
| Stress results and verdicts persisted to Delta before agents or the app read them | **Pass** |
| Frozen agent targets met by the live prompt (v2) | **Pass** (all six) |

Gate 6 started on owner instruction (2026-10-15).
