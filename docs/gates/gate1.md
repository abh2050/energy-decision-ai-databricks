# Gate 1 report: Data

## 1. Gate and date

Gate 1, 2026-10-14.

## 2. What was built

| Requirement | Built | Files |
|---|---|---|
| FR1 snapshot | UCI zip stored in volume `edip.raw.snapshots` under `uci_ld2011_2014/2026-10-14/` with `manifest.json` (source URL, DOI, CC BY 4.0 attribution, bytes, SHA256, retrieval method) | `src/edip/data/ingest_job.py`, `config/data.yaml` |
| FR2 client selection | Written rule in `config/data.yaml`, applied in order with counts recorded | `src/edip/core/selection.py` |
| FR3 units | 15 minute kW / 4 = interval kWh; hourly mean kW and hourly kWh, hour beginning | `src/edip/core/units.py` |
| FR4 DST and activation | March placeholder rows removed, October doubled rows split in half, leading zeros before activation excluded; output in Portuguese standard time | `src/edip/core/cleaning.py` |
| FR5 splits | Chronological train, validation, test with recorded boundaries | `src/edip/core/splits.py` |
| FR6 tariffs | PG&E B-19 secondary encoded from the official sheet; synthetic high-spread stress tariff derived and labelled; PGE low-spread tariff pending (open question 1) | `src/edip/core/tariff.py`, `config/tariffs/` |
| FR7 provenance | Table and column comments state Portuguese load 2011 to 2014, units, and time basis; the UI display arrives at Gate 6 | `edip.curated.load_observations` |
| Job | Serverless bundle job `edip-gate1-ingest`, logged to MLflow with dataset and config hashes | `resources/gate1_jobs.yml` |

## 3. Test results

- pytest: **58 passed, 0 failed, 0 warnings**. New in Gate 1: units 5, cleaning 9, splits
  and selection 5, tariffs 14.
- Required tests:
  1. Four readings of 100 kW produce 100 kWh for the hour: `test_four_readings_of_100_kw_make_100_kwh`, **pass**.
  2. DST handling on known March and October dates (2013-03-31, 2013-10-27): `test_march_placeholder_rows_dropped_and_day_has_24_hours`, `test_october_doubled_hour_split_preserves_energy`, **pass**.
  3. No test timestamp in train or validation: `test_test_partition_timestamps_never_in_train_or_validation`, **pass**.
- Ruff check and format: clean. Repo scan: 0 findings.
- Ingest job: succeeded on serverless (MLflow run `gate1-ingest`).

## 4. Key numbers

All from [gate1_data_quality.json](gate1_data_quality.json) (the job's report, also stored
next to the snapshot) and table `edip.curated.load_observations` (Delta version 29).

| Item | Value |
|---|---|
| Dataset SHA256 | `f6c4d0e0df12ecdb9ea008dd6eef3518adb52c559d04a9bac2e1b81dcfc8d4e1` |
| Raw rows x clients | 140,256 x 370 (labels 2011-01-01 00:15 to 2015-01-01 00:00) |
| Selection counts | 370 clients → 160 activated before 2012 → 48 with documented DST artifacts in all six change days → 27 with all training readings nonzero → 6 in the B-19 demand range |
| Selected client | **MT_189** (lowest number among MT_189, MT_199, MT_205, MT_214, MT_274, MT_325) |
| MT_189 training maximum demand | 804.4 kW (15 minute) |
| MT_189 activation | first reading, 2011-01-01 00:15 |
| DST checks, MT_189 | March 2012, 2013, 2014: four placeholder rows all zero. October doubling ratios: 1.92, 1.91, 2.01 |
| Rows removed | 35,040 readings before the series start (2011); 12 March placeholder readings; 0 incomplete hours |
| Rows split | 12 October readings split into 24 |
| Hourly rows | 26,304 |
| Train | 2012-01-01 to 2013-06-30, 13,128 hours, 0 zero hours, max 751.8 kW hourly mean |
| Validation | 2013-07-01 to 2013-12-31, 4,416 hours, 0 zero hours, max 796.9 kW |
| Test | 2014-01-01 to 2014-12-31, 8,760 hours, 1 zero hour, max 671.9 kW |

