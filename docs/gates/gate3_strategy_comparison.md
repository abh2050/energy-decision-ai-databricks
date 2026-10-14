# Gate 3 strategy comparison

Generated from [gate3_results.json](gate3_results.json). Test year 2014 (UTC), client MT_189, forecaster version 2, config hash `122505f6dd18f558`. Battery: 375.9 kW / 751.8 kWh (50% of the training peak 751.8 kW, 2 hours). All amounts in USD before tax. Operating cost (assumed) 4,868 per year, charged to forecast-driven strategies.

## pge_b19_secondary

| Strategy | Settled bill | Energy | Demand | Facility capacity | Max billing demand kW | Throughput kWh | Degradation | Net benefit gross | Net benefit after op. cost | Regret vs hindsight | Violations | Clipped discharge kWh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_battery | 905,027 | 455,648 | 449,379 | 0 | 747.6 | 0 | 0 | 0 | 0 | 35,980 | 0 | 0 |
| fixed_schedule | 955,101 | 448,031 | 507,070 | 0 | 795.4 | 207,908 | 6,237 | -56,311 | -56,311 | 92,291 | 0 | 345 |
| seasonal_forecast | 960,229 | 448,601 | 511,628 | 0 | 1026.8 | 124,811 | 3,744 | -58,946 | -63,814 | 94,925 | 0 | 302 |
| ml_forecast | 959,138 | 448,755 | 510,383 | 0 | 1026.8 | 121,710 | 3,651 | -57,762 | -62,630 | 93,742 | 0 | 154 |
| robust_quantile | 960,748 | 447,994 | 512,755 | 0 | 1026.8 | 145,377 | 4,361 | -60,082 | -64,950 | 96,062 | 0 | 163 |
| hindsight | 865,157 | 450,168 | 414,989 | 0 | 815.6 | 129,684 | 3,891 | 35,980 | 35,980 | 0 | 0 | 0 |

## pgn_sched85_secondary

| Strategy | Settled bill | Energy | Demand | Facility capacity | Max billing demand kW | Throughput kWh | Degradation | Net benefit gross | Net benefit after op. cost | Regret vs hindsight | Violations | Clipped discharge kWh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_battery | 413,506 | 261,387 | 120,551 | 31,569 | 688.9 | 0 | 0 | 0 | 0 | 11,154 | 0 | 0 |
| fixed_schedule | 412,815 | 259,260 | 120,402 | 33,153 | 688.9 | 178,230 | 5,347 | -4,656 | -4,656 | 15,810 | 0 | 354 |
| seasonal_forecast | 414,547 | 261,275 | 119,876 | 33,397 | 688.9 | 15,048 | 451 | -1,493 | -6,361 | 12,647 | 0 | 0 |
| ml_forecast | 414,161 | 261,297 | 119,645 | 33,220 | 688.9 | 11,452 | 344 | -999 | -5,867 | 12,153 | 0 | 0 |
| robust_quantile | 413,248 | 261,129 | 118,703 | 33,415 | 688.9 | 23,851 | 716 | -457 | -5,325 | 11,611 | 0 | 0 |
| hindsight | 400,154 | 260,817 | 105,804 | 33,533 | 630.1 | 73,261 | 2,198 | 11,154 | 11,154 | 0 | 0 | 0 |

## synthetic_high_spread_m1

