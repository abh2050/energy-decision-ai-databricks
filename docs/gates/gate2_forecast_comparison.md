# Gate 2 forecast comparison

Generated from [gate2_results.json](gate2_results.json) (MLflow run `a9cf74a771ad442696fd78d73bfea987`, model `edip.ml.load_forecaster` version 1, config hash `8e6df8209868ceb6`). Client MT_189; 24 hour forecasts at 00:00 UTC each day; kW are hourly means.

## Summary

| Forecaster | Split | Days | MAE kW | MAPE % | Abs error at actual peak hour kW | Abs peak magnitude error kW | Peak hour hit % | P10-P90 coverage % | Pinball kW (P10 / P50 / P90 / mean) |
|---|---|---|---|---|---|---|---|---|---|
| Seasonal (previous week) | test | 365 | 31.72 | 8.42 | 42.47 | 42.03 | 21.4 | n/a | n/a |
| LightGBM point | test | 365 | 22.00 | 6.06 | 31.80 | 27.92 | 26.6 | n/a | n/a |
| LightGBM quantile (P50; P10-P90 band) | test | 365 | 22.03 | 6.06 | 32.04 | 28.28 | 27.9 | 72.9 | 5.37 / 11.02 / 5.43 / 7.27 |
| Seasonal (previous week) | validation | 184 | 40.51 | 9.87 | 57.77 | 57.56 | 27.7 | n/a | n/a |
| LightGBM point | validation | 184 | 26.41 | 6.72 | 41.98 | 36.91 | 27.2 | n/a | n/a |
| LightGBM quantile (P50; P10-P90 band) | validation | 184 | 26.44 | 6.74 | 41.83 | 36.63 | 27.2 | 72.8 | 6.54 / 13.22 / 7.03 / 8.93 |

## Test error by forecast hour (UTC hour of the planning day)

| Hour | Seasonal MAE | Seasonal MAPE % | LGBM point MAE | LGBM point MAPE % | LGBM P50 MAE | LGBM P50 MAPE % |
|---|---|---|---|---|---|---|
| 0 | 23.56 | 7.88 | 17.62 | 5.90 | 17.35 | 5.81 |
| 1 | 27.30 | 11.00 | 19.11 | 7.84 | 19.18 | 7.88 |
| 2 | 26.72 | 11.68 | 20.80 | 9.26 | 20.84 | 9.27 |
| 3 | 23.56 | 10.52 | 18.05 | 8.11 | 17.92 | 8.04 |
| 4 | 24.86 | 9.38 | 17.31 | 6.62 | 17.45 | 6.67 |
| 5 | 23.53 | 7.48 | 16.69 | 5.36 | 16.79 | 5.38 |
| 6 | 25.53 | 7.94 | 18.38 | 5.80 | 18.27 | 5.76 |
| 7 | 23.74 | 7.35 | 17.55 | 5.52 | 17.58 | 5.53 |
| 8 | 28.45 | 7.53 | 19.89 | 5.46 | 19.65 | 5.39 |
| 9 | 28.72 | 7.02 | 20.28 | 5.25 | 20.08 | 5.20 |
| 10 | 31.62 | 7.51 | 21.50 | 5.38 | 21.35 | 5.33 |
| 11 | 39.03 | 8.58 | 25.41 | 5.71 | 25.36 | 5.68 |
| 12 | 43.90 | 9.89 | 28.16 | 6.63 | 28.20 | 6.63 |
| 13 | 44.05 | 9.62 | 28.16 | 6.36 | 28.19 | 6.36 |
| 14 | 44.20 | 9.47 | 27.01 | 5.95 | 27.35 | 6.02 |
| 15 | 46.13 | 9.69 | 28.76 | 6.15 | 29.12 | 6.22 |
| 16 | 45.20 | 9.34 | 29.32 | 6.19 | 29.59 | 6.24 |
| 17 | 40.81 | 8.40 | 28.65 | 6.03 | 28.89 | 6.08 |
| 18 | 38.88 | 8.06 | 26.49 | 5.64 | 26.53 | 5.64 |
| 19 | 31.65 | 7.00 | 21.48 | 4.88 | 21.37 | 4.86 |
| 20 | 26.22 | 6.13 | 19.59 | 4.72 | 19.61 | 4.72 |
| 21 | 23.82 | 5.86 | 17.55 | 4.52 | 17.81 | 4.59 |
| 22 | 24.66 | 6.80 | 19.50 | 5.54 | 19.63 | 5.56 |
| 23 | 25.18 | 7.85 | 20.85 | 6.65 | 20.69 | 6.59 |

Pinball loss and coverage apply only to the quantile forecaster.

## Version 2: conformalized quantile regression

From [gate2_calibration_results.json](gate2_calibration_results.json) (MLflow run `806d05010804457a9fa4a3208e941ad3`, model version 2). Calibration: 92 days (2013-10-01 to 2014-01-01, exclusive), one correction per forecast hour. These months were also used for tuning.

| Split | Coverage raw % | Coverage calibrated % | Mean width raw kW | Mean width calibrated kW | Pinball P10 raw / cal kW | Pinball P90 raw / cal kW |
|---|---|---|---|---|---|---|
| validation | 72.80 | 79.03 | 67.0 | 77.2 | 6.54 / 6.43 | 7.03 / 6.81 |
| test | 72.89 | 80.51 | 59.6 | 69.8 | 5.37 / 5.26 | 5.43 / 5.42 |

Correction per forecast hour (kW added below P10 and above P90; negative narrows):

| Hour | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| kW | 6.77 | 7.45 | 9.74 | 7.83 | 5.28 | -0.25 | 2.46 | 3.88 | 0.89 | 8.29 | 3.61 | 10.34 | 9.41 | 4.83 | 2.77 | 11.97 | 6.32 | 5.32 | 8.05 | 1.15 | 7.37 | -0.57 | -1.61 | 1.76 |

## Peak timing

| Split | Forecast peak within one hour of actual: seasonal / LGBM point / LGBM P50 % |
|---|---|
| validation | 51.6 / 49.5 / 48.9 |
| test | 52.3 / 62.7 / 64.4 |

Months whose actual peak hour (highest hourly kW, Lisbon clock) falls in the robust strategy's protected window:

| Split | Tariff | Protected periods | Months in window | Share % | Months outside (local hour, period) |
|---|---|---|---|---|---|
| validation | pge_b19_secondary | peak | 4 of 6 | 66.7 | 2013-08 (15:00, part_peak); 2013-12 (12:00, off_peak) |
| validation | pgn_sched85_secondary | on_peak | 4 of 6 | 66.7 | 2013-08 (15:00, off_peak); 2013-12 (12:00, mid_peak) |
| test | pge_b19_secondary | peak | 9 of 12 | 75.0 | 2014-02 (11:00, off_peak); 2014-05 (14:00, off_peak); 2014-06 (14:00, part_peak) |
| test | pgn_sched85_secondary | on_peak | 8 of 12 | 66.7 | 2014-02 (11:00, mid_peak); 2014-05 (14:00, mid_peak); 2014-06 (14:00, mid_peak); 2014-12 (19:00, off_peak) |
