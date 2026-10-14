# Gate 3 report: Dispatch and settlement

## 1. Gate and date

Gate 3, 2026-10-14. Acceptance targets frozen before the first replay
(`config/acceptance_targets.yaml`, SHA256 pinned by `tests/unit/test_frozen_targets.py`);
battery assumptions approved (`config/battery.yaml`).

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR14 MILP | 24 UTC hourly steps per day, SciPy `milp` with HiGHS | `src/edip/core/optimizer.py` |
| FR15 constraints | SOC bounds (10 to 90 percent), power limits, charge-mode binary (no simultaneous charge and discharge), efficiency split equally (sqrt of 90 percent round trip), terminal reserve 50 percent, grid import at or above zero, no export | `src/edip/core/optimizer.py`, `src/edip/core/battery.py` |
| FR16 six strategies | no battery, fixed schedule (owner rule), seasonal forecast, ML forecast, robust quantile (P90 in protected periods, P50 otherwise; forecaster version 2), hindsight | `src/edip/core/strategies.py` |
| FR17 tariff charges | Energy from the Lisbon-clock period of each UTC hour; demand charges as incremental cost above the running monthly peak per charge and local month; variable charge multiplier | `src/edip/replay/replay.py` |
| FR18 to FR21 settlement | Plan settled against actual load: discharge clipped to actual load, power, and energy above soc_min; charge clipped to power and room below soc_max; settled SOC carried; demand billed on 15 minute (B-19) and 30 minute (PGE) net load; PGE Facility Capacity seeded with 11 no-battery months | `src/edip/core/settlement.py`, `src/edip/core/billing_demand.py` |
| Replay | All 6 strategies on 6 tariffs (B-19, PGE, synthetic m1 to m3) across 2014; economics against the frozen targets | `src/edip/replay/replay_job.py`, `src/edip/replay/evaluate.py` |
| Delta | `edip.curated.dispatch_schedules`, `settlement_outcomes`, `replay_outcomes` (annual and monthly rows) | `resources/gate3_jobs.yml` |

## 3. Test results

- pytest: **103 passed, 0 failed**. New in Gate 3: dispatch 6, evaluation 2, frozen targets 2.
- Required tests:
  1. Property tests (Hypothesis): `test_property_settled_schedule_never_violates_constraints`
     (200 random plans, loads, and starting SOC) and
     `test_property_optimizer_plans_settle_without_violations`, **pass**. The first one
     found a real bug during development: settlement did not clip discharge to the power
     limit. Fixed before the replay.
  2. 50 kW planned discharge against 30 kW actual load settles at 30 kW:
     `test_settlement_clips_50_kw_discharge_to_30_kw_actual_load`, **pass**.
  3. No-battery bill equals the tariff applied to raw load (independent calculation of
     energy and the three B-19 demand charges on 15 minute load):
     `test_no_battery_bill_equals_tariff_applied_to_raw_load`, **pass**.
  4. Hindsight regret never negative: `test_hindsight_regret_is_never_negative`
     (Hypothesis, from the same starting state and running peaks), **pass**. In the
     replay, every strategy's annual regret is also at or above zero.
- Replay job: succeeded on the second run (the first failed writing a mixed-type column;
  the computation was moved into a pure `compute()` checked locally against Arrow).

## 4. Key numbers

From [gate3_results.json](gate3_results.json) and `edip.curated.replay_outcomes`. Full
tables for all six tariffs: [gate3_strategy_comparison.md](gate3_strategy_comparison.md).
Battery 375.9 kW / 751.8 kWh. USD per year, before tax.

**PG&E B-19 (anchored)**

| Strategy | Settled bill | Max billing demand kW | Throughput kWh | Net benefit (gross) | Net benefit after op. cost | Regret vs hindsight | Violations |
|---|---|---|---|---|---|---|---|
| No battery | 905,027 | 747.6 | 0 | 0 | 0 | 35,980 | 0 |
| Fixed schedule | 955,101 | 795.4 | 207,908 | −56,311 | −56,311 | 92,291 | 0 |
| Seasonal forecast | 960,229 | 1,026.8 | 124,811 | −58,946 | −63,814 | 94,925 | 0 |
| ML forecast | 959,138 | 1,026.8 | 121,710 | −57,762 | −62,630 | 93,742 | 0 |
| Robust quantile | 960,748 | 1,026.8 | 145,377 | −60,082 | −64,950 | 96,062 | 0 |
| Hindsight | 865,157 | 815.6 | 129,684 | 35,980 | 35,980 | 0 | 0 |

