# Gate 7 report: Public delivery and teardown

## 1. Gate and date

Gate 7, 2026-10-15, started on owner instruction after the Gate 6 review decisions.

## 2. What was built

| Task | Built | Files |
|---|---|---|
| Sandbox adapter (1) | Frozen 90 day slice of the client's real hourly load (2014-06-01 to 2014-08-29 UTC, plus 8 days of history) and a seeded synthetic generator (30 extra days, labelled synthetic). The pinned ONNX quantile models run in onnxruntime web (features and conformal corrections as in Python). The daily mixed integer program is ported to highs js and solved in a web worker when the user changes battery size, tariff, strategy, day, or reserve. Results views read the live app's own responses, exported from the corrected snapshot | `frontend/src/adapters/sandbox.ts`, `frontend/src/wasm/{forecaster,optimizer,worker,solver}.ts`, `scripts/export_sandbox.py`, `scripts/export_public.py`, `frontend/public/data/{sandbox,replay}/` |
| Recorded traces (2) | The 40 traces from the final configuration, keyed by scenario, with the deterministic verdicts for the cell each run evaluated. A scenario without a recording shows the template summary, labelled "template" | `frontend/public/data/traces/` |
| Banner (3) | "Sandbox mode: model and optimizer run locally in your browser; agent responses are recorded from the live system." (sticky, every view) | `frontend/src/pages/sandbox.tsx` |
| Explainer (4) | Three minute captioned demo video recorded from the deployed app; clickable architecture diagram (7 layers: what runs and why); animated walkthrough of held-out run h02; 5 screenshots of the final configuration; MLflow trace excerpts; results (2014 replay), sensitivity map, agent evaluation, and the recommendation | `frontend/src/explainer/Explainer.tsx`, `frontend/public/media/`, `frontend/public/data/explainer/` |
| Public bundle scan (5) | CI and the Pages workflow build the pages, then fail if `site/` contains a workspace URL, token pattern, or email | `.github/workflows/ci.yml`, `pages.yml`, `scripts/scan_public_bundle.py` |
| GitHub Pages (6) | <https://abh2050.github.io/energy-decision-ai-databricks/sandbox/> and <https://abh2050.github.io/energy-decision-ai-databricks/explainer/> (landing page at the repository path) | `.github/workflows/pages.yml`, `frontend/vite.pages.config.ts` |
| Export and teardown (7) | Every Delta table (40, 3,336,596 rows) as parquet with a manifest, tariff sheets and the UCI snapshot manifest, and the Lakebase state, published as release asset `results-2026-10-15` (28.1 MB). Teardown: bundle destroy (app, 17 jobs, Lakebase project, schemas, volumes; 25 resources), catalog `edip` deleted, secret scope `edip` and service principal `edip-viewer-e2e` deleted | `src/edip/eval/export_job.py`, `scripts/export_lakebase.py` |
| After teardown (8) | Both pages opened and tested against the deployed GitHub Pages site after teardown | section 3 |

## 3. Test results

- Public pages, Playwright, network blocked except the static site: **7 passed**. They
  ran three times: locally, on GitHub Pages before teardown, and on GitHub Pages
  **after teardown**. The tests cover:
  - the sandbox banner, the forecast and schedule computed in the browser, and resolving
    after changes to battery, tariff, and reserve;
  - the synthetic-day label;
  - the recorded agent run and the template for an unrecorded scenario;
  - provenance on every view;
  - the explainer sections and the landing links.
- **Optimizer parity:** the browser optimizer against Python on 20 saved cases (both
  tariffs; ML, robust, hindsight; four battery sizes). Largest difference **0.00000
  percent** of cost (limit 0.5 percent).
- **ONNX parity**, first slice day: largest difference 0.00035 kW (P10); point 0.00013 kW.
- pytest 147 passed; live app Playwright 6 passed (synthetic snapshot); CI and the Pages
  workflow passed; public bundle scan 0 findings.

## 4. Key numbers

- **Recommendation**, from [../business_case.md](../business_case.md): do not buy a
  battery for this load profile. If one exists, run robust dispatch and fix the maximum
  demand guard before a pilot.
  - Base battery: frozen rule revise, with amendment A1 revise.
  - Robust on B-19: +3,198 to +37,363 USD per year before capital.
  - Best capital case: 30.8 year payback, NPV −829,491 USD.
- **Export manifest:** 40 tables. Zip SHA256 is in the release notes.

## 5. Deviations and why

1. **Live app MLflow traces did not upload.** Databricks Apps could not reach the workspace
   storage endpoint, so trace IDs exist but trace data does not. The Gate 6 report is
   corrected. The explainer's trace excerpts come from the final evaluation run, whose
   traces were stored; Lakebase call records cover the live runs.
2. **The UCI source zip (261 MB) is not re-hosted.** The release carries its manifest
   (source URL, DOI, SHA256) and the zip stays at its DOI; a 290 MB upload also timed out.
3. **Explainer code lives in `frontend/src/explainer/`**, not a top-level `explainer/`,
   because it shares the React tree and `node_modules`.
4. **Sandbox schedules are settled hourly in the browser**, without 15 minute billing or
   the charge guard (labelled). The results views show the full replay.
5. **Retained after teardown:**
   - MLflow experiments under `/Shared/edip/`, which hold run and trace evidence and use
     no compute;
   - the workspace's default Serverless Starter Warehouse, which this project did not
     create and which is stopped.

   The app finished deleting on its own (state DELETING at teardown).
6. **The demo video has captions, not narration.**

## 6. Open questions for the owner

1. Delete the retained MLflow experiments as well?
2. The business v3 format rule rejects A1's own wording ("does not beat both"), which
   lowers format compliance. Should "beat" in that phrase be allowed, as a new validator
   version with a new evaluation?

## 7. Exit checklist

| Item | Status |
|---|---|
| Both pages pass their tests after teardown | **Pass** (7 of 7 on GitHub Pages after teardown) |
| README states the headline finding, links both pages and the video, lists assumptions and limitations | **Pass** |
| Playwright on each public page with the network blocked except static assets | **Pass** |
| Browser optimizer matches Python on 20 saved cases within 0.5 percent | **Pass** (0.00000 percent) |
| Exports kept (release asset) and billable resources torn down | **Pass** |

Gate 7 complete.
