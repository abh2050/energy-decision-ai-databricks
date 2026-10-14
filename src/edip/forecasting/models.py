"""LightGBM point and quantile forecasters (FR9 to FR11). No Databricks code here."""

from __future__ import annotations

import itertools
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from pydantic import BaseModel

from edip.core.features import FEATURES, build_features, seasonal_baseline

QUANTILE_COLUMNS = {0.1: "p10", 0.5: "p50", 0.9: "p90"}


class Dataset(BaseModel):
    """Features, target, and split per hour (UTC hour_start index)."""

    model_config = {"arbitrary_types_allowed": True}
    X: pd.DataFrame
    y: pd.Series
    split: pd.Series
    seasonal: pd.Series


def make_dataset(hourly: pd.DataFrame) -> Dataset:
    """From load_observations rows (hour_start, kw_mean, split) for one client."""
    df = hourly.sort_values("hour_start").set_index("hour_start")
    y = df["kw_mean"].astype(float)
    feats = build_features(y)
    ok = feats.notna().all(axis=1)
    # Round features to float32 so split thresholds are learned on values the ONNX model
    # (float32 inputs, used in the browser) sees identically; otherwise a value near a
    # threshold can take a different branch (observed 0.38 kW parity error).
    return Dataset(
        X=feats[ok].astype("float32").astype("float64"),
        y=y[ok],
        split=df.loc[ok, "split"],
        seasonal=seasonal_baseline(y)[ok],
    )


class TuningResult(BaseModel):
    params: dict[str, Any]
    best_iteration: int
    validation_mae_kw: float
    trials: list[dict[str, Any]]


def _base_params(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "learning_rate": cfg["tuning"]["learning_rate"],
        "n_estimators": cfg["tuning"]["max_estimators"],
        "random_state": cfg["seed"],
        "deterministic": True,
        "force_row_wise": True,
        "n_jobs": 1,
        "verbose": -1,
    }


def tune_point(ds: Dataset, cfg: dict[str, Any]) -> TuningResult:
    """Grid search on validation MAE with early stopping on validation."""
    tr, va = ds.split == "train", ds.split == "validation"
    trials = []
    grid = itertools.product(cfg["tuning"]["num_leaves"], cfg["tuning"]["min_child_samples"])
    for leaves, child in grid:
        params = {**_base_params(cfg), "num_leaves": leaves, "min_child_samples": child}
        model = lgb.LGBMRegressor(objective="l1", **params)
        model.fit(
            ds.X[tr],
            ds.y[tr],
            eval_X=ds.X[va],
            eval_y=ds.y[va],
            eval_metric="l1",
            callbacks=[lgb.early_stopping(cfg["tuning"]["early_stopping_rounds"], verbose=False)],
        )
        pred = model.predict(ds.X[va], num_iteration=model.best_iteration_)
        trials.append(
            {
                "num_leaves": leaves,
                "min_child_samples": child,
                "best_iteration": int(model.best_iteration_),
                "validation_mae_kw": float(np.mean(np.abs(ds.y[va] - pred))),
            }
        )
    best = min(trials, key=lambda t: t["validation_mae_kw"])
    params = {
        **_base_params(cfg),
        "num_leaves": best["num_leaves"],
        "min_child_samples": best["min_child_samples"],
    }
    return TuningResult(
        params=params,
        best_iteration=best["best_iteration"],
        validation_mae_kw=best["validation_mae_kw"],
        trials=trials,
    )


def fit(
    ds: Dataset, params: dict[str, Any], objective: str, alpha: float | None, cfg: dict[str, Any]
) -> lgb.LGBMRegressor:
    """Fit on train, early-stop on validation, then cap trees at the best iteration."""
    tr, va = ds.split == "train", ds.split == "validation"
    extra = {"alpha": alpha} if alpha is not None else {}
    metric = "quantile" if objective == "quantile" else "l1"
    model = lgb.LGBMRegressor(objective=objective, **params, **extra)
    model.fit(
        ds.X[tr],
        ds.y[tr],
        eval_X=ds.X[va],
        eval_y=ds.y[va],
        eval_metric=metric,
        callbacks=[lgb.early_stopping(cfg["tuning"]["early_stopping_rounds"], verbose=False)],
    )
    # Refit exactly best_iteration trees so ONNX export and prediction agree.
    final = lgb.LGBMRegressor(
        objective=objective, **{**params, "n_estimators": int(model.best_iteration_)}, **extra
    )
    final.fit(ds.X[tr], ds.y[tr])
    return final


def predict_all(
    point: lgb.LGBMRegressor, quantiles: dict[float, lgb.LGBMRegressor], X: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    """Point and sorted quantile predictions; also returns the number of crossing rows."""
    out = pd.DataFrame({"point": point.predict(X[list(FEATURES)])}, index=X.index)
    raw = np.column_stack([quantiles[a].predict(X[list(FEATURES)]) for a in sorted(quantiles)])
    crossings = int((np.diff(raw, axis=1) < 0).any(axis=1).sum())
    ordered = np.sort(raw, axis=1)
    for i, a in enumerate(sorted(quantiles)):
        out[QUANTILE_COLUMNS[a]] = ordered[:, i]
    return out, crossings


def daily_frame(ds: Dataset, preds: pd.DataFrame, split: str) -> pd.DataFrame:
    """One row per (decision_date, horizon_h) for complete planning days in `split`."""
    idx = ds.X.index[ds.split == split]
    frame = pd.DataFrame(
        {
            "target_hour": idx,
            "decision_date": idx.normalize(),
            "horizon_h": idx.hour,
            "actual": ds.y.loc[idx].to_numpy(),
            "seasonal": ds.seasonal.loc[idx].to_numpy(),
        }
    )
    frame = frame.join(preds.loc[idx].reset_index(drop=True))
    complete = frame.groupby("decision_date")["horizon_h"].transform("size") == 24
    return frame[complete].reset_index(drop=True)
