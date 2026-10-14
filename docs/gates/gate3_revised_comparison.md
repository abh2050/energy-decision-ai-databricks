# Gate 3 revised strategy (post-hoc) versus pre-registered

Revised: [gate3_revised_results.json](gate3_revised_results.json), label "revised strategy, post-hoc", settings {'guard_margin_fraction': 0.02, 'robust_charge_band_k': 1.0}. Pre-registered: [gate3_results.json](gate3_results.json). Test year 2014, USD before tax; net benefit after the assumed operating cost.

## pge_b19_secondary

| Strategy | Bill pre | Bill revised | Net benefit pre | Net benefit revised | Max billing demand kW pre / revised | Guard clipped kWh | Guard shortfall days | Regret revised | Violations revised |
|---|---|---|---|---|---|---|---|---|---|
| no_battery | 905,027 | 905,027 | 0 | 0 | 747.6 / 747.6 | 0 | 0 | 38,512 | 0 |
| fixed_schedule | 955,101 | 926,939 | -56,311 | -27,917 | 795.4 / 747.6 | 12,124 | 0 | 66,429 | 0 |
| seasonal_forecast | 960,229 | 908,535 | -63,814 | -11,953 | 1026.8 / 747.6 | 5,827 | 53 | 45,597 | 0 |
| ml_forecast | 959,138 | 907,233 | -62,630 | -10,624 | 1026.8 / 747.6 | 4,293 | 49 | 44,269 | 0 |
| robust_quantile | 960,748 | 899,387 | -64,950 | -3,006 | 1026.8 / 747.6 | 378 | 4 | 36,650 | 0 |
| hindsight | 865,157 | 862,624 | 35,980 | 38,512 | 815.6 / 747.6 | 121 | 3 | 0 | 0 |

## pgn_sched85_secondary

| Strategy | Bill pre | Bill revised | Net benefit pre | Net benefit revised | Max billing demand kW pre / revised | Guard clipped kWh | Guard shortfall days | Regret revised | Violations revised |
|---|---|---|---|---|---|---|---|---|---|
| no_battery | 413,506 | 413,506 | 0 | 0 | 688.9 / 688.9 | 0 | 0 | 12,083 | 0 |
| fixed_schedule | 412,815 | 411,363 | -4,656 | -2,898 | 688.9 / 688.9 | 28,943 | 0 | 14,981 | 0 |
| seasonal_forecast | 414,547 | 412,716 | -6,361 | -4,507 | 688.9 / 688.9 | 2,872 | 32 | 11,723 | 0 |
| ml_forecast | 414,161 | 412,556 | -5,867 | -4,250 | 688.9 / 688.9 | 2,716 | 29 | 11,465 | 0 |
| robust_quantile | 413,248 | 409,328 | -5,325 | -1,924 | 688.9 / 688.9 | 8,855 | 100 | 9,139 | 0 |
| hindsight | 400,154 | 399,939 | 11,154 | 12,083 | 630.1 / 630.1 | 13,281 | 119 | 0 | 0 |

## synthetic_high_spread_m1

| Strategy | Bill pre | Bill revised | Net benefit pre | Net benefit revised | Max billing demand kW pre / revised | Guard clipped kWh | Guard shortfall days | Regret revised | Violations revised |
|---|---|---|---|---|---|---|---|---|---|
| no_battery | 905,027 | 905,027 | 0 | 0 | 747.6 / 747.6 | 0 | 0 | 38,512 | 0 |
| fixed_schedule | 955,101 | 926,939 | -56,311 | -27,917 | 795.4 / 747.6 | 12,124 | 0 | 66,429 | 0 |
| seasonal_forecast | 960,229 | 908,535 | -63,814 | -11,953 | 1026.8 / 747.6 | 5,827 | 53 | 45,597 | 0 |
| ml_forecast | 959,138 | 907,233 | -62,630 | -10,624 | 1026.8 / 747.6 | 4,293 | 49 | 44,269 | 0 |
| robust_quantile | 960,748 | 899,387 | -64,950 | -3,006 | 1026.8 / 747.6 | 378 | 4 | 36,650 | 0 |
| hindsight | 865,157 | 862,624 | 35,980 | 38,512 | 815.6 / 747.6 | 121 | 3 | 0 | 0 |

## synthetic_high_spread_m1_5

| Strategy | Bill pre | Bill revised | Net benefit pre | Net benefit revised | Max billing demand kW pre / revised | Guard clipped kWh | Guard shortfall days | Regret revised | Violations revised |
|---|---|---|---|---|---|---|---|---|---|
| no_battery | 930,955 | 930,955 | 0 | 0 | 747.6 / 747.6 | 0 | 0 | 41,670 | 0 |
| fixed_schedule | 975,850 | 947,848 | -51,132 | -22,899 | 795.4 / 747.6 | 12,124 | 0 | 64,569 | 0 |
| seasonal_forecast | 1,027,155 | 943,196 | -108,044 | -23,786 | 1026.8 / 747.6 | 11,172 | 69 | 60,588 | 0 |
| ml_forecast | 1,025,738 | 943,294 | -106,569 | -23,909 | 1026.8 / 747.6 | 8,474 | 50 | 60,711 | 0 |
| robust_quantile | 1,015,869 | 925,398 | -96,707 | -5,690 | 1026.8 / 747.6 | 1,373 | 7 | 42,492 | 0 |
| hindsight | 886,203 | 883,327 | 38,795 | 41,670 | 815.6 / 747.6 | 133 | 4 | 0 | 0 |

