# Pilot business case (working notes)

## Recommendation

**Do not buy a battery for this load profile.** At published PG&E B-19 rates no battery
size recovers its installed cost within 15 years under any non-hindsight strategy (best
case: robust dispatch, 100 percent of peak for 4 hours, 30.8 year payback, NPV −829,491
USD at the mid ATB cost; note 8), and on PGE Schedule 85 nothing forecast-driven beats no
battery at base costs (note 7). Every battery size fails at least one stress limit
(decision verdicts below).

**If a battery already exists, run robust dispatch and fix the maximum demand guard before
a pilot.** Robust dispatch is the only non-hindsight strategy that beats no battery at every B-19
battery size (+3,198 to +37,363 USD per year before capital cost; note 7). The guard still
lets charging set a new monthly maximum demand under its month-start limit (note 10;
future work 1), and the frozen strategy settings (charge guard margin 0.02, robust P90
charge planning k 1.0) were tuned under the guard defect (note 5) and have not been
retuned with the corrected guard.


## Amendment A1, 2026-10-15 (owner decision)

**A pilot recommendation requires positive net benefit over no battery and over the fixed
schedule**, for the strategy and tariff named in the recommendation. Reason: the frozen
economics target (`config/acceptance_targets.yaml`, unchanged) measures ML and robust
dispatch only against the fixed schedule, and did not anticipate that the fixed schedule
itself would lose money. In the revised Gate 3 rerun, ML and robust passed that target on
B-19 while losing 10,624 and 3,006 USD per year against no battery. Under this amendment
such a pass cannot support a pilot recommendation. The frozen target is still evaluated
and reported as written.


The full business case is assembled at Gates 4 and 7 from persisted results. Notes that
must carry into it:

1. **Retraining.** The evaluation fits the forecasters once on 2012-01 to 2013-06 and
   holds them fixed through the 2014 test year (no refit on train plus validation, owner
   decision at Gate 2). A production system would retrain monthly on a rolling window,
   so measured forecast error is likely pessimistic for later test months.
2. **Savings basis.** All savings are reported before tax. PGE Schedule 108 is applied as
   a 1.015 multiplier on modelled variable charges; fixed customer charges and
   percentage taxes or franchise fees are excluded.
3. **Forecast uncertainty.** The P10 to P90 band is calibrated with conformalized
   quantile regression on October to December 2013, months that were also used to tune
   the models (model version 2).
4. **Gate 3 result (strategies as first specified).** On PG&E B-19, every forecast-driven
   strategy and the fixed schedule lost 56,000 to 65,000 USD per year against no battery,
   because day-ahead charging set new demand peaks; perfect hindsight saved 35,980 USD.
   Any revised strategy must be reported next to this result.
5. **Result sets (owner decision 2026-10-15).** Three labelled sets are kept:
   **pre-registered** (Gate 3 strategies as first specified, note 4); **revised strategy,
   post-hoc (guard defect)** (superseded; Delta tables with the suffix `_guard_defect`,
   files in [results/guard_defect/](results/guard_defect/)); and **revised strategy,
   post-hoc (corrected guard)**, the revised result. Both revised sets use the same frozen
   settings (charge guard margin 0.02, robust P90 charge planning k 1.0, tuned on July to
   December 2013 with the defective guard and not retuned); only the guard's month start
   differs.
6. **Revised result, 2014, base battery** (corrected guard; Delta
   `edip.curated.replay_outcomes_revised`, [gates/gate3_revised_results.json](gates/gate3_revised_results.json)).
   Net benefit against no battery on B-19: robust **+5,645 USD per year**, ML −3,159,
   fixed schedule −14,727, hindsight +40,201 (guard defect set: robust −3,006, ML −10,624,
   fixed −27,917). On PGE: robust −2,235, ML −4,175, fixed −2,845. ML and robust pass the
   frozen B-19 target; neither passes on PGE.
