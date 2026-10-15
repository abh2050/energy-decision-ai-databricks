# Gate 4 report: Sensitivity

> **Superseded numbers (2026-10-15).** Revised-strategy results in this report were produced with the charge guard defect and are now labelled "revised strategy, post-hoc (guard defect)". The corrected results are in [gate6_review.md](gate6_review.md).

## 1. Gate and date

Gate 4, 2026-10-14 to 2026-10-15. Strategy settings: **revised strategy, post-hoc**
(`config/revised_strategy.yaml`: settlement charge guard, margin 0.02; robust P90 charge
planning, k = 1.0). The pre-registered Gate 3 result is unchanged.

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR22 grid | 540 cells, each a full 2014 replay of all six strategies: B-19 spread family (gap multiplier 1.0 = B-19, 1.5, 2.0, 3.0) and PGE Schedule 85; battery power 25, 50, 100 percent of the training peak (751.8 kW); duration 2 and 4 hours; round-trip efficiency 85 and 90 percent; degradation 0.02, 0.03, 0.05 USD per kWh; demand charge rates x0.5, x1.0, x1.5; assumed operating cost 4,868 USD per year | `config/sensitivity_grid.yaml`, `src/edip/replay/grid.py` |
| Demand rate scaling | Every demand charge and Facility Capacity rate scaled together | `src/edip/core/tariff.py` (`scale_demand`) |
| FR23 boundaries | For each strategy and battery cell: smallest spread multiplier at which it beats the fixed schedule (FR23) and at which it beats no battery | `src/edip/core/sensitivity.py` |
| Outputs | Delta `edip.eval.sensitivity_grid` (3,240 rows); flip boundary JSON and PNG for the public pages | `src/edip/replay/grid_job.py`, `src/edip/replay/charts.py`, `frontend/public/data/sensitivity/` |
| Execution | 15 slices (tariff x power fraction) in 10 local processes, 1,933 s wall time; Databricks job `edip-gate4-aggregate` wrote the Delta table and outputs and logged to MLflow `/Shared/edip/gate4_sensitivity` | `scripts/run_grid_local.py`, `resources/gate4_jobs.yml` |
| Speed | Tariff calendar computed once per replay instead of per day: results identical to the previous code (maximum bill difference 0.00 USD on the same machine), about 2.4 times faster | `src/edip/replay/replay.py` |

## 3. Test results

- pytest: **113 passed, 0 failed**. New in Gate 4: sensitivity 3 (flip boundary, never,
  demand scaling).
- Grid: 540 cells, **0 constraint violations**, 0 solver failures.
- Aggregate job: succeeded on its first run.

## 4. Key numbers

From `edip.eval.sensitivity_grid` and [gate4_flip_boundary.json](gate4_flip_boundary.json);
chart [gate4_flip_boundary.png](gate4_flip_boundary.png). Net benefit is against no
battery, USD per year before tax, after degradation and, for forecast-driven strategies,
the assumed operating cost. **It does not include battery capital cost** (PRD net benefit
definition), so larger batteries are favoured.

**Headline**: on PG&E B-19 at published rates, the guarded robust strategy beats having no
battery only with larger batteries (+3,602 USD per year at 50 percent of peak for 4 hours,
+1,615 at 100 percent for 2 hours, +29,764 at 100 percent for 4 hours; −2,165 at the 50
percent, 2 hour base case), ML dispatch only with the largest battery (+3,926), no
forecast-driven strategy beats no battery on PGE at any size (best: robust −1,121), and
perfect hindsight would earn 22,882 to 83,279 USD per year on B-19.

**Base costs (90 percent efficiency, 0.03 USD per kWh, demand rates x1.0), net benefit
against no battery:**

| Tariff | Battery | Fixed | ML | Robust | Hindsight |
|---|---|---|---|---|---|
| B-19 | 25% / 2 h | −1,383 | −15,118 | −1,461 | 22,882 |
| B-19 | 25% / 4 h | 6,786 | −11,868 | −3,132 | 36,880 |
| B-19 | 50% / 2 h | −27,917 | −10,624 | −2,165 | 39,342 |
| B-19 | 50% / 4 h | −20,934 | −6,847 | 3,602 | 56,361 |
| B-19 | 100% / 2 h | −27,249 | −9,520 | 1,615 | 54,887 |
| B-19 | 100% / 4 h | −21,944 | 3,926 | 29,764 | 83,279 |
| PGE | 25% / 2 h | −1,465 | −4,062 | −2,460 | 9,623 |
| PGE | 50% / 4 h | −5,804 | −4,528 | −1,121 | 13,117 |
| PGE | 100% / 4 h | −7,112 | −4,740 | −3,011 | 8,248 |

**Share of the 108 battery and cost cells where each strategy beats no battery:**

| Tariff | Fixed | Seasonal | ML | Robust | Hindsight |
|---|---|---|---|---|---|
| B-19 (spread x1.0) | 14.8% | 5.6% | 5.6% | 31.5% | 100% |
| Spread x1.5 | 33.3% | 14.8% | 13.9% | 41.7% | 100% |
| Spread x2.0 | 49.1% | 22.2% | 22.2% | 50.0% | 100% |
| Spread x3.0 | 77.8% | 47.2% | 48.1% | 84.3% | 100% |
| PGE | 0.0% | 0.0% | 0.0% | 11.1% | 100% |

