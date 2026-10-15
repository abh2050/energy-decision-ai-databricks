# Pilot business case (working notes)

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
5. **Revised strategy, post-hoc (Gate 3).** With a settlement charge guard and P90 charge
   planning, tuned on July to December 2013 and run once on 2014: B-19 net benefit against
   no battery is ML −10,624 and robust −3,006 USD per year (hindsight +38,512). ML and
   robust pass the frozen target because it is measured against a fixed schedule that
   loses 27,917 USD; every pass must be shown next to net benefit against no battery.
6. **Sensitivity (Gate 4, revised strategy).** At B-19 published rates the guarded robust
   strategy beats no battery only with larger batteries (+3,602 USD per year at 50 percent
   of peak for 4 hours, +29,764 at 100 percent for 4 hours); nothing forecast-driven beats
   no battery on PGE. Net benefit excludes battery capital cost, which favours the largest
   battery; the pilot case must set annual savings against installed cost.
7. **Capital layer (evidence, not a gate; added 2026-10-15).** Installed cost from the
   NREL/NLR 2025 ATB commercial battery storage CAPEX for cost year 2026 (2023 dollars):
   low 207.7 USD/kWh + 487.1 USD/kW, mid 255.3 + 507.7, high 284.7 + 520.4 (derived from
   the 2 h and 4 h values). Life 15 years and discount rate 8 percent are ASSUMED; fixed
   O&M, replacement, and incentives are excluded. At the mid cost no non-hindsight strategy
   pays back within 15 years on either tariff; on B-19 the best case (robust dispatch, 100
   percent of peak, 4 hours) earns 28,281 USD per year against 1,149,297 USD installed: a
   40.6 year payback and an NPV of −907,229 USD. Full table:
   [business_case_capital.md](business_case_capital.md).
8. **Known limit: months billed above no battery (Gate 5, recorded 2026-10-14 and
   2026-10-15; no strategy changed, owner decision).** The frozen stress rule caps every
   month at 1 percent above the no-battery bill. On B-19 at the base battery, months that
   exceed it do so **entirely through the all-hours maximum demand charge**: across all 77
   such months in the base case and the three stress tests, maximum demand adds 219,018
   USD, while energy saves 44,511 USD and peak and part-peak period demand save 4,353 USD.
   Base case (unstressed): ML exceeds the limit in 2 months (2014-03 +1.5 percent, 2014-05
   +3.8 percent; 2,981 USD excess) and robust in 3 (2014-02 +1.4, 2014-03 +1.7, 2014-12
   +3.6 percent; 3,823 USD); the fixed schedule in 8 (worst +14.1 percent; 21,522 USD).
   PGE Schedule 85 has no month above the limit (worst +0.2 percent).

   **Cause.** For every excess month the 15 minute interval that set the billed maximum
   demand was traced, with the battery action, the guard's limit for that hour, and actual
   load (`edip.eval.stress_peak_moments`). In all 77 months the battery was **charging**
   (83 to 376 kW; never discharging) on top of actual load, and billed demand stayed at or
   below the guard's limit; in 47 of the 58 months below it equals the limit to 0.1 kW.
   The guard did what it was built to do; the limit itself was too high, because **as built
   the guard's month-start limit carries forward the highest running peak since the replay
   began**, not the previous month's billed demand as its specification and the Gate 3
   report state. A month whose own peak stays below its start value hands that start value
   on (pinned by `test_known_limit_month_start_carries_forward_the_higher_peak`).

   | Source of the guard limit at the billed interval | Months not flagged at first (58) | Months flagged as month-start (19) |
   |---|---|---|
   | Carried forward from 2013-12 (the seed month, 615.1 kW billed) | 25 | 0 |
   | Carried forward from 2014-04 (no-battery maximum 747.6 kW) | 23 | 5 |
   | Carried forward from 2014-06 (heat-week case only) | 10 | 1 |
   | The previous month (the limit as specified) | 0 | 13 |

   So 64 of the 77 months come from the carried-forward limit and 13 from the
   previous-month limit as specified. The first-pass check (19 months) compared billed
   demand with the previous month's *actual* billed demand, so it missed the carry-forward.
   Base case ML and robust: ML 2014-03 (limit from 2013-12), robust 2014-02 and 2014-03
   (2013-12) and 2014-12 (2014-04; 117.3 kW charge on a 537.1 kW interval billed 654.3 kW
   against 591.5 kW without a battery). The frozen strategy settings were tuned with this
   same guard code, so reported results are internally consistent; they understate what a
   guard built to its specification might achieve, which is untested. Sources:
   `edip.eval.stress_excess_months`, `edip.eval.stress_peak_moments`,
   [gates/gate5_stress_results.json](gates/gate5_stress_results.json).

## Decision verdicts (base case, revised strategy, post-hoc)

**Frozen rule: revise. With amendment A1 (dated, stricter): withhold.**
([A1 and its reason](#amendment-a1-2026-10-15-owner-decision))

Both verdicts are computed independently from the same persisted inputs
(`edip.eval.decision_verdicts`): no violations, coverage 80.5 percent, ML and robust pass
the frozen B-19 target (measured against a fixed schedule that loses 27,917 USD), all three
stress tests breached; under A1 no strategy beats both no battery and the fixed schedule.
A1 is stricter, so it is the live recommendation; the frozen verdict is always shown next
to it.

## Future work

1. **A maximum demand aware guard.** Reset the month-start limit to the previous month's
   actual billed demand (the specified rule), and limit charging against the facility's
   running maximum demand for the current month, so charging cannot set a new all-hours
   maximum. Any such change is a new post-hoc variant: tune on 2013, run 2014 once, and
   report it next to the pre-registered and current revised results.
2. Monthly retraining of the forecaster on a rolling window (note 1).
3. Re-evaluate the agents whenever a prompt changes, before it goes live.
