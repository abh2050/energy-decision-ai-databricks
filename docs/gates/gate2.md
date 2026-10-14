# Gate 2 report: Forecasting

## 1. Gate and date

Gate 2, 2026-10-14. Pre-Gate 2 owner decisions from the Gate 1 review are in
[gate1.md](gate1.md), section 6.

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR8 seasonal baseline | Previous-week forecast: load at the same hour seven days earlier | `src/edip/core/features.py` |
| FR9 LightGBM point | L1 objective on lags 24 and 168, rolling means of 24 and 168 hours shifted 24 hours, local hour of day, local day of week | `src/edip/core/features.py`, `src/edip/forecasting/models.py` |
| FR10 quantiles | LightGBM quantile models at 0.1, 0.5, 0.9; crossings removed by sorting each hour | `src/edip/forecasting/models.py` |
| FR11 daily forecasts and metrics | 24 hour forecasts at 00:00 UTC for every validation and test day; MAE and MAPE by forecast hour, peak hour error, P10 to P90 coverage, pinball loss | `src/edip/core/metrics.py`, [gate2_forecast_comparison.md](gate2_forecast_comparison.md) |
| FR12 registry | One pyfunc model returning point, p10, p50, p90, registered as `edip.ml.load_forecaster` version 1 in Unity Catalog; pinned in `config/model_versions.yaml` | `src/edip/forecasting/pyfunc_model.py` |
| FR13 ONNX | Four ONNX files with parity on 1,000 test rows logged to MLflow | `src/edip/forecasting/onnx_export.py`, `frontend/public/data/models/` |
| Delta | `edip.curated.forecast_features`, `edip.curated.forecast_predictions` (with model version and MLflow run ID) | `src/edip/forecasting/train_job.py` |
| Job | Serverless bundle job `edip-gate2-forecasting`; MLflow run tagged with `dataset_sha256` and `config_hash` | `resources/gate2_jobs.yml`, `config/forecasting.yaml` |

Tuning used the validation partition only: a grid over `num_leaves` {15, 31, 63} and
`min_child_samples` {20, 50} at learning rate 0.05, with early stopping on validation.
Chosen: `num_leaves` 31, `min_child_samples` 20; trees: point 167, P10 188, P50 183,
P90 129.

## 3. Test results

- pytest: **88 passed, 0 failed**. New in Gate 2: features 6, metrics 5, forecasting 4.
- Required tests:
  1. Leakage: `test_leakage_future_values_never_change_features` replaces every load
     value from the decision time onward (target shifted forward by 1, 24, and 168 hours)
     and confirms no feature for the planning day changes;
     `test_leakage_feature_correlation_with_future_is_zero_on_white_noise` confirms each
     lag and rolling feature has correlation below 0.05 with its target. **Pass**.
  2. ONNX parity below 0.01 kW on 1,000 rows: `test_onnx_parity_on_1000_rows_below_0_01_kw`
     (synthetic data, all four models), **pass**; on the real models in the job, **pass**
     (section 4).
- Ruff check and format: clean. Repo scan: 0 findings.
- Gate 2 job: succeeded on the third run (first two failed on dependency conflicts,
  section 5).

## 4. Key numbers

From [gate2_results.json](gate2_results.json) (MLflow run `a9cf74a771ad442696fd78d73bfea987`)
and `edip.curated.forecast_predictions`. Full table, including error by forecast hour:
[gate2_forecast_comparison.md](gate2_forecast_comparison.md).

| Test 2014, 365 days | MAE kW | MAPE % | Abs error at actual peak hour kW | Peak hour hit % | P10 to P90 coverage % | Mean pinball kW |
|---|---|---|---|---|---|---|
| Seasonal (previous week) | 31.72 | 8.42 | 42.47 | 21.4 | n/a | n/a |
| LightGBM point | 22.00 | 6.06 | 31.80 | 26.6 | n/a | n/a |
| LightGBM quantile (P50) | 22.03 | 6.06 | 32.04 | 27.9 | 72.9 | 7.27 |

| Other | Value |
|---|---|
| Validation MAE, LightGBM point (tuning objective) | 26.41 kW |
| Validation P10 to P90 coverage | 72.8 % |
| ONNX parity, max absolute difference on 1,000 test rows | point 0.00018, P10 0.00016, P50 0.00018, P90 0.00033 kW (limit 0.01) |
| Quantile crossing hours fixed by sorting | 40 |
| Registered model | `edip.ml.load_forecaster` version 1 |

**Against the PRD target**: P10 to P90 coverage must be within 5 points of 80 percent on
the test period. Version 1 measured **72.9 percent, which missed the target**; version 2
measures 80.51 percent (section 6).

## 5. Deviations and why

