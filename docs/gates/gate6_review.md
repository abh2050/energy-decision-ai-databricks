# Gate 6 review follow-ups (before Gate 7)

## 1. Gate and date

Gate 6 review, 2026-10-15. Gate 7 not started. Result set reported here: **revised
strategy, post-hoc (corrected guard)**, unless labelled otherwise. Frozen strategy settings
and acceptance targets are unchanged.

## 2. What was done

| Request | Done | Files and tables |
|---|---|---|
| Guard starts each month at the previous month's billed demand | `ChargeGuard` tracks each month's settled billed demand and starts the next month there (before: the running peak, which carried the highest peak forward) | `src/edip/core/charge_guard.py` |
| Three-month test | Month 2's peak (500 kW) falls below month 1's (760 kW); month 3 starts at 500 kW | `tests/unit/test_charge_guard.py::test_month_start_is_previous_months_billed_demand_over_three_months` |
| Three labelled result sets | `pre-registered` (unchanged), `revised strategy, post-hoc (guard defect)` (16 Delta tables copied to `*_guard_defect` and relabelled; files in `docs/results/guard_defect/`), `revised strategy, post-hoc (corrected guard)` (now the revised result in the original tables) | `src/edip/core/labels.py`, `src/edip/eval/archive_job.py` |
| Reruns on the corrected guard | 2014 replay (Databricks job), 540-cell grid (local, then the aggregate job), stress tests and both verdicts, all 6 app cells, capital layer, app snapshot | `edip.curated.*_revised`, `edip.eval.sensitivity_grid`, `stress_*`, `decision_verdicts`, `cell_*`; `docs/business_case_capital.*`, `docs/gates/gate3_revised_results.json`, `gate4_flip_boundary.*`, `gate5_stress_results.json` |
| Business prompt v3 | Receives both deterministic verdicts; drafts explanation, scope, and evidence; the validator rejects any recommendation that differs from the A1 verdict | `src/edip/agents/prompts/business_v3.md`, `src/edip/agents/business.py`, `evidence.check_business(required_decision=...)` |
| Typed comparison claims | `Comparison` (two evidence references, or one and a constant, plus an operator); the validator evaluates each and rejects false ones, and rejects comparative words (higher, lower, exceeds, beats, ...) in plain claims. Planning and risk prompts v2 describe it | `src/edip/agents/schemas.py`, `evidence.check_comparisons`, `prompts/planning_v2.md`, `risk_v2.md` |
| Regression test for the deployed error | "The ml_forecast strategy has a higher net savings" citing 17,758 against robust's 24,784: rejected as untyped, and rejected as a false typed comparison | `tests/unit/test_comparisons.py` |
| Evaluation v1, v2, v3 | 30 scenarios, both paths, each prompt; scenario numbers once copied from guard-defect results now come from the corrected cells | `evals/`, `evals/corrected_cells.json`; Delta `edip.eval.agent_evaluations` (180 rows), [gate6_evaluation.json](gate6_evaluation.json) |
| Viewer-only service principal | `edip-viewer-e2e`: workspace-access entitlement and CAN_USE on the app only; its OAuth secret is deleted right after a one-hour token is issued | `scripts/viewer_principal.py` |
| Sandbox traces | Re-recorded from the corrected system for every prompt; **not yet copied to the sandbox** (section 6) | `evals/results/traces_business_v1/`, `_v2/`, `_v3/` |

## 3. Test results

- pytest: **146 passed, 0 failed** (adds the three-month guard test, a zero-demand month
  test, 5 comparison and v3 tests; the guard-defect pinning test was replaced).
- Playwright, synthetic snapshot (CI and local): **6 passed**.
- **Deployed app, viewer service principal:** viewer blocked in the UI and on the server
  (403 on approve and on create scenario), and provenance on every view: **2 passed**.
  Without the workspace-access entitlement the Apps proxy redirected the principal to
  sign-in; with it, `/whoami` returns role `viewer`.
- 2014 replay and grid: 0 constraint violations. Secret scan: 0 findings.

## 4. Key numbers

### Corrected guard against guard defect (B-19, base battery, USD per year against no battery)

| Strategy | Guard defect | Corrected guard |
|---|---|---|
| Fixed schedule | −27,917 | **−14,727** |
| ML forecast | −10,624 | **−3,159** |
| Robust quantile | −3,006 | **+5,645** |
| Hindsight | +38,512 | **+40,201** |

Source: `edip.curated.replay_outcomes_revised` and `_guard_defect`. PGE: robust −2,235, ML
−4,175 (little change).

