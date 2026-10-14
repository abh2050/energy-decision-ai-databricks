# Pilot business case (working notes)

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