1. **Final fit on train only.** Validation is used to tune and early-stop; models are not
   refit on train plus validation (the more conservative reading of "tune only on the
   validation partition"; open question 2).
2. **Features rounded to float32.** ONNX models take float32 input. With float64
   training data one quantile model diverged from its ONNX export by 0.38 kW because a
   value sat on a split threshold; training on float32-representable features brings
   every model within 0.0004 kW.
3. **Decision time 00:00 UTC** with all load before the planning day known. Every
   feature for hour t uses load at t − 24 or older, so the same features hold for all
   24 horizons.
4. **ONNX opset 15**, the highest the onnxmltools LightGBM converter supports.
5. **Dependency pins for the Databricks runtime.** `onnx` 1.23 needs protobuf 6, which
   breaks the runtime's MLflow (first failed run); pinned `onnx` 1.17.0 and protobuf
   below 6 in the job (second failed run had the unsatisfiable combination). The
   runtime's MLflow is 2.x, so `log_model` uses `artifact_path` there and `name` on
   MLflow 3.
6. **One registered model** returns point and quantiles together so a replay pins one
   version (FR12); the four LightGBM boosters are its artifacts.

## 6. Changes after owner review (2026-10-14)

Gate 2 was approved with these changes:

1. **Coverage target kept at 80 ± 5 percent; conformalized quantile regression applied.**
   One correction per forecast hour (0 to 23 UTC), fitted on the last three months of
   validation (2013-10-01 to 2013-12-31, 92 days, 2,208 hours). **These calibration months
   were also used for tuning** (validation early stopping and the hyperparameter grid).
   Corrections range from -1.61 kW (narrower) to 11.97 kW (wider).
2. **Version 2 registered and pinned.** `edip.ml.load_forecaster` version 2 (MLflow run
   `806d05010804457a9fa4a3208e941ad3`) wraps the version 1 boosters unchanged (maximum
   difference from the version 1 predictions: 0.0 kW) and adds the corrections; it takes
   `horizon_h` as an extra input. Version 1 stays registered and is recorded under
   `history` in `config/model_versions.yaml`. `forecast_predictions` now holds version 2
   rows, with the version 1 band kept as `p10_raw` and `p90_raw`; earlier rows remain in
   the Delta table history.
3. **Test coverage, as measured: 80.51 percent** with version 2 (version 1: 72.89
   percent). Validation: 79.03 percent (version 1: 72.80). Mean band width on test grew
   from 59.6 kW to 69.8 kW. Details: [gate2_calibration_results.json](gate2_calibration_results.json)
   and the version 2 section of [gate2_forecast_comparison.md](gate2_forecast_comparison.md).
4. **No refit on train plus validation.** The business case notes
   ([../business_case.md](../business_case.md)) record that production would retrain
   monthly on a rolling window.
5. **New peak timing metrics** (test 2014):
   - Forecast peak within one hour of the actual peak: seasonal 52.3 percent, LightGBM
     point 62.7 percent, LightGBM P50 64.4 percent of days.
   - Months whose actual peak hour falls inside the robust strategy's protected window:
     B-19 peak period 9 of 12 (75.0 percent; outside: February at 11:00, May at 14:00,
     June at 14:00 local); PGE on-peak 8 of 12 (66.7 percent; outside: February, May,
     June, and December, whose peak fell on a Sunday). These months set the demand
     charges that P90 protection does not cover.
6. **Runtime recorded and pinned.** The `edip-runtime-probe` job recorded serverless
   environment 4: Python 3.12.3, mlflow-skinny 2.22.0, protobuf 5.29.4
   (`config/runtime.yaml`). Every data and ML job now pins `mlflow-skinny==2.22.0` and
   `protobuf==5.29.4`. Agent jobs at Gate 5 need MLflow 3.10 or later (required by
   databricks-openai) and will need their own environment spec.

Tests added: calibration 3, peak timing metrics 2. Suite: **93 passed**.

## 7. Exit checklist

| Item | Status |
|---|---|
| Forecast comparison table: MAE and MAPE by forecast hour, peak hour error, P10 to P90 coverage, pinball loss, for all three forecasters | **Pass** ([gate2_forecast_comparison.md](gate2_forecast_comparison.md); pinball and coverage apply to the quantile forecaster only) |
| ONNX files saved for the public build | **Pass** (`frontend/public/data/models/`, four models, `feature_spec.json`, and `cqr_corrections.json` for version 2) |
| Models registered in Unity Catalog and one version pinned | **Pass** (`config/model_versions.yaml`, version 2; version 1 recorded) |
| Required tests: leakage and ONNX parity | **Pass** |
| PRD success metric: coverage within 5 points of 80 percent | **Pass** with version 2 (80.51 percent on test, measured); version 1 failed (72.89 percent) |

Awaiting approval to start Gate 3.