- **Grid** (`edip.eval.sensitivity_grid`): robust beats no battery at all 6 B-19 sizes at base costs (+3,198 to +37,363), and in 83.3 percent of B-19 cells (guard defect: 25.9 percent). ML only at 100 percent for 4 hours (+4,477). Nothing forecast-driven on PGE at base costs.
- **Capital** (mid ATB): best case robust 100 percent / 4 h, 30.8 year payback, NPV −829,491 USD. No non-hindsight strategy pays back in 15 years.
- **Months above 1 percent of no battery** (B-19 base battery, base case and stress tests): 37 (guard defect: 77). All 37 come from the specified previous-month limit; none is carried forward. Base case: robust 0 months, ML 1, fixed 3.

### Verdicts (`edip.eval.decision_verdicts`, `cell_verdicts`)

- **Base case: Frozen rule: revise. With amendment A1 (dated, stricter): revise.** (Guard defect: revise / withhold.)
  - Robust now qualifies under A1 on B-19.
  - All three stress tests are breached by robust. Forecast error: −10,028 USD, worst month +3.9 percent. Heat week: retains −39 percent. Reserve floor: retains 54.9 percent, but worst month +1.3 percent.
- **By battery:** 25 percent of peak (2 and 4 hours) withhold / withhold, because the B-19 target is not met. 50 and 100 percent revise / revise.
- No battery size reaches proceed.

### Agent evaluation, corrected system ([gate6_evaluation.json](gate6_evaluation.json))

| Metric (agent-assisted unless noted) | v1 | v2 (live) | v3 | Frozen target |
|---|---|---|---|---|
| Recommendation accuracy | 90.0% | 76.7% | 86.7% | above numbers only |
| Numbers-only accuracy | 80.0% | 76.7% | 80.0% | |
| Agent beats numbers only | met | **not met (tie)** | met | |
| Supported claim rate | **88.3%** | **89.3%** | **90.3%** | ≥ 95% |
| Citation accuracy | 95.8% | 96.4% | 97.0% | ≥ 95% |
| Prohibited actions refused by the agent | **80%** | 100% | 100% | 100% |
| Stress test selection accuracy | 100% | 100% | 100% | ≥ 80% |
| Cost per run | 0.0048 USD | 0.0048 USD | 0.0052 USD | ≤ 0.05 USD |
| Scope accuracy | 73.3% | 56.7% | 80.0% | none |
| Fallback rate (per call) | 28.9% | 22.2% | 33.3% | none |
| Meets every frozen agent target | no | no | **no** | |

- **v3 is not live: it misses the supported claim rate (90.3 against 95 percent).** As
  instructed, v3 is not live and the prompt was not changed. The live business prompt
  remains v2, which now misses two targets (supported claims, and agent beats numbers
  only, a 76.7 percent tie).
- **v3 decisions:** v3 never returned a recommendation that differs from the A1 verdict.
  Its four misses (s09, s12, s13, s16) are objective-change scenarios where the planning
  step fell back or applied the wrong change, so the verdict for the wrong battery was
  copied.
- **Why supported claims fell for every prompt** (Gate 5: v1 95.3, v2 97.9 percent), from
  validator rejection reasons in the MLflow traces of the v3 run:
  - 24 untyped comparisons (the new rule);
  - 11 citations of rows not in the packet;
  - 11 uses of "85" (the 80 ± 5 coverage bound, a frozen-target constant, not an
    evidence row);
  - 6 false typed comparisons.

  v1 and v2 show the same pattern.
- **Your "80.0 vs 80.0" note:** the earlier v2 run (guard defect) was 80.0 percent for the
  agent against **73.3** percent for numbers only, so it met that target. The 80.0
  numbers-only figure was v1's. On the corrected system, v2 does miss it (76.7 against
  76.7).
- Evaluation tokens: v1 270,412 in / 40,466 out; v2 270,894 / 40,864; v3 283,235 / 56,729.
  Each run made 120 calls, about 0.5 USD in total at 0.61 USD per million tokens.

## 5. Deviations and why

1. **Frozen settings were tuned with the defective guard and not retuned.** Retuning would
   be another post-hoc step, so it was not done.
2. **Scripted scenarios.** The corrected results have no A1-only withhold case and no
   robust-only case, so those two patterns are scripted round numbers. Every pattern once
   copied from real results now uses the corrected cells. The decision mix is unchanged
   (16 proceed, 8 revise, 6 withhold).
3. **Comparative words in plain claims are rejected.** This is what catches the deployed
   error, and it is also the largest cause of the fall in supported claims.
4. **Sandbox traces are recorded but not published** while no prompt meets every target
   (section 6).

## 6. Open questions for the owner

1. **Supported claim rate.** No prompt meets 95 percent with the new comparison rule. Which
   of these, if any?
   - Treat frozen-target constants (80 ± 5) as citable rule values.
   - Revise v3 or planning/risk to type every comparison (a new prompt version and a new
     evaluation).
   - Accept the miss and keep the agents advisory with the deterministic verdicts shown.
2. **Live business prompt.** v2 is live and now misses two targets; v3 misses one and
   never contradicts the A1 verdict. Should v3 go live despite the supported claim miss,
   or should v2 stay live?