`load_observations` columns: `client_id`, `hour_start` (TIMESTAMP, Portuguese standard
time = UTC), `kw_mean` (kW), `kwh` (kWh), `n_intervals` (always 4), `split`,
`dataset_sha256`. Every column carries a comment with its unit.

## 5. Deviations and why

1. **Series starts 2012-01-01.** The data shows the documented DST artifacts in 2012 to
   2014 but not in 2011, so the 2011 clock basis cannot be verified. Splits: train
   18 months, validation 6 months, test 2014 (12 complete billing months).
2. **Time basis is Portuguese standard time (WET, equal to UTC).** Every day has 24 hours
   and energy is preserved. Tariff windows are applied to this clock (assumption; open
   question 3).
3. **DST artifacts differ from the UCI description.** The placeholder and doubled rows sit
   at wall-clock labels 01:00 to 01:45 (the nonexistent and repeated local times), and only
   about two thirds of clients show them. The selection rule therefore requires the
   documented pattern on all six change days, so the correction is verifiable for the
   chosen client.
4. **Selection rule adds a demand criterion.** The PRD selects by training completeness.
   The rule also requires the training demand to fall in PG&E B-19's mandatory range
   (above 499 kW for three consecutive months, at most 999 kW), so the anchored tariff
   applies to the chosen load. Ties go to the lowest client number; no validation or
   test data is used.
5. **Snapshot uploaded, not downloaded by the job.** Serverless egress is blocked by the
   workspace network policy. The file was downloaded locally and uploaded through the
   Files API; the manifest records this, and the SHA256 matches the local download.
6. **Hourly demand.** B-19 bills demand on 15 minute averages; FR3 makes the project
   hourly, which understates demand charges. Recorded in the tariff file.
7. **Dependencies.** Core dependencies (numpy 2.3.5, pandas 2.3.3, pydantic, pyyaml) are
   separate from a `platform` extra, so Databricks jobs install less; pandas stays on 2.x
   to match the Databricks runtime.

## 6. Open questions for the owner

1. **PGE tariff sheet (blocks the low-spread case).** PGE's tariff page needs a browser.
   Please download the current **Schedule 85** PDF from portlandgeneral.com (Rates and
   regulatory → Tariff) and save it as `~/Downloads/pge_sched85.pdf`; I'll encode it with
   the same provenance as B-19. Two decisions:
   - Schedule 85 (201 to 4,000 kW) fits MT_189's demand; Schedule 83 (31 to 200 kW) does
     not. I chose 85 as the conservative fit; confirm.
   - Schedule 85's own energy charges are small (0.196 to 0.288 cents per kWh in the 2025
     sheet) because PGE prices most energy in separate adjustment schedules (for example
     Schedule 125). Under the "exclude riders" rule those drop out, so the PGE case would
     be almost entirely demand charges. Keep that, or include the power cost schedule?
2. **Synthetic tariff multiplier.** The stress tariff triples each season's energy spread
   around off-peak (`energy_spread_multiplier: 3.0`). Confirm or give a value.
3. **Tariff clock.** US tariff hours are applied to the Portuguese standard-time clock.
   Confirm this mapping (the alternative, Portuguese wall-clock time, would bring back
   23 and 25 hour days).

## 7. Exit checklist

| Item | Status |
|---|---|
| `load_observations` exists in Delta with documented columns and units | **Pass** |
| Data quality report lists row counts, removed rows, and the selected client | **Pass** ([gate1_data_quality.json](gate1_data_quality.json), section 4) |
| Required tests (units, DST, split isolation) | **Pass** |
| Task 7: anchored and synthetic tariffs encoded | **Pass**; PGE low-spread tariff **pending** (open question 1) |

Awaiting approval to start Gate 2.