## synthetic_high_spread_m2

| Strategy | Bill pre | Bill revised | Net benefit pre | Net benefit revised | Max billing demand kW pre / revised | Guard clipped kWh | Guard shortfall days | Regret revised | Violations revised |
|---|---|---|---|---|---|---|---|---|---|
| no_battery | 956,882 | 956,882 | 0 | 0 | 747.6 / 747.6 | 0 | 0 | 45,762 | 0 |
| fixed_schedule | 996,598 | 968,757 | -45,953 | -17,880 | 795.4 / 747.6 | 12,124 | 0 | 63,643 | 0 |
| seasonal_forecast | 1,047,747 | 964,289 | -102,709 | -18,949 | 1026.8 / 747.6 | 11,290 | 70 | 59,844 | 0 |
| ml_forecast | 1,047,433 | 964,160 | -102,335 | -18,849 | 1024.9 / 747.6 | 8,446 | 50 | 59,743 | 0 |
| robust_quantile | 1,034,743 | 946,819 | -89,654 | -1,182 | 973.9 / 747.6 | 1,330 | 6 | 42,076 | 0 |
| hindsight | 908,040 | 905,162 | 42,885 | 45,762 | 815.6 / 747.6 | 133 | 4 | 0 | 0 |

## synthetic_high_spread_m3

| Strategy | Bill pre | Bill revised | Net benefit pre | Net benefit revised | Max billing demand kW pre / revised | Guard clipped kWh | Guard shortfall days | Regret revised | Violations revised |
|---|---|---|---|---|---|---|---|---|---|
| no_battery | 1,008,737 | 1,008,737 | 0 | 0 | 747.6 / 747.6 | 0 | 0 | 54,317 | 0 |
| fixed_schedule | 1,038,095 | 1,010,575 | -35,595 | -7,844 | 795.4 / 747.6 | 12,124 | 0 | 62,161 | 0 |
| seasonal_forecast | 1,089,511 | 1,006,481 | -92,618 | -9,286 | 1026.8 / 747.6 | 11,400 | 71 | 58,736 | 0 |
| ml_forecast | 1,089,486 | 1,006,239 | -92,533 | -9,075 | 1024.9 / 747.6 | 8,322 | 51 | 58,525 | 0 |
| robust_quantile | 1,076,406 | 988,947 | -79,464 | 8,543 | 973.9 / 747.6 | 1,318 | 6 | 40,906 | 0 |
| hindsight | 951,343 | 948,462 | 51,436 | 54,317 | 815.6 / 747.6 | 133 | 4 | 0 | 0 |

## Economics against the frozen targets (revised)

| Tariff | Strategy | Incremental (frozen reading) | Required | Pass | Incremental (single count) | Pass |
|---|---|---|---|---|---|---|
| pge_b19_secondary | ml_forecast | 17,293 | -2,792 and > 4,868 | yes | 22,161 | yes |
| pge_b19_secondary | robust_quantile | 24,911 | -2,792 and > 4,868 | yes | 29,779 | yes |
| pgn_sched85_secondary | ml_forecast | -1,352 | -290 and > 4,868 | no | 3,516 | no |
| pgn_sched85_secondary | robust_quantile | 975 | -290 and > 4,868 | no | 5,843 | yes |
| synthetic_high_spread_m1 | ml_forecast | 17,293 | -2,792 and > 4,868 | yes | 22,161 | yes |
| synthetic_high_spread_m1 | robust_quantile | 24,911 | -2,792 and > 4,868 | yes | 29,779 | yes |
| synthetic_high_spread_m1_5 | ml_forecast | -1,010 | -2,290 and > 4,868 | no | 3,858 | no |
| synthetic_high_spread_m1_5 | robust_quantile | 17,209 | -2,290 and > 4,868 | yes | 22,077 | yes |
| synthetic_high_spread_m2 | ml_forecast | -968 | -1,788 and > 4,868 | no | 3,900 | no |
| synthetic_high_spread_m2 | robust_quantile | 16,699 | -1,788 and > 4,868 | yes | 21,567 | yes |
| synthetic_high_spread_m3 | ml_forecast | -1,231 | -784 and > 4,868 | no | 3,637 | no |
| synthetic_high_spread_m3 | robust_quantile | 16,387 | -784 and > 4,868 | yes | 21,255 | yes |
