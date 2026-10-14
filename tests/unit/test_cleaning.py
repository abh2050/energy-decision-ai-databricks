from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from edip.core.cleaning import (
    activation_time,
    check_dst_day,
    drop_pre_activation,
    march_change_day,
    october_change_day,
    to_standard_time,
)
from edip.core.units import to_hourly

LISBON = ZoneInfo("Europe/Lisbon")


def _day_series(day: str, value: float = 10.0) -> pd.Series:
    """Wall-clock labels for one local day plus the next midnight, like UCI rows."""
    idx = pd.date_range(f"{day} 00:15", periods=96, freq="15min")
    return pd.Series(value, index=idx, dtype=float)


@pytest.mark.parametrize("year", [2012, 2013, 2014])
def test_change_days_match_lisbon_timezone(year):
    mar, octo = march_change_day(year), october_change_day(year)
    noon = lambda d: pd.Timestamp(f"{d} 12:00", tz=LISBON).utcoffset()  # noqa: E731
    before = lambda d: pd.Timestamp(f"{d} 00:30", tz=LISBON).utcoffset()  # noqa: E731
    assert before(mar) == pd.Timedelta(0) and noon(mar) == pd.Timedelta(hours=1)
    assert before(octo) == pd.Timedelta(hours=1) and noon(octo) == pd.Timedelta(0)


def test_known_change_days():
    assert march_change_day(2013) == date(2013, 3, 31)
    assert october_change_day(2013) == date(2013, 10, 27)


def test_march_placeholder_rows_dropped_and_day_has_24_hours():
    # 2013-03-31: wall-clock 01:00-01:45 do not exist and hold zeros.
    s = pd.concat([_day_series("2013-03-30"), _day_series("2013-03-31"), _day_series("2013-04-01")])
    s = s[~s.index.duplicated()]
    for t in ("01:00", "01:15", "01:30", "01:45"):
        s[pd.Timestamp(f"2013-03-31 {t}")] = 0.0
    assert check_dst_day(s, date(2013, 3, 31), "march").placeholder_zero

    std = to_standard_time(s, [2013])
    assert (std == 10.0).all()  # every placeholder zero removed
    assert len(s) - len(std) == 4
    steps = std.index.to_series().diff().dropna()
    assert (steps == pd.Timedelta(minutes=15)).all()  # no gap in standard time
    hourly = to_hourly(std)
    day = hourly.loc["2013-03-31"]
    assert len(day) == 24
    assert day["kwh"].sum() == pytest.approx(24 * 10.0)


def test_october_doubled_hour_split_preserves_energy():
    # 2013-10-27: wall-clock 01:00-01:45 occur twice and hold both hours.
    s = pd.concat([_day_series("2013-10-26"), _day_series("2013-10-27"), _day_series("2013-10-28")])
    s = s[~s.index.duplicated()]
    for t in ("01:00", "01:15", "01:30", "01:45"):
        s[pd.Timestamp(f"2013-10-27 {t}")] = 20.0
    check = check_dst_day(s, date(2013, 10, 27), "october")
    assert check.doubling_ratio == pytest.approx(2.0)

    std = to_standard_time(s, [2013])
    assert len(std) - len(s) == 4
    assert std.sum() == pytest.approx(s.sum())  # energy preserved
    assert (std == 10.0).all()
    steps = std.index.to_series().diff().dropna()
    assert (steps == pd.Timedelta(minutes=15)).all()
    day = to_hourly(std).loc["2013-10-27"]
    assert len(day) == 24


def test_summer_labels_shift_back_one_hour():
    s = _day_series("2013-07-01")
    std = to_standard_time(s, [2013])
    assert std.index[0] == pd.Timestamp("2013-06-30 23:15")


def test_activation_drops_leading_zeros_only():
    idx = pd.date_range("2012-01-01 00:15", periods=6, freq="15min")
    s = pd.Series([0, 0, 5, 0, 6, 7], index=idx, dtype=float)
    assert activation_time(s) == idx[2]
    assert list(drop_pre_activation(s)) == [5, 0, 6, 7]
    assert drop_pre_activation(pd.Series([0.0, 0.0], index=idx[:2])).empty
