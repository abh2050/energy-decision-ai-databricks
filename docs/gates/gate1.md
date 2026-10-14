# Gate 1 report: Data

## 1. Gate and date

Gate 1, 2026-10-14 (revised the same day after the owner's tariff and time-basis decisions).

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR1 snapshot | UCI zip stored in volume `edip.raw.snapshots` under `uci_ld2011_2014/2026-10-14/` with `manifest.json` (source URL, DOI, CC BY 4.0 attribution, bytes, SHA256, retrieval method) | `src/edip/data/ingest_job.py`, `config/data.yaml` |
| FR2 client selection | Written rule in `config/data.yaml`, applied in order with counts recorded; tariff eligibility verified | `src/edip/core/selection.py`, `src/edip/core/eligibility.py` |
| FR3 units | 15 minute kW / 4 = interval kWh; hourly mean kW and hourly kWh, hour beginning | `src/edip/core/units.py` |
| FR4 DST and activation | March placeholder rows removed, October doubled rows split in half, leading zeros before activation excluded; output in UTC | `src/edip/core/cleaning.py` |
| FR5 splits | Chronological train, validation, test with recorded boundaries | `src/edip/core/splits.py` |
| FR6 tariffs | PG&E B-19 secondary; PGE Schedule 85 secondary with every applicable adjustment schedule; synthetic sweep with gap multipliers 1.0, 1.5, 2.0, 3.0. Every charge cites a source document with URL, SHA256, sheet, advice letter, and effective date. Periods assigned from the Europe/Lisbon wall clock | `src/edip/core/tariff.py`, `config/tariffs/` |
| FR7 provenance | Table and column comments state the load origin, units, and UTC basis; the UI display arrives at Gate 6 | `edip.curated.load_observations` |
| Source archive | All 37 tariff PDFs plus `SHA256SUMS` in `/Volumes/edip/raw/snapshots/tariffs/2026-10-14/` | — |
| Job | Serverless bundle job `edip-gate1-ingest`, logged to MLflow with dataset and config hashes | `resources/gate1_jobs.yml` |

## 3. Test results

- pytest: **64 passed, 0 failed, 0 warnings** at first review (73 after the decisions in section 6). Gate 1 tests: units 5, cleaning 8, splits
  and selection 5, tariffs 16, eligibility 4.
- Required tests:
  1. Four readings of 100 kW produce 100 kWh for the hour: `test_four_readings_of_100_kw_make_100_kwh`, **pass**.
  2. DST handling on known dates. Data cleaning: 2013-03-31 and 2013-10-27
     (`test_march_placeholder_rows_dropped_and_day_has_24_hours`,
     `test_october_doubled_hour_split_preserves_energy`). Tariff periods on UTC
     horizons: 2014-03-30 maps 24 UTC hours to 23 local clock hours and 2014-10-26 to a
     repeated 01:00 (`test_march_transition_day_maps_24_utc_hours_to_23_local_hours`,
     `test_october_transition_day_maps_24_utc_hours_to_25_hour_local_clock`). **Pass**.
  3. No test timestamp in train or validation: `test_test_partition_timestamps_never_in_train_or_validation`, **pass**.
- Ruff check and format: clean. Repo scan: 0 findings.
- Ingest job: succeeded on serverless (MLflow run `gate1-ingest`).

## 4. Key numbers

From [gate1_data_quality.json](gate1_data_quality.json) (the job's report, also stored
next to the snapshot) and table `edip.curated.load_observations` (Delta version 39).

| Item | Value |
|---|---|
| Dataset SHA256 | `f6c4d0e0df12ecdb9ea008dd6eef3518adb52c559d04a9bac2e1b81dcfc8d4e1` |
| Raw rows x clients | 140,256 x 370 (labels 2011-01-01 00:15 to 2015-01-01 00:00) |
| Selection counts | 370 → 160 activated before 2012 → 48 with documented DST artifacts on all six change days → 27 with all training readings nonzero → 6 in the B-19 demand range |
| Selected client | **MT_189** (lowest number among MT_189, MT_199, MT_205, MT_214, MT_274, MT_325) |
| PGE Schedule 85 check (30 minute Demand, 13 month windows) | **Pass in 24 of 24 windows.** Monthly Demand 457.8 to 804.8 kW: every window has 13 of 13 months above 200 kW (rule: more than 6) and 0 above 4,000 kW (rule: at most 1) |
| PG&E B-19 check (15 minute demand) | Monthly demand 472.4 to 826.5 kW; longest run above 499 kW is 19 months (rule: 3); at most 999 kW in all 25 twelve-month windows |
| DST checks, MT_189 | March 2012, 2013, 2014: four placeholder rows all zero. October doubling ratios: 1.92, 1.91, 2.01 |
| Rows removed | 35,040 readings before the series start (2011); 12 March placeholder readings; 0 incomplete hours |
| Rows split | 12 October readings split into 24 |
| Hourly rows | 26,304 (UTC) |
| Train | 2012-01-01 to 2013-06-30 UTC, 13,128 hours, 0 zero hours, max 751.8 kW hourly mean |
| Validation | 2013-07-01 to 2013-12-31, 4,416 hours, 0 zero hours, max 796.9 kW |
| Test | 2014-01-01 to 2014-12-31, 8,760 hours, 1 zero hour, max 671.9 kW |

### Tariffs

| Tariff | Sources | Included | Excluded |
|---|---|---|---|
| PG&E B-19 secondary (anchored) | B-19 Sheet 4, Advice 7846-E, effective 2026-03-01; Section 6 periods, Advice 7116-E-B | Total bundled energy rates by season and period; maximum, peak, and part-peak demand charges | Customer charge (fixed); percentage taxes and franchise fees. Not modelled: Peak Day Pricing (opt-out program, events unknown), power factor adjustment (no power factor data), standby |
| PGE Schedule 85 secondary, Cost of Service (low spread) | Schedule 85 Fourth Revision of Sheet 85-1, Advice 26-24, effective 2026-07-08; Schedule 100 (applicability); Rule B; 21 adjustment schedules; period definitions from the Third Revision of Sheet 85-1 (Advice 25-38, effective 2026-01-01) | System usage charge; Schedule 125 TOU energy (on 5.808, mid 4.664, off 3.901 cents per kWh); flat adjustments 105, 109, 115, 118, 120, 121, 122, 123, 126, 135 to 138, 143, 145, 146, 149 to 153; transmission, distribution, and generation demand charges on Peak Demand (Monday to Saturday 6 a.m. to 10 p.m.); tiered Facility Capacity charge | Basic charge (fixed); Schedules 103 and 106 (percentage taxes); Schedule 108 (1.5 percent public purpose charge, open question 1); Schedule 102 (residential and farm only); Schedule 128 (Daily Price and Direct Access only). Not modelled: reactive demand (no kVAR data) |
| Synthetic sweep (stress) | Derived from B-19 | B-19 with summer peak = off-peak + m x (peak - off-peak), m = 1.0, 1.5, 2.0, 3.0 | As B-19 |

## 5. Deviations and why

1. **Series starts 2012-01-01.** The data shows the documented DST artifacts in 2012 to
   2014 but not in 2011, so the 2011 clock basis cannot be verified.
2. **UTC storage, Lisbon wall-clock tariff periods (owner decision).** Every horizon is
   24 UTC hours; on transition days those hours cover 23 or 25 local clock hours, and
   periods, seasons, and weekdays follow the local clock.
3. **DST artifacts differ from the UCI description.** The placeholder and doubled rows sit
   at wall-clock labels 01:00 to 01:45, and only about two thirds of clients show them,
   so the selection rule requires the pattern on all six change days.
4. **Selection rule adds a demand criterion** (B-19 mandatory range); MT_189 also meets
   PGE Schedule 85's applicability rule. Ties go to the lowest client number; no
   validation or test data is used.
5. **Snapshot uploaded, not downloaded by the job.** Serverless egress is blocked by the
   workspace network policy; the manifest records this, and the SHA256 matches.
6. **Hourly demand.** B-19 bills 15 minute demand and PGE 30 minute demand; the project
   is hourly (FR3), which understates demand charges. Recorded in both tariff files.
7. **PGE energy periods.** The current Schedule 85 (effective 2026-07-08) moved energy
   pricing to Schedule 125 and dropped the period footnote; Schedule 125 does not restate
   the hours. The periods come from the prior revision (effective 2026-01-01), the latest
   published definition.
8. **Owner-downloaded PDF superseded.** The Schedule 85 file in `~/Downloads` is the
   Third Revision (effective 2026-01-01). PGE's tariff page now links the Fourth Revision
   (effective 2026-07-08), which is used for rates; the Third Revision is kept as the
   period-definition source.
9. **Dependencies.** Core dependencies (numpy 2.3.5, pandas 2.3.3, pydantic, pyyaml) are
   separate from a `platform` extra so Databricks jobs install less.

## 6. Owner decisions after review (2026-10-14)

Gate 1 was approved with these changes, all applied before Gate 2:

1. **Schedule 108** is modelled as a 1.015 multiplier on every modelled variable charge
   (energy, demand, Facility Capacity) for PGE; all savings are reported before tax
   (`variable_charge_multiplier`, `savings_basis` in the tariff files).
2. **Schedule 126** stays included; the Schedule 100 reasoning is recorded on the
   component (`applicability_note`).
3. **Synthetic sweep**: in both summer and winter, off-peak fixed, peak and part-peak
   gaps to off-peak multiplied by m (1.0, 1.5, 2.0, 3.0); super off-peak unchanged.
4. **PGE period hours**: PGE Rules A to N (all 14 downloaded) and the current Schedules
   83, 85, 89, and 125 contain no definition of the energy period hours. The hours are
   labelled as coming from a **superseded revision** (Schedule 85 Third Revision,
   effective 2026-01-01). The current Schedule 38 (effective 2026-07-08) states the same
   hours for its own energy periods and is recorded as corroboration only.
5. **Settlement billing demand** (`src/edip/core/billing_demand.py`,
   `config/settlement.yaml`): 15 minute actual load minus the hourly battery output held
   flat within the hour, floored at zero, averaged over 15 minutes for B-19 and 30 minutes
   for PGE. New table `edip.curated.load_intervals_15min` (105,216 rows, four per hourly
   row; the 15 minute values average back to `load_observations` exactly).
6. **Facility Capacity history**: seeded with the 11 months of no-battery Demand before
   the first billed month, so every test month is billed. Seeding with no-battery Demand
   can only raise Facility Capacity, which is conservative for battery savings.

Tests added: billing demand 7 (15 minute B-19 rule, 30 minute PGE rule, interval
alignment, charging and the no-export floor, PGE Sunday window, Facility Capacity
seeding and missing history). Suite: **73 passed**.

## 7. Exit checklist

| Item | Status |
|---|---|
| `load_observations` exists in Delta with documented columns and units | **Pass** |
| Data quality report lists row counts, removed rows, and the selected client | **Pass** ([gate1_data_quality.json](gate1_data_quality.json), section 4) |
| Required tests (units, DST, split isolation) | **Pass** |
| Task 7: tariffs encoded with provenance; synthetic labelled | **Pass** |
| MT_189 against Schedule 85's "more than six times in 13 months" rule | **Pass** (24 of 24 windows) |

Awaiting approval to start Gate 2.