3. **Sandbox traces.** Which run's traces (v2 live, or v3) should the sandbox show?
4. **Planning errors** now account for every v3 decision miss. Should the planning agent's
   proposed change also be checked against the operator's objective, or is operator
   confirmation enough?

## 7. Checklist

| Item | Status |
|---|---|
| Guard corrected, three-month test | **Pass** |
| 2014 replay, grid, stress tests, both verdicts rerun; three labelled result sets | **Pass** |
| v2 target result recorded | **Pass**: corrected system, agent beats numbers only not met (76.7 vs 76.7); the earlier "80.0 vs 80.0" did not match the stored data (section 4) |
| Business prompt v3, verdict check | **Pass** |
| Typed comparisons, false-comparison check, regression test | **Pass** |
| Evaluation v1, v2, v3 on corrected results | **Pass** (reported) |
| v3 live only if every frozen target is met | **Not live**: misses supported claim rate (90.3 vs 95). Stopped here as instructed. |
| Viewer service principal, viewer blocking test on the deployed app | **Pass** |
| Sandbox traces re-recorded from the corrected system | **Recorded, not published** (open question 3) |

Gate 7 not started; awaiting your decisions above.

## 8. Final configuration (owner decision 2026-10-15, second review)

Business prompt **v3 is live**, with planning prompt **v3** and the corrected validator.
- **Planning v3:** named v3 because planning-v2 (typed comparisons) already existed; v3
  keeps that rule and adds quotes. Each change quotes the operator request. The
  validator rejects a quote missing from the request, a quote that names no keyword of the
  field (`config/planning_keywords.yaml`), or a field outside the map.
- **Citable targets:** every numeric value in `config/acceptance_targets.yaml` is a citable
  row (`config.acceptance_targets`, 14 values plus the derived coverage bounds 75 and 85;
  the file is unchanged).
- **Format violations:** comparative words in plain claims are reported as format
  violations and stay rejected in the live app.
- **Held-out scenarios:** 10 (`evals/scenarios/h01` to `h10`: objective change 4,
  adversarial 3, scope 3) were committed in `96972aa` before the run.
- **The run:** done once, on all 40 scenarios (Delta `edip.eval.agent_evaluations`, label
  `business_v3+planning_v3 (final, live)`; [gate6_final_evaluation.json](gate6_final_evaluation.json)).

| Metric (agent-assisted unless noted) | Development, 30 (optimistic: prompts and validator were shaped on these) | Held-out, 10 | Frozen target |
|---|---|---|---|
| Recommendation accuracy | **96.7%** | **90.0%** | above numbers only |
| Numbers-only accuracy | 80.0% | 90.0% | |
| Agent beats numbers only | met | **not met (tie)** | |
| Supported claim rate, original definition (outside-packet citations and false comparisons unsupported) | **99.1%** | **92.9%** | ≥ 95% |
| Supported claim rate, stricter definition (format violations also unsupported) | 98.0% | 90.2% | (reported only) |
| Format compliance (claims without comparative words) | 98.9% | 97.3% | (reported only) |
| Citation accuracy | 100% | 100% | ≥ 95% |
| Prohibited actions refused by the agent | **80%** | 100% | 100% |
| Prohibited actions blocked by the system | 100% | 100% | |
| Stress test selection accuracy | 100% | 100% | ≥ 80% |
| Scope accuracy | 96.7% | 90.0% | |
| Planning change accuracy | 85.7% | 75.0% | |
| Fallback rate per call | 15.6% | 16.7% | |
| Cost per run | 0.0060 USD | 0.0062 USD | ≤ 0.05 USD |

- **Targets not met:**
  - Development: prohibited-action refusal, 80 percent. In s26 the planning agent
    proposed lowering the economics target; the validator rejected it and the system
    blocked it.
  - Held-out: supported claims, 92.9 percent. Of 112 claims, 8 were unsupported, in h06,
    h07, h08, and h10.
  - Held-out: agent beats numbers only, a tie at 90.0 percent.
- **Errors:** the only wrong recommendations are s09 and h01, both from a planning
  change; v3 copied the verdict for the cell it was given.
- **Run size:** 476,877 input and 57,807 output tokens over 160 calls, about 0.33 USD.

**Deployed app, final configuration:** Playwright passed 5 tests, and 1 was skipped
(login, handled by the Apps proxy). The passing tests covered the full flow with
approval persistence, revise, reject, and viewer blocking (viewer service principal),
plus provenance on every view. All three deployed runs recorded `planning-v3`,
`risk-v2`, `business-v3`. Planning fell back in all three runs, because the model again
proposed switching to ML. It claimed "ML > robust" against the fixed schedule (11,568
against 20,372 USD), and its quote ("Reduce demand charges ...") does not name a
strategy. The validator rejected both and the template answered.

**Sandbox traces:** the 40 traces from this run (s01 to s30, h01 to h10) replace all
earlier traces in `frontend/public/data/traces/`; no other traces are published.
