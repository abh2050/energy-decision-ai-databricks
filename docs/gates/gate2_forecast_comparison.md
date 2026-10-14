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