7. **Sensitivity (corrected guard; `edip.eval.sensitivity_grid`).** At B-19 published
   rates and base costs, robust dispatch beats no battery at all six battery sizes (+3,198
   at 25 percent of peak for 2 hours to +37,363 at 100 percent for 4 hours) and in 83.3
   percent of all B-19 grid cells (guard defect: 25.9 percent). ML beats no battery only
   at 100 percent for 4 hours (+4,477; 11.1 percent of B-19 cells). On PGE nothing
   forecast-driven beats no battery at base costs (best: robust −1,275 at 50 percent for 4
   hours). Net benefit excludes battery capital cost.
8. **Capital layer (evidence, not a gate; corrected guard).** Installed cost from the
   NREL/NLR 2025 ATB commercial battery storage CAPEX for cost year 2026 (2023 dollars):
   low 207.7 USD/kWh + 487.1 USD/kW, mid 255.3 + 507.7, high 284.7 + 520.4. Life 15 years
   and discount rate 8 percent are ASSUMED; fixed O&M, replacement, and incentives are
   excluded. At the mid cost no non-hindsight strategy pays back within 15 years; the best
   case (robust, 100 percent of peak, 4 hours) earns 37,363 USD per year against 1,149,297
   USD installed: a 30.8 year payback and an NPV of −829,491 USD (guard defect: 40.6 years,
   −907,229). Full table: [business_case_capital.md](business_case_capital.md).
9. **Guard defect and its correction.** As first built, the charge guard started each month
   at the highest running peak since the replay began instead of the previous month's
   billed demand, so a high peak (the December 2013 seed, April 2014) was carried forward.
   Under that defect 77 months (base case and stress tests, B-19 base battery) billed more
   than 1 percent above no battery, 64 of them from the carried-forward limit. The guard was
   corrected on 2026-10-15 to its specification (test:
   `test_month_start_is_previous_months_billed_demand_over_three_months`); no strategy
   setting changed.
10. **Known limit after the correction.** With the corrected guard, 37 months (base case
   and stress tests, B-19 base battery) still bill more than 1 percent above no battery,
   all through the all-hours maximum demand charge (+111,822 USD; energy −19,909, peak
   period demand −858), and **all 37 come from the specified month-start limit**: the
   previous month's billed demand is above this month's no-battery maximum, and charging
   fills up to it (in 31 of 39 traced intervals billed demand equals the limit to 0.1 kW;
   charge 33 to 376 kW, never discharge). Base case: ML in 2014-05 (+3.8 percent), the fixed
   schedule in 3 months; robust in none. Robust exceeds only under stress (forecast error:
   2014-02 and 2014-11; reserve floor: 2014-02). Sources: `edip.eval.stress_excess_months`,
   `edip.eval.stress_peak_moments`, [gates/gate5_stress_results.json](gates/gate5_stress_results.json).

## Decision verdicts (base case, revised strategy, post-hoc, corrected guard)

**Frozen rule: revise. With amendment A1 (dated, stricter): revise.**
([A1 and its reason](#amendment-a1-2026-10-15-owner-decision))

Both verdicts are computed independently from the same persisted inputs
(`edip.eval.decision_verdicts`): no violations, coverage 80.5 percent, ML and robust pass
the frozen B-19 target, robust qualifies under A1 on B-19 (+5,645 USD against no battery,
+20,372 against the fixed schedule), and all three stress tests are breached on B-19
(robust: forecast error −10,028 USD and a worst month of +3.9 percent; heat week −7,850 USD,
retaining −39 percent; reserve floor retains 54.9 percent but its worst month is +1.3
percent). Under the guard defect the verdicts were frozen rule revise, A1 withhold.

By battery size (`edip.eval.cell_verdicts`; frozen / A1): 25 percent of peak, 2 and 4
hours: withhold / withhold (B-19 economics target not met); 50 and 100 percent, 2 and 4
hours: revise / revise (stress limits breached).

## Future work

1. **A maximum demand aware guard.** The month-start reset to the previous month's billed
   demand is done (2026-10-15). What remains (note 10): limit charging against this
   month's own running maximum demand rather than last month's, so charging cannot set a
   new all-hours maximum when this month's load is lower. Any such change is a new post-hoc variant: tune on 2013, run 2014 once, and
   report it next to the pre-registered and current revised results.
2. Monthly retraining of the forecaster on a rolling window (note 1).
3. Re-evaluate the agents whenever a prompt changes, before it goes live.
