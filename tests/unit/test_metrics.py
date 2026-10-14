import pandas as pd
import pytest

from edip.core.metrics import coverage, mae, mape, peak_error, pinball, score


def _frame():
    rows = []
    for d, date in enumerate(["2014-01-01", "2014-01-02"]):
        for h in range(3):
            actual = [100, 300, 200][h] + d
            rows.append(
                {
                    "decision_date": date,
                    "horizon_h": h,
                    "actual": actual,
                    "point": actual + 10,
                    "p10": actual - 20,
                    "p50": actual + 10,
                    "p90": actual + (5 if h else -5),
                }
            )
    return pd.DataFrame(rows)


def test_basic_metrics():
    a, p = pd.Series([100.0, 200.0]), pd.Series([110.0, 180.0])
    assert mae(a, p) == 15
    assert mape(a, p) == pytest.approx((10 + 10) / 2)
    assert mape(pd.Series([0.0, 100.0]), pd.Series([5.0, 110.0])) == pytest.approx(
        10
    )  # zero skipped


def test_pinball_is_asymmetric():
    a = pd.Series([100.0])
    assert pinball(a, pd.Series([90.0]), 0.9) == pytest.approx(9.0)  # under-forecast
    assert pinball(a, pd.Series([110.0]), 0.9) == pytest.approx(1.0)  # over-forecast


def test_coverage_counts_inclusive_band():
    a = pd.Series([1.0, 5.0, 9.0])
    assert coverage(a, pd.Series([0.0, 5.0, 10.0]), pd.Series([2.0, 6.0, 12.0])) == pytest.approx(
        200 / 3
    )


def test_peak_error_uses_actual_peak_hour():
    pe = peak_error(_frame(), "point")
    assert pe.mean_abs_error_at_actual_peak_kw == 10
    assert pe.mean_abs_peak_magnitude_error_kw == 10
    assert pe.peak_hour_hit_rate_pct == 100


def test_score_with_quantiles():
    s = score(_frame(), "lgbm_quantile", "p50")
    assert s.days == 2 and s.hours == 6
    assert len(s.by_horizon) == 3
    assert s.p10_p90_coverage_pct == pytest.approx(200 / 3)  # horizon 0 misses (p90 below actual)
    assert set(s.pinball_kw) == {"p10", "p50", "p90", "mean"}
    point_only = _frame().drop(columns=["p10", "p50", "p90"])
    assert score(point_only, "seasonal", "point").pinball_kw is None
