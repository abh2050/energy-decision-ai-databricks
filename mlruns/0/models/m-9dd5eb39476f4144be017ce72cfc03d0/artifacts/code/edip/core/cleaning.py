"""Daylight saving and activation cleaning for UCI load readings (FR4).

UCI labels readings with Portuguese wall-clock time (Europe/Lisbon). On the March change
day the wall-clock labels 01:00 to 01:45 do not exist and hold zero placeholders; on the
October change day the same labels occur twice and hold the consumption of both hours.
Observed in the data: the pattern holds in 2012 to 2014 (not 2011) for most clients.

Output is UTC (Portugal's standard time, WET, equals UTC): every day has 24 hours and
energy is preserved. Placeholder rows are dropped and doubled rows are split in half.
Tariff periods are later assigned from the Europe/Lisbon wall clock (edip.core.tariff).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from pydantic import BaseModel

BLOCK_LABELS = ("01:00", "01:15", "01:30", "01:45")
ONE_HOUR = pd.Timedelta(hours=1)


def last_sunday(year: int, month: int) -> date:
    first_next = date(year + (month == 12), month % 12 + 1, 1)
    last = first_next - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - 6) % 7)


def march_change_day(year: int) -> date:
    return last_sunday(year, 3)


def october_change_day(year: int) -> date:
    return last_sunday(year, 10)


def block_index(day: date) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(f"{day} {t}") for t in BLOCK_LABELS])


class DstDayCheck(BaseModel):
    day: date
    kind: str  # "march" or "october"
    rows_present: int
    placeholder_zero: bool | None = None  # march: all four block rows are zero
    doubling_ratio: float | None = None  # october: block mean / neighbouring hours mean


def check_dst_day(kw: pd.Series, day: date, kind: str) -> DstDayCheck:
    block = kw.reindex(block_index(day))
    present = int(block.notna().sum())
    if kind == "march":
        return DstDayCheck(
            day=day, kind=kind, rows_present=present, placeholder_zero=bool((block == 0).all())
        )
    before = kw.loc[pd.Timestamp(f"{day} 00:00") : pd.Timestamp(f"{day} 00:45")]
    after = kw.loc[pd.Timestamp(f"{day} 02:00") : pd.Timestamp(f"{day} 02:45")]
    neighbours = pd.concat([before, after]).mean()
    ratio = float(block.mean() / neighbours) if neighbours > 0 else None
    return DstDayCheck(day=day, kind=kind, rows_present=present, doubling_ratio=ratio)


def to_utc(kw: pd.Series, years: list[int]) -> pd.Series:
    """Convert Europe/Lisbon wall-clock labelled readings to UTC labels.

    Applies the DST correction only for `years`, the years in which the data shows the
    documented artifacts. The caller verifies the artifacts with `check_dst_day` first.
    """
    out = kw.copy()
    for year in years:
        mar, octo = march_change_day(year), october_change_day(year)
        out = out.drop(index=block_index(mar), errors="ignore")
        summer = (out.index >= pd.Timestamp(f"{mar} 02:00")) & (
            out.index < pd.Timestamp(f"{octo} 01:00")
        )
        doubled = out.index.isin(block_index(octo))
        first = out[doubled] / 2  # first occurrence, still summer time
        first.index = first.index - ONE_HOUR
        second = out[doubled] / 2  # second occurrence, standard time
        shifted = out[~doubled].copy()
        shifted.index = shifted.index.where(~summer[~doubled], shifted.index - ONE_HOUR)
        out = pd.concat([shifted, first, second]).sort_index()
    if out.index.has_duplicates:
        raise ValueError("duplicate timestamps after DST correction")
    return out


def activation_time(kw: pd.Series) -> pd.Timestamp | None:
    """First reading above zero; earlier zeros mean the client was not yet connected."""
    positive = kw[kw > 0]
    return positive.index[0] if len(positive) else None


def drop_pre_activation(kw: pd.Series) -> pd.Series:
    start = activation_time(kw)
    return kw.iloc[0:0] if start is None else kw.loc[start:]
