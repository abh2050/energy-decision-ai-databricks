import pandas as pd
import pytest

from edip.core.eligibility import monthly_max_demand, pge_b19, pgn_schedule_85

CLOCK = "Europe/Lisbon"


def _series(months: int, base: float, spikes: dict[int, float] | None = None) -> pd.Series:
    """Interval-end labelled 15 minute kW, one spike pair per listed month index."""
    idx = pd.date_range("2012-01-01 00:15", periods=months * 31 * 96, freq="15min")
    idx = idx[idx < pd.Timestamp("2012-01-01") + pd.DateOffset(months=months)]
    s = pd.Series(base, index=idx)
    for m, kw in (spikes or {}).items():
        t = pd.Timestamp("2012-01-10 12:15") + pd.DateOffset(months=m)
        s[t] = kw
        s[t + pd.Timedelta(minutes=15)] = kw
    return s


def test_thirty_minute_demand_averages_two_readings():
    s = _series(1, 100.0)
    s[pd.Timestamp("2012-01-05 10:15")] = 300.0  # one 15 minute reading only
    m30 = monthly_max_demand(s, 30, CLOCK)
    m15 = monthly_max_demand(s, 15, CLOCK)
    assert m30.iloc[0] == pytest.approx(200.0)
    assert m15.iloc[0] == pytest.approx(300.0)


def test_schedule_85_needs_more_than_six_months_above_200():
    seven = _series(13, 150.0, {m: 250.0 for m in range(7)})
    six = _series(13, 150.0, {m: 250.0 for m in range(6)})
    assert pgn_schedule_85(seven, CLOCK).passed
    result = pgn_schedule_85(six, CLOCK)
    assert not result.passed
    assert result.worst_window.months_above_min == 6


def test_schedule_85_allows_one_month_above_4000():
    once = _series(13, 300.0, {0: 4500.0})
    twice = _series(13, 300.0, {0: 4500.0, 5: 4500.0})
    assert pgn_schedule_85(once, CLOCK).passed
    assert not pgn_schedule_85(twice, CLOCK).passed


def test_b19_consecutive_months_and_cap():
    s = _series(12, 300.0, {2: 600.0, 3: 600.0, 4: 600.0})
    result, run = pge_b19(s, CLOCK)
    assert run == 3 and result.passed
    over, _ = pge_b19(_series(12, 300.0, {1: 1200.0}), CLOCK)
    assert not over.passed
