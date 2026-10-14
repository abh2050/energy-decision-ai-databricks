import pandas as pd
import pytest

from edip.core.units import interval_kwh, to_hourly


def _series(values, start="2012-01-01 00:15"):
    idx = pd.date_range(start, periods=len(values), freq="15min")
    return pd.Series(values, index=idx, dtype=float)


def test_four_readings_of_100_kw_make_100_kwh():
    hourly = to_hourly(_series([100, 100, 100, 100]))
    assert len(hourly) == 1
    row = hourly.iloc[0]
    assert row["kwh"] == 100.0
    assert row["kw_mean"] == 100.0
    assert hourly.index[0] == pd.Timestamp("2012-01-01 00:00")


def test_interval_kwh_divides_by_four():
    assert interval_kwh(_series([40.0])).iloc[0] == 10.0


def test_kwh_equals_mean_kw_for_one_hour():
    hourly = to_hourly(_series([10, 20, 30, 40]))
    assert hourly.iloc[0]["kwh"] == pytest.approx(25.0)
    assert hourly.iloc[0]["kw_mean"] == pytest.approx(25.0)


def test_incomplete_hour_is_dropped():
    hourly = to_hourly(_series([1, 1, 1, 1, 1, 1]))
    assert list(hourly.index) == [pd.Timestamp("2012-01-01 00:00")]


def test_rejects_unsorted_index():
    s = _series([1, 2, 3, 4]).iloc[::-1]
    with pytest.raises(ValueError):
        to_hourly(s)