| Strategy | Settled bill | Energy | Demand | Facility capacity | Max billing demand kW | Throughput kWh | Degradation | Net benefit gross | Net benefit after op. cost | Regret vs hindsight | Violations | Clipped discharge kWh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_battery | 905,027 | 455,648 | 449,379 | 0 | 747.6 | 0 | 0 | 0 | 0 | 35,980 | 0 | 0 |
| fixed_schedule | 955,101 | 448,031 | 507,070 | 0 | 795.4 | 207,908 | 6,237 | -56,311 | -56,311 | 92,291 | 0 | 345 |
| seasonal_forecast | 960,229 | 448,601 | 511,628 | 0 | 1026.8 | 124,811 | 3,744 | -58,946 | -63,814 | 94,925 | 0 | 302 |
| ml_forecast | 959,138 | 448,755 | 510,383 | 0 | 1026.8 | 121,710 | 3,651 | -57,762 | -62,630 | 93,742 | 0 | 154 |
| robust_quantile | 960,748 | 447,994 | 512,755 | 0 | 1026.8 | 145,377 | 4,361 | -60,082 | -64,950 | 96,062 | 0 | 163 |
| hindsight | 865,157 | 450,168 | 414,989 | 0 | 815.6 | 129,684 | 3,891 | 35,980 | 35,980 | 0 | 0 | 0 |

## synthetic_high_spread_m1_5

| Strategy | Settled bill | Energy | Demand | Facility capacity | Max billing demand kW | Throughput kWh | Degradation | Net benefit gross | Net benefit after op. cost | Regret vs hindsight | Violations | Clipped discharge kWh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_battery | 930,955 | 481,576 | 449,379 | 0 | 747.6 | 0 | 0 | 0 | 0 | 38,795 | 0 | 0 |
| fixed_schedule | 975,850 | 468,780 | 507,070 | 0 | 795.4 | 207,908 | 6,237 | -51,132 | -51,132 | 89,927 | 0 | 345 |
| seasonal_forecast | 1,027,155 | 466,446 | 560,709 | 0 | 1026.8 | 232,526 | 6,976 | -103,176 | -108,044 | 141,970 | 0 | 453 |
| ml_forecast | 1,025,738 | 466,553 | 559,185 | 0 | 1026.8 | 230,580 | 6,917 | -101,701 | -106,569 | 140,495 | 0 | 471 |
| robust_quantile | 1,015,869 | 466,428 | 549,441 | 0 | 1026.8 | 230,818 | 6,925 | -91,839 | -96,707 | 130,633 | 0 | 500 |
| hindsight | 886,203 | 469,897 | 416,306 | 0 | 815.6 | 198,580 | 5,957 | 38,795 | 38,795 | 0 | 0 | 0 |

## synthetic_high_spread_m2

| Strategy | Settled bill | Energy | Demand | Facility capacity | Max billing demand kW | Throughput kWh | Degradation | Net benefit gross | Net benefit after op. cost | Regret vs hindsight | Violations | Clipped discharge kWh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_battery | 956,882 | 507,503 | 449,379 | 0 | 747.6 | 0 | 0 | 0 | 0 | 42,885 | 0 | 0 |
| fixed_schedule | 996,598 | 489,528 | 507,070 | 0 | 795.4 | 207,908 | 6,237 | -45,953 | -45,953 | 88,838 | 0 | 345 |
| seasonal_forecast | 1,047,747 | 487,329 | 560,418 | 0 | 1026.8 | 232,522 | 6,976 | -97,841 | -102,709 | 140,726 | 0 | 457 |
| ml_forecast | 1,047,433 | 487,442 | 559,991 | 0 | 1024.9 | 230,545 | 6,916 | -97,467 | -102,335 | 140,352 | 0 | 471 |
| robust_quantile | 1,034,743 | 487,276 | 547,467 | 0 | 973.9 | 230,837 | 6,925 | -84,786 | -89,654 | 127,671 | 0 | 500 |
| hindsight | 908,040 | 491,563 | 416,477 | 0 | 815.6 | 198,580 | 5,957 | 42,885 | 42,885 | 0 | 0 | 0 |

## synthetic_high_spread_m3