**PGE Schedule 85 (low spread)**: no battery 413,506; fixed −4,656; seasonal −6,361;
ML −5,867; robust −5,325 (net after operating cost); hindsight +11,154.

**Economics against the frozen targets** (ML and robust evaluated separately):

| Tariff | Strategy | Incremental over fixed (frozen reading) | Required | Pass | Incremental (single count) | Pass |
|---|---|---|---|---|---|---|
| B-19 | ML forecast | −6,319 | −5,631 and > 4,868 | **no** | −1,451 | **no** |
| B-19 | Robust quantile | −8,639 | −5,631 and > 4,868 | **no** | −3,771 | **no** |
| PGE | ML forecast | −1,211 | −466 and > 4,868 | **no** | 3,657 | **no** |
| PGE | Robust quantile | −669 | −466 and > 4,868 | **no** | 4,199 | **no** |

All four synthetic tariffs also fail. Total accepted constraint violations: **0**.

**Headline**: with the strategies as specified, no battery strategy that runs on a
forecast or a fixed rule saves money at this site; they lose 56,000 to 65,000 USD per
year on B-19 because demand charges rise. Perfect hindsight saves 35,980 USD per year on
B-19 and 11,154 USD on PGE, so the battery has value that the day-ahead strategies do not
capture.

**Why, from the settled data** (B-19, ML forecast): on 2014-06-16 at 13:00 Lisbon (summer
off-peak) the forecast was 478.8 kW, actual load was 671.5 kW, and the day-ahead plan
charged 317 kW, so grid draw reached 988.5 kW and set a new monthly maximum demand billed
at 37.37 USD per kW. In 117 of 718 charging hours, settled grid draw exceeded the
no-battery annual peak (747.6 kW). The fixed schedule's full-power night charging does
the same: 410.7 kW of load plus 375.9 kW of charging set an August peak of 795.4 kW.
Wider synthetic spreads make it worse (ML net −106,569 USD at m = 1.5), because the
optimizer cycles more and charges into more forecast errors.

Under the frozen decision rule, **the B-19 economics failure means withhold**, regardless
of the stress and coverage results still to come at Gate 5.

## 5. Deviations and why

1. **Terminal reserve applies to the optimizer strategies only.** The fixed schedule
   discharges to soc_min per the owner's rule; physical limits are identical for all six
   strategies. This disadvantages ML and robust dispatch, the conservative direction.
2. **The optimizer does not model PGE Facility Capacity** (a 12 month, two-peak ratchet).
   Settlement bills it exactly for every strategy.
3. **Planning is hourly; billing is 15 and 30 minute.** The optimizer plans charging up
   to the running hourly peak; intra-hour spikes then raise billed demand. Hindsight is
   affected too (815.6 kW billed versus 747.6 kW with no battery).
4. **Operating cost wording in the frozen file.** `savings_basis` subtracts the operating
   cost from ML and robust net benefit, and the economics target also requires the
   increment to exceed it. The official pass/fail uses that literal reading (rule 11); the
   single-count reading is reported alongside. Both fail.
5. **Fixed schedule charging hours.** "From 00:00 local in off-peak hours" is implemented
   as: from local midnight, charge at full power in off-peak or super off-peak hours
   before the first discharge hour, until soc_max.
6. **Serverless runtime.** The replay takes about 20 minutes on serverless compute versus
   about 1.5 minutes locally for the same code; relevant for the Gate 4 grid cost.

## 6. Open questions for the owner

1. **The strategies lose money because nothing stops charging from setting a new demand
   peak.** Options, all strategy definition changes (the frozen targets stay as they are):
   - a. **Charge guard at settlement** (applies to every strategy, no forecast needed):
     clip charging in each hour so settled grid draw stays at or below the month's
     running billed peak for that charge window. This is what a real site controller does.
   - b. **Plan charging on P90** in every hour (robust strategy only), so charging leaves
     room for forecast error.
   - c. **Fixed schedule charges at reduced power** spread over all off-peak hours instead
     of full power from midnight.

   Because the test year has now been seen, I recommend choosing among these on the
   validation half-year (2013-07 to 2013-12) only, freezing the choice, and then rerunning
   2014 once, reporting both the original and the revised results.
2. **Proceed to Gate 4 now or after question 1?** The sensitivity grid multiplies the
   replay (about 20 minutes per full run on serverless); running it on the current
   strategies would mostly map losses. My recommendation is to settle question 1 first.

## 8. Revised strategy, post-hoc (owner decision 2026-10-14)

