import numpy as np
import pandas as pd
import pytest
import yaml

from edip.core.features import FEATURES
from edip.forecasting.models import daily_frame, fit, make_dataset, predict_all, tune_point
from edip.forecasting.onnx_export import parity_max_abs_diff, to_onnx

with open("config/forecasting.yaml") as fh:
    CFG = yaml.safe_load(fh)
SMALL = {
    **CFG,
    "tuning": {
        **CFG["tuning"],
        "num_leaves": [15],
        "min_child_samples": [20],
        "max_estimators": 200,
        "early_stopping_rounds": 20,
    },
}


@pytest.fixture(scope="module")
def ds():
    idx = pd.date_range("2013-01-01", periods=24 * 120, freq="h")
    rng = np.random.default_rng(3)
    kw = (
        400
        + 150 * np.sin(2 * np.pi * (idx.hour - 6) / 24)
        + 60 * (idx.weekday < 5)
        + rng.normal(0, 15, len(idx))
    )
    split = np.where(
        idx < "2013-03-15", "train", np.where(idx < "2013-04-10", "validation", "test")
    )
    return make_dataset(pd.DataFrame({"hour_start": idx, "kw_mean": kw, "split": split}))


@pytest.fixture(scope="module")
def models(ds):
    tuned = tune_point(ds, SMALL)
    point = fit(ds, tuned.params, "l1", None, SMALL)
    quantiles = {a: fit(ds, tuned.params, "quantile", a, SMALL) for a in (0.1, 0.5, 0.9)}
    return tuned, point, quantiles


def test_dataset_drops_rows_without_full_history(ds):
    assert ds.X.notna().all().all()
    assert list(ds.X.columns) == list(FEATURES)
    assert ds.X.index[0] == pd.Timestamp("2013-01-08 23:00")  # 191 earlier hours needed


def test_tuning_uses_validation_only(models):
    tuned, point, _ = models
    assert tuned.trials and tuned.validation_mae_kw > 0
    assert point.n_estimators == tuned.best_iteration


def test_quantiles_are_ordered_and_daily_frame_complete(ds, models):
    _, point, quantiles = models
    preds, _ = predict_all(point, quantiles, ds.X)
    assert (preds.p10 <= preds.p50).all() and (preds.p50 <= preds.p90).all()
    frame = daily_frame(ds, preds, "test")
    assert (frame.groupby("decision_date").size() == 24).all()
    assert set(frame.horizon_h) == set(range(24))


def test_onnx_parity_on_1000_rows_below_0_01_kw(ds, models):
    _, point, quantiles = models
    X = ds.X.iloc[:1000]
    for model in [point, *quantiles.values()]:
        onx = to_onnx(model, len(FEATURES), CFG["onnx"]["target_opset"])
        assert parity_max_abs_diff(model, onx, X) < CFG["onnx"]["max_abs_diff_kw"]
