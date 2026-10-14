"""Gate 2 Databricks job: tune, fit, forecast, score, export, register (FR8 to FR13).

Reads edip.curated.load_observations. Writes edip.curated.forecast_features,
edip.curated.forecast_predictions, ONNX files and results.json in the edip.ml.artifacts
volume, an MLflow run tagged with dataset_sha256 and config_hash, and a Unity Catalog
model version of edip.ml.load_forecaster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from edip.core.features import FEATURES
from edip.core.metrics import score
from edip.forecasting.models import (
    QUANTILE_COLUMNS,
    daily_frame,
    fit,
    make_dataset,
    predict_all,
    tune_point,
)
from edip.forecasting.onnx_export import parity_max_abs_diff, to_onnx


def config_hash(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/forecasting.yaml")
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--out", default="/Volumes/edip/ml/artifacts/gate2")
    args = parser.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    cfg_hash = config_hash(cfg)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    obs = spark.table(f"{args.catalog}.curated.load_observations").toPandas()
    dataset_sha = obs["dataset_sha256"].iloc[0]
    client = obs["client_id"].iloc[0]
    ds = make_dataset(obs[["hour_start", "kw_mean", "split"]])

    tuned = tune_point(ds, cfg)
    point = fit(ds, tuned.params, "l1", None, cfg)
    quantiles = {a: fit(ds, tuned.params, "quantile", a, cfg) for a in cfg["quantiles"]}
    preds, crossings = predict_all(point, quantiles, ds.X)

    scores = {}
    frames = {}
    for split in ("validation", "test"):
        frame = daily_frame(ds, preds, split)
        frames[split] = frame
        scores[split] = [
            score(
                frame.drop(columns=list(QUANTILE_COLUMNS.values())), "seasonal_naive", "seasonal"
            ),
            score(frame.drop(columns=list(QUANTILE_COLUMNS.values())), "lgbm_point", "point"),
            score(frame, "lgbm_quantile_p50", "p50"),
        ]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    parity_rows = ds.X[ds.split == "test"].iloc[: cfg["onnx"]["parity_rows"]]
    named = {"point": point, **{QUANTILE_COLUMNS[a]: m for a, m in quantiles.items()}}
    parity = {}
    for name, model in named.items():
        onx = to_onnx(model, len(FEATURES), cfg["onnx"]["target_opset"])
        (out / f"load_forecaster_{name}.onnx").write_bytes(onx)
        parity[name] = parity_max_abs_diff(model, onx, parity_rows)
    parity_passed = all(v < cfg["onnx"]["max_abs_diff_kw"] for v in parity.values())
    (out / "feature_spec.json").write_text(
        json.dumps({"features": list(FEATURES), "dtype": "float32", "clock": "Europe/Lisbon"})
    )

    import mlflow
    from mlflow.models import infer_signature

    from edip.forecasting import pyfunc_model

    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment("/Shared/edip/gate2_forecasting")
    with mlflow.start_run(run_name="gate2-forecasters") as run:
        mlflow.set_tags(
            {
                "gate": "2",
                "dataset_sha256": dataset_sha,
                "config_hash": cfg_hash,
                "client_id": client,
            }
        )
        mlflow.log_params(
            {
                **{k: v for k, v in tuned.params.items() if k != "n_estimators"},
                "point_trees": point.n_estimators,
                **{f"{QUANTILE_COLUMNS[a]}_trees": m.n_estimators for a, m in quantiles.items()},
                "features": ",".join(FEATURES),
            }
        )
        for split, rows in scores.items():
            for s in rows:
                mlflow.log_metric(f"{split}_{s.forecaster}_mae_kw", s.mae_kw)
                mlflow.log_metric(f"{split}_{s.forecaster}_mape_pct", s.mape_pct)
                if s.p10_p90_coverage_pct is not None:
                    mlflow.log_metric(f"{split}_coverage_pct", s.p10_p90_coverage_pct)
                    mlflow.log_metric(f"{split}_pinball_mean_kw", s.pinball_kw["mean"])
        for name, diff in parity.items():
            mlflow.log_metric(f"onnx_parity_max_abs_diff_kw_{name}", diff)
        mlflow.log_metric("quantile_crossing_rows", crossings)
        mlflow.log_dict(tuned.model_dump(), "tuning.json")
        for f in out.glob("*.onnx"):
            mlflow.log_artifact(str(f), "onnx")

        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            for name, model in named.items():
                path = Path(tmp) / f"{name}.txt"
                model.booster_.save_model(str(path))
                files[name] = str(path)
            sample = ds.X.iloc[:50]
            signature = infer_signature(sample, preds[["point", "p10", "p50", "p90"]].iloc[:50])
            info = mlflow.pyfunc.log_model(
                name="load_forecaster",
                python_model=pyfunc_model.LoadForecaster(),
                artifacts=files,
                signature=signature,
                input_example=sample.iloc[:5],
                code_paths=[str(Path(pyfunc_model.__file__).parents[1])],
                pip_requirements=["lightgbm==4.7.0", "pandas==2.3.3", "numpy==2.3.5"],
                registered_model_name=cfg["registry"]["model_name"],
            )
        version = info.registered_model_version
        run_id = run.info.run_id

    feats = ds.X.copy()
    feats["split"] = ds.split
    feats = feats.reset_index().rename(columns={"index": "hour_start"})
    feats["dataset_sha256"] = dataset_sha
    spark.createDataFrame(feats).write.mode("overwrite").option(
        "overwriteSchema", "true"
    ).saveAsTable(f"{args.catalog}.curated.forecast_features")

    predictions = pd.concat([f.assign(split=s) for s, f in frames.items()], ignore_index=True)
    predictions["model_name"] = cfg["registry"]["model_name"]
    predictions["model_version"] = str(version)
    predictions["mlflow_run_id"] = run_id
    spark.createDataFrame(predictions).write.mode("overwrite").option(
        "overwriteSchema", "true"
    ).saveAsTable(f"{args.catalog}.curated.forecast_predictions")

    results = {
        "client_id": client,
        "dataset_sha256": dataset_sha,
        "config_hash": cfg_hash,
        "mlflow_run_id": run_id,
        "model_name": cfg["registry"]["model_name"],
        "model_version": str(version),
        "tuning": tuned.model_dump(),
        "trees": {"point": point.n_estimators}
        | {QUANTILE_COLUMNS[a]: m.n_estimators for a, m in quantiles.items()},
        "quantile_crossing_rows": crossings,
        "onnx_parity_max_abs_diff_kw": parity,
        "onnx_parity_passed": parity_passed,
        "scores": {k: [s.model_dump() for s in v] for k, v in scores.items()},
    }
    (out / "results.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(json.dumps({"model_version": str(version), "parity_passed": parity_passed}))
    return 0 if parity_passed else 1


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