The results in sections 3 and 4 are the **pre-registered** result and stay unchanged
(`dispatch_schedules`, `settlement_outcomes`, `replay_outcomes`, `gate3_results.json`).
The owner then approved two strategy changes, tuned on validation and run on 2014 once.

**Changes.** A settlement charge guard for all six strategies, including hindsight
(`src/edip/core/charge_guard.py`). It caps charging below the running peak of every
demand determinant in effect: B-19 maximum demand, peak period demand, and summer
part-peak demand (part-peak included as "every determinant in effect"; it only restricts
charging further); PGE window demand and Facility Capacity Demand. The cap uses the
smallest headroom across the hour's 15 minute intervals against actual load, starts each
month at the previous month's billed demand, reduces charging only, and records clipped
kWh. Days that end below reserve because of clipping are counted as guard shortfall days,
not violations. The robust strategy also plans demand on P50 + k x (P90 - P50).

**Tuning.** July to December 2013 only, local runs logged to the MLflow experiment
`/Shared/edip/gate3_revised_tuning` (7 trials; [gate3_revised_tuning.json](gate3_revised_tuning.json)).
Chosen: guard margin 0.02, k = 1.0 (plain P90). Frozen in
[config/revised_strategy.yaml](../../config/revised_strategy.yaml) before the 2014 rerun.
The local predictions file also held 2014 rows; the tuning script filters to validation
and asserts no 2014 hour is used.

**Rerun.** Databricks job `edip-gate3-replay-revised`, once, labelled "revised strategy,
post-hoc"; outputs in `*_revised` tables and [gate3_revised_results.json](gate3_revised_results.json).
Side by side: [gate3_revised_comparison.md](gate3_revised_comparison.md). Constraint
violations: 0. Solver failures: 0.

| Net benefit vs no battery, USD per year | B-19 pre | B-19 revised | PGE pre | PGE revised |
|---|---|---|---|---|
| Fixed schedule | −56,311 | −27,917 | −4,656 | −2,898 |
| Seasonal forecast | −63,814 | −11,953 | −6,361 | −4,507 |
| ML forecast | −62,630 | −10,624 | −5,867 | −4,250 |
| Robust quantile | −64,950 | −3,006 | −5,325 | −1,924 |
| Hindsight | 35,980 | 38,512 | 11,154 | 12,083 |

The guard removes every new demand peak: highest billed demand on B-19 falls from 1,026.8
kW to 747.6 kW, the no-battery level, for every strategy. Guard shortfall days (B-19):
seasonal 53, ML 49, robust 4, hindsight 3. On synthetic m3, robust dispatch is the only
non-hindsight strategy with a positive net benefit (8,543 USD).

**Economics against the frozen targets (revised).** B-19: ML and robust **pass** under
both readings (incremental over fixed 17,293 and 24,911 USD under the frozen reading).
PGE: ML fails both readings; robust fails the frozen reading (+975 USD, below the 4,868 USD
operating cost) and passes the single-count reading.

**Flag on the frozen target (rule 3: reported, not edited).** The economics target
compares ML and robust with the fixed schedule only. In the revised run the fixed schedule
loses 27,917 USD on B-19, so ML and robust pass while still losing 10,624 and 3,006 USD per
year against no battery. Read mechanically, the frozen decision rule gives "proceed,
scoped to B-19" (pending the Gate 5 stress and coverage checks), for strategies that do
not beat having no battery. I recommend the business case report net benefit against no
battery next to every pass, and that the owner decide whether a pilot recommendation can
rest on a pass against a loss-making baseline.

Tests added: charge guard 6 (month-start limit, 15 minute headroom, both B-19
determinants, part-peak, PGE Facility Capacity, settlement integration), P90 charge
planning 1. Suite: **110 passed**.

## 7. Exit checklist

| Item | Status |
|---|---|
| Strategy comparison table: settled bill, peak, throughput, degradation cost, violations, and regret for all six strategies | **Pass** ([gate3_strategy_comparison.md](gate3_strategy_comparison.md)) |
| Accepted constraint violations equal zero | **Pass** (0 across 36 tariff and strategy runs) |
| Required tests: property, clipping, no-battery bill, regret | **Pass** |
| Economics against the frozen targets (reported, not an exit item) | **Fail** on every tariff for ML and robust dispatch |

Gate 4 is on hold for the owner's review of the revised rerun. When it starts, the grid
runs as parallel tasks per tariff and battery size on small job compute.

Awaiting approval to start Gate 4.
