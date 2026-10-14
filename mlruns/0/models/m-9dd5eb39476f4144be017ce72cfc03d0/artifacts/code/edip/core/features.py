"""Forecast features (FR5, FR9). Every feature for target hour t uses load at t - 24 or older.

Decision time for planning day D is 00:00 UTC on D: all load before D is known, none on
or after it. Each target hour t in D (t = D + h, h = 0..23) therefore sees only load at
or before D - 1 h, because t - 24 <= D - 1 h. Calendar features come from the timestamp.
Hour of day and day of week use the Europe/Lisbon wall clock, where the load was metered.
"""

from __future__ import annotations

import pandas as pd

FEATURES = (
    "lag_24",
    "lag_168",
    "roll_mean_24_shift_24",
    "roll_mean_168_shift_24",
    "hour_local",
    "dow_local",
)
MIN_SHIFT_HOURS = 24
HISTORY_HOURS = 168 + MIN_SHIFT_HOURS  # longest look-back of any feature


def build_features(kw: pd.Series, clock: str = "Europe/Lisbon") -> pd.DataFrame:
    """Features indexed like `kw` (hourly, UTC hour_start, no gaps)."""
    expected = pd.date_range(kw.index[0], kw.index[-1], freq="h")
    if len(expected) != len(kw) or not (kw.index == expected).all():
        raise ValueError("hourly series must be complete and ordered")
    past = kw.shift(MIN_SHIFT_HOURS)  # value known at the decision time for every horizon
    local = kw.index.tz_localize("UTC").tz_convert(clock)
    return pd.DataFrame(
        {
            "lag_24": past,
            "lag_168": kw.shift(168),
            "roll_mean_24_shift_24": past.rolling(24, min_periods=24).mean(),
            "roll_mean_168_shift_24": past.rolling(168, min_periods=168).mean(),
            "hour_local": local.hour.astype("int32"),
            "dow_local": local.weekday.astype("int32"),
        },
        index=kw.index,
    )


def seasonal_baseline(kw: pd.Series) -> pd.Series:
    """Previous-week forecast (FR8): the load at the same hour seven days earlier."""
    return kw.shift(168).rename("seasonal_naive")
