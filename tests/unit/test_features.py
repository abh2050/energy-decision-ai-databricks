import numpy as np
import pandas as pd
import pytest

from edip.core.features import FEATURES, HISTORY_HOURS, build_features, seasonal_baseline


def _series(days: int = 30, seed: int = 0) -> pd.Series:
    idx = pd.date_range("2014-01-01", periods=days * 24, freq="h")
    rng = np.random.default_rng(seed)
    daily = 300 + 100 * np.sin(2 * np.pi * idx.hour / 24)
    return pd.Series(daily + rng.normal(0, 10, len(idx)), index=idx)


def test_leakage_future_values_never_change_features():
    """Shift the target forward (replace every value from the decision time on) and confirm
    no feature for the planning day moves: features use nothing after the decision time."""
    kw = _series()
    decision = pd.Timestamp("2014-01-20 00:00")
    day = pd.date_range(decision, periods=24, freq="h")
    base = build_features(kw).loc[day]

    for shift in (1, 24, 168):
        tampered = kw.copy()
        future = tampered.index >= decision
        tampered[future] = kw.shift(-shift)[future].fillna(0) * 7 + 1000
        assert build_features(tampered).loc[day].equals(base), shift


def test_leakage_feature_correlation_with_future_is_zero_on_white_noise():
    """On white noise, no feature may correlate with the value at its own target hour."""
    idx = pd.date_range("2014-01-01", periods=24 * 400, freq="h")
    noise = pd.Series(np.random.default_rng(1).normal(size=len(idx)), index=idx)
    feats = build_features(noise).dropna()
    target = noise.loc[feats.index]
    for col in ("lag_24", "lag_168", "roll_mean_24_shift_24", "roll_mean_168_shift_24"):
        assert abs(np.corrcoef(feats[col], target)[0, 1]) < 0.05, col


def test_lags_and_rolling_values():
    kw = _series()
    feats = build_features(kw)
    t = pd.Timestamp("2014-01-20 13:00")
    assert feats.loc[t, "lag_24"] == kw.loc[t - pd.Timedelta(hours=24)]
    assert feats.loc[t, "lag_168"] == kw.loc[t - pd.Timedelta(hours=168)]
    window = kw.loc[t - pd.Timedelta(hours=47) : t - pd.Timedelta(hours=24)]
    assert feats.loc[t, "roll_mean_24_shift_24"] == pytest.approx(window.mean())
    assert list(feats.columns) == list(FEATURES)
    assert feats.iloc[HISTORY_HOURS - 1 :].dropna().shape[0] > 0
    assert feats.iloc[: HISTORY_HOURS - 1]["roll_mean_168_shift_24"].isna().all()


def test_calendar_uses_lisbon_clock():
    idx = pd.DatetimeIndex([pd.Timestamp("2014-07-14 15:00"), pd.Timestamp("2014-01-13 15:00")])
    kw = pd.Series([1.0, 1.0], index=idx)
    full = kw.reindex(pd.date_range(idx.min(), idx.max(), freq="h")).fillna(1.0)
    feats = build_features(full).loc[idx]
    assert feats.loc["2014-07-14 15:00", "hour_local"] == 16  # summer, UTC+1
    assert feats.loc["2014-01-13 15:00", "hour_local"] == 15  # winter, UTC+0
    assert feats.loc["2014-07-14 15:00", "dow_local"] == 0  # Monday


def test_rejects_gaps():
    kw = _series().drop(pd.Timestamp("2014-01-05 03:00"))
    with pytest.raises(ValueError):
        build_features(kw)


def test_seasonal_baseline_is_previous_week():
    kw = _series()
    t = pd.Timestamp("2014-01-20 05:00")
    assert seasonal_baseline(kw).loc[t] == kw.loc[t - pd.Timedelta(days=7)]
