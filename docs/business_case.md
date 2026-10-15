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
