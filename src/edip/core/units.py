"""Unit conversion for 15 minute load readings (FR3).

UCI readings are the average kW over each 15 minute interval, labelled by the interval
end. Interval energy is kW / 4. Hours are labelled by their start (hour beginning).
"""

from __future__ import annotations

import pandas as pd

INTERVALS_PER_HOUR = 4
INTERVAL = pd.Timedelta(minutes=15)


def interval_kwh(kw: pd.Series) -> pd.Series:
    """Energy in each 15 minute interval from its average kW."""
    return kw / INTERVALS_PER_HOUR


def to_hourly(kw: pd.Series) -> pd.DataFrame:
    """Aggregate interval-end labelled 15 minute kW to hour-beginning rows.

    Returns columns kw_mean (average kW over the hour), kwh (energy in the hour), and
    n_intervals. Hours without all four intervals are dropped, never padded.
    """
    if not kw.index.is_monotonic_increasing or kw.index.has_duplicates:
        raise ValueError("index must be strictly increasing")
    hour = (kw.index - INTERVAL).floor("h")
    grouped = kw.groupby(hour)
    out = pd.DataFrame(
        {
            "kw_mean": grouped.mean(),
            "kwh": interval_kwh(kw).groupby(hour).sum(),
            "n_intervals": grouped.count(),
        }
    )
    out.index.name = "hour_start"
    return out[out["n_intervals"] == INTERVALS_PER_HOUR]
