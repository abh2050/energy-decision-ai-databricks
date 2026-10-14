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


def test_peak_within_one_hour():
    from edip.core.metrics import peak_within_one_hour_pct

    rows = []
    for d, (actual_peak, pred_peak) in enumerate([(14, 15), (14, 16), (3, 3)]):
        for h in range(24):
            rows.append(
                {
                    "decision_date": d,
                    "horizon_h": h,
                    "actual": 100 + (50 if h == actual_peak else 0),
                    "point": 100 + (50 if h == pred_peak else 0),
                }
            )
    assert peak_within_one_hour_pct(pd.DataFrame(rows), "point") == pytest.approx(200 / 3)


def test_months_peak_in_protected_window():
    from pathlib import Path

    from edip.core.metrics import months_peak_in_protected_window
    from edip.core.tariff import load_tariff

    b19 = load_tariff(Path(__file__).parents[2] / "config" / "tariffs" / "anchored_tou.yaml")
    hours = pd.date_range("2014-06-30 23:00", "2014-08-31 22:00", freq="h")  # Lisbon Jul-Aug
    kw = pd.Series(100.0, index=hours)
    kw[pd.Timestamp("2014-07-10 16:00")] = 900  # 17:00 Lisbon, B-19 summer peak
    kw[pd.Timestamp("2014-08-10 10:00")] = 900  # 11:00 Lisbon, off-peak
    result = months_peak_in_protected_window(kw, b19, ["peak"])
    assert result.months == 2 and result.months_in_window == 1
    assert [d.period for d in result.detail] == ["peak", "off_peak"]
    assert result.detail[0].local_hour == 17