**Flip boundaries** (smallest spread multiplier, over 108 battery and cost cells):

| Strategy | Beats no battery at x1.0 / x1.5 / x2.0 / x3.0 / never | Beats fixed at x1.0 / never |
|---|---|---|
| Seasonal forecast | 6 / 11 / 9 / 25 / 57 | 61 / 46 (1 more at x1.5) |
| ML forecast | 6 / 11 / 8 / 27 / 56 | 59 / 47 (1 each at x1.5, x2.0) |
| Robust quantile | 34 / 19 / 11 / 29 / 15 | 79 / 29 |
| Hindsight | 108 / 0 / 0 / 0 / 0 | 108 / 0 |

**Frozen-target pass rates** (strict reading, share of cells): B-19 ML 49.1 percent,
robust 66.7 percent; PGE ML 11.1 percent, robust 25.0 percent. Many of these passes are
against a loss-making fixed schedule (Gate 3, section 8).

## 5. Deviations and why

1. **Grid slices ran locally (owner decision).** On serverless the grid was estimated at
   about 19 compute hours (25 to 30 USD) against a 5 USD alert. The 15 slices ran in local
   processes on the same Delta inputs (fetched by `scripts/fetch_tables.py`); a Databricks
   job wrote the Delta table and outputs. The workspace is serverless-only, so "small job
   compute" maps to serverless tasks; the parallel `edip-gate4-grid` job is defined but
   not run.
2. **Cross-platform solver differences.** Local and Databricks runs of the same cell can
   pick different, equally good MILP plans: the base cell's robust net benefit is −2,165
   USD locally and −3,006 USD in the Databricks revised rerun; hindsight 39,342 versus
   38,512. The Gate 3 revised rerun remains the record for the base cell.
3. **Synthetic m1 not rerun.** It is identical to B-19 (Gate 3), so B-19 is the x1.0 point.
4. **Demand charge multipliers 0.5, 1.0, 1.5** were proposed at Gate 4 and approved.
5. **No battery capital cost.** Net benefit follows the PRD definition (wear, cloud, review);
   a pilot decision needs the battery's installed cost against these annual figures.

## 6. Open questions for the owner

1. **Capital cost.** Should the business case add an assumed installed cost (USD per kWh
   and per kW) and a payback or annualized cost? Without it the grid favours the largest
   battery.
2. **Decision baseline** (from Gate 3): should pilot scope rest on beating no battery, the
   fixed schedule, or both?

## 8. Follow-ups after approval (2026-10-15)

**Deterministic optimizer.** HiGHS through SciPy `milp` now runs single-threaded with a
fixed random seed (0), a relative MIP gap of 1e-6, and a throughput tie-break of 1e-7 USD
per kWh on charge plus discharge (at most 0.66 USD a year for the largest grid battery;
never billed). The base cell rerun on Databricks (Linux aarch64) and locally (Darwin arm64)
agrees within **0.01 USD per bill** across all 12 tariff and strategy bills (limit 10 USD).
The deterministic plans differ slightly from the earlier ones (base cell: robust −3,133
USD, ML −10,158 USD, hindsight +43,814 USD against no battery).

**Grid rerun.** One sign in the flip boundary chart changed (B-19 ML, 100 percent / 4 h:
+3,926 to −1,257 USD), so the full grid was rerun (540 cells, 1,695 s, 0 violations) and
the aggregate job rewrote `edip.eval.sensitivity_grid` and the chart. Against the first
grid, 32 of 2,700 battery-strategy outcomes against no battery and 31 against the fixed
schedule changed sign; median net benefit change 2 USD, largest 9,074 USD.

**Updated headline** (deterministic grid, base costs): on B-19 the guarded robust strategy
beats no battery only with larger batteries (+3,128 USD per year at 50 percent / 4 h,
+1,034 at 100 percent / 2 h, +28,281 at 100 percent / 4 h); ML dispatch beats no battery at
no base-cost size (best −1,257); nothing forecast-driven beats no battery on PGE; hindsight
would earn 22,861 to 83,107 USD per year on B-19. Share of cells beating no battery on
B-19: robust 25.9 percent, ML 2.8 percent, fixed 14.8 percent.

**Capital layer (business case only, not a gate):** see
[../business_case_capital.md](../business_case_capital.md). At the mid ATB cost no
non-hindsight strategy recovers its capital in 15 years; the best (robust, 100 percent /
4 h) has a 40.6 year simple payback and an NPV of −907,229 USD.

## 7. Exit checklist

| Item | Status |
|---|---|
| Flip boundary chart saved as PNG and JSON for the public pages | **Pass** (`frontend/public/data/sensitivity/`, `docs/gates/gate4_flip_boundary.*`) |
| Gate report states the headline finding in one sentence with its numbers | **Pass** (section 4) |
| `sensitivity_grid` written; every cell a full replay | **Pass** (540 cells, 0 violations) |

Awaiting approval to start Gate 5.