| Strategy | Settled bill | Energy | Demand | Facility capacity | Max billing demand kW | Throughput kWh | Degradation | Net benefit gross | Net benefit after op. cost | Regret vs hindsight | Violations | Clipped discharge kWh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_battery | 1,008,737 | 559,358 | 449,379 | 0 | 747.6 | 0 | 0 | 0 | 0 | 51,436 | 0 | 0 |
| fixed_schedule | 1,038,095 | 531,025 | 507,070 | 0 | 795.4 | 207,908 | 6,237 | -35,595 | -35,595 | 87,032 | 0 | 345 |
| seasonal_forecast | 1,089,511 | 529,093 | 560,418 | 0 | 1026.8 | 232,522 | 6,976 | -87,750 | -92,618 | 139,186 | 0 | 457 |
| ml_forecast | 1,089,486 | 529,218 | 560,269 | 0 | 1024.9 | 230,527 | 6,916 | -87,665 | -92,533 | 139,102 | 0 | 471 |
| robust_quantile | 1,076,406 | 528,971 | 547,435 | 0 | 973.9 | 230,899 | 6,927 | -74,596 | -79,464 | 126,032 | 0 | 463 |
| hindsight | 951,343 | 534,892 | 416,451 | 0 | 815.6 | 198,585 | 5,958 | 51,436 | 51,436 | 0 | 0 | 0 |

## Economics against the frozen targets

| Tariff | Strategy | Fixed net benefit | Incremental (frozen reading) | Required (10% of fixed) | Op. cost | Pass (frozen) | Incremental (single count) | Pass (single count) |
|---|---|---|---|---|---|---|---|---|
| pge_b19_secondary | ml_forecast | -56,311 | -6,319 | -5,631 | 4,868 | no | -1,451 | no |
| pge_b19_secondary | robust_quantile | -56,311 | -8,639 | -5,631 | 4,868 | no | -3,771 | no |
| pgn_sched85_secondary | ml_forecast | -4,656 | -1,211 | -466 | 4,868 | no | 3,657 | no |
| pgn_sched85_secondary | robust_quantile | -4,656 | -669 | -466 | 4,868 | no | 4,199 | no |
| synthetic_high_spread_m1 | ml_forecast | -56,311 | -6,319 | -5,631 | 4,868 | no | -1,451 | no |
| synthetic_high_spread_m1 | robust_quantile | -56,311 | -8,639 | -5,631 | 4,868 | no | -3,771 | no |
| synthetic_high_spread_m1_5 | ml_forecast | -51,132 | -55,437 | -5,113 | 4,868 | no | -50,569 | no |
| synthetic_high_spread_m1_5 | robust_quantile | -51,132 | -45,575 | -5,113 | 4,868 | no | -40,707 | no |
| synthetic_high_spread_m2 | ml_forecast | -45,953 | -56,382 | -4,595 | 4,868 | no | -51,514 | no |
| synthetic_high_spread_m2 | robust_quantile | -45,953 | -43,701 | -4,595 | 4,868 | no | -38,833 | no |
| synthetic_high_spread_m3 | ml_forecast | -35,595 | -56,938 | -3,560 | 4,868 | no | -52,070 | no |
| synthetic_high_spread_m3 | robust_quantile | -35,595 | -43,868 | -3,560 | 4,868 | no | -39,000 | no |

Fixed-schedule discharge hours (local clock) per tariff and season, from training data:

- pge_b19_secondary: window `Maximum peak demand`, hours {'summer': [17, 18], 'winter': [19, 20]}
- pgn_sched85_secondary: window `Transmission and related services, per kW of monthly Peak Demand`, hours {'all_year': [18, 19]}
- synthetic_high_spread_m1: window `Maximum peak demand`, hours {'summer': [17, 18], 'winter': [19, 20]}
- synthetic_high_spread_m1_5: window `Maximum peak demand`, hours {'summer': [17, 18], 'winter': [19, 20]}
- synthetic_high_spread_m2: window `Maximum peak demand`, hours {'summer': [17, 18], 'winter': [19, 20]}
- synthetic_high_spread_m3: window `Maximum peak demand`, hours {'summer': [17, 18], 'winter': [19, 20]}
