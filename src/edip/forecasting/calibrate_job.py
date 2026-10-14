"""Gate 2 change: conformalized quantile regression on version 1, registered as version 2.

Wraps the version 1 boosters unchanged, fits one P10 to P90 correction per forecast hour
on the last three months of validation, measures validation and test coverage, adds the
peak timing metrics, and rewrites edip.curated.forecast_predictions for version 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml

from edip.core.calibration import apply_cqr, fit_cqr
from edip.core.features import FEATURES
from edip.core.metrics import (
    coverage,
    months_peak_in_protected_window,
    peak_within_one_hour_pct,
    pinball,
    score,
)
from edip.core.tariff import load_tariff
from edip.forecasting.models import daily_frame, make_dataset

QCOLS = ["p10", "p50", "p90"]


def config_hash(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def predict_with(boosters: dict[str, lgb.Booster], X: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"point": boosters["point"].predict(X[list(FEATURES)])}, index=X.index)
    q = np.sort(np.column_stack([boosters[k].predict(X[list(FEATURES)]) for k in QCOLS]), axis=1)
    for i, k in enumerate(QCOLS):
        out[k] = q[:, i]
    return out


def band_metrics(frame: pd.DataFrame, lo: str, hi: str) -> dict[str, float]:
    return {
        "coverage_pct": coverage(frame.actual, frame[lo], frame[hi]),
        "pinball_p10_kw": pinball(frame.actual, frame[lo], 0.1),
        "pinball_p90_kw": pinball(frame.actual, frame[hi], 0.9),
        "mean_width_kw": float((frame[hi] - frame[lo]).mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/forecasting.yaml")
    parser.add_argument("--tariffs", default="config/tariffs")
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--out", default="/Volumes/edip/ml/artifacts/gate2")
    args = parser.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    cal_cfg = cfg["calibration"]

    import mlflow
    from mlflow.models import infer_signature
    from pyspark.sql import SparkSession

    from edip.forecasting import pyfunc_model

    spark = SparkSession.builder.getOrCreate()
    mlflow.set_registry_uri("databricks-uc")
    model_name = cfg["registry"]["model_name"]
    base_version = cal_cfg["base_model_version"]

    work = Path(tempfile.mkdtemp())
    base_dir = Path(
        mlflow.artifacts.download_artifacts(
            artifact_uri=f"models:/{model_name}/{base_version}", dst_path=str(work / "v1")
        )
    )
    files = {k: next(base_dir.rglob(f"{k}.txt")) for k in ("point", *QCOLS)}
    boosters = {k: lgb.Booster(model_file=str(p)) for k, p in files.items()}

    obs = spark.table(f"{args.catalog}.curated.load_observations").toPandas()
    dataset_sha = obs["dataset_sha256"].iloc[0]
    ds = make_dataset(obs[["hour_start", "kw_mean", "split"]])
    preds = predict_with(boosters, ds.X)

    v1 = spark.table(f"{args.catalog}.curated.forecast_predictions").toPandas()
    v1 = v1[v1.model_version == base_version].set_index("target_hour")
    repro = float((v1[QCOLS] - preds.loc[v1.index, QCOLS]).abs().max().max())

    frames = {s: daily_frame(ds, preds, s) for s in ("validation", "test")}
    start, end = (pd.Timestamp(t) for t in cal_cfg["window"])
    val = frames["validation"]
    cal = val[(val.target_hour >= start) & (val.target_hour < end)]
    cqr = fit_cqr(cal, cal_cfg["target_coverage"], start.isoformat(), end.isoformat())
    for frame in frames.values():
        frame["p10_raw"], frame["p90_raw"] = frame.p10, frame.p90
        lo, hi = apply_cqr(frame.p10, frame.p50, frame.p90, frame.horizon_h, cqr)
        frame["p10"], frame["p90"] = lo, hi

    tariffs_dir = Path(args.tariffs)
    tariffs = {
        "pge_b19_secondary": load_tariff(tariffs_dir / "anchored_tou.yaml"),
        "pgn_sched85_secondary": load_tariff(tariffs_dir / "low_spread_tou.yaml"),
    }
    results: dict[str, Any] = {
        "model_name": model_name,
        "base_version": base_version,
        "v1_reproduction_max_abs_diff_kw": repro,
        "calibration": cqr.model_dump(),
        "calibration_rows": len(cal),
        "calibration_days": int(cal.decision_date.nunique()),
        "dataset_sha256": dataset_sha,
        "config_hash": config_hash(cfg),
        "splits": {},
    }
    for split, frame in frames.items():
        part: dict[str, Any] = {
            "days": int(frame.decision_date.nunique()),
            "band_raw": band_metrics(frame, "p10_raw", "p90_raw"),
            "band_calibrated": band_metrics(frame, "p10", "p90"),
            "calibrated_score": score(
                frame.drop(columns=["p10_raw", "p90_raw"]), "lgbm_cqr_p50", "p50"
            ).model_dump(),
            "peak_within_one_hour_pct": {
                "seasonal_naive": peak_within_one_hour_pct(frame, "seasonal"),
                "lgbm_point": peak_within_one_hour_pct(frame, "point"),
                "lgbm_p50": peak_within_one_hour_pct(frame, "p50"),
            },
            "coverage_by_hour_calibrated_pct": {
                int(h): coverage(g.actual, g.p10, g.p90) for h, g in frame.groupby("horizon_h")
            },
        }
        actual = pd.Series(frame.actual.to_numpy(), index=pd.DatetimeIndex(frame.target_hour))
        part["months_peak_in_protected_window"] = {
            tid: months_peak_in_protected_window(
                actual, t, cfg["robust_protected_periods"][tid]
            ).model_dump()
            for tid, t in tariffs.items()
        }
        results["splits"][split] = part

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cqr_corrections.json").write_text(cqr.model_dump_json(indent=2))

    mlflow.set_experiment("/Shared/edip/gate2_forecasting")
    with mlflow.start_run(run_name="gate2-cqr") as run:
        mlflow.set_tags(
            {
                "gate": "2",
                "change": "conformalized quantile regression",
                "base_model_version": base_version,
                "dataset_sha256": dataset_sha,
                "config_hash": results["config_hash"],
                "mlflow_version": mlflow.__version__,
            }
        )
        for split, part in results["splits"].items():
            for k, v in part["band_calibrated"].items():
                mlflow.log_metric(f"{split}_calibrated_{k}", v)
            for k, v in part["band_raw"].items():
                mlflow.log_metric(f"{split}_raw_{k}", v)
        mlflow.log_dict(results, "calibration_results.json")

        art = dict(files)
        cqr_path = work / "cqr.json"
        cqr_path.write_text(cqr.model_dump_json())
        art = {k: str(p) for k, p in art.items()} | {"cqr": str(cqr_path)}
        sample = ds.X.iloc[:50].copy()
        sample["horizon_h"] = sample.index.hour
        example_out = preds.iloc[:50][["point", *QCOLS]]
        where = (
            {"name": "load_forecaster"}
            if int(mlflow.__version__.split(".")[0]) >= 3
            else {"artifact_path": "load_forecaster"}
        )
        info = mlflow.pyfunc.log_model(
            **where,
            python_model=pyfunc_model.LoadForecaster(),
            artifacts=art,
            signature=infer_signature(sample, example_out),
            input_example=sample.iloc[:5],
            code_paths=[str(Path(pyfunc_model.__file__).parents[1])],
            pip_requirements=["lightgbm==4.7.0", "pandas==2.3.3", "numpy==2.3.5"],
            registered_model_name=model_name,
        )
        version = str(info.registered_model_version)
        run_id = run.info.run_id
    shutil.rmtree(work, ignore_errors=True)

    rows = pd.concat([f.assign(split=s) for s, f in frames.items()], ignore_index=True)
    rows["model_name"] = model_name
    rows["model_version"] = version
    rows["mlflow_run_id"] = run_id
    spark.createDataFrame(rows).write.mode("overwrite").option(
        "overwriteSchema", "true"
    ).saveAsTable(f"{args.catalog}.curated.forecast_predictions")
    results |= {"model_version": version, "mlflow_run_id": run_id}
    (out / "calibration_results.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "model_version": version,
                "test_coverage": results["splits"]["test"]["band_calibrated"]["coverage_pct"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
