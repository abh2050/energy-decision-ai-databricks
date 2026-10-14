"""Billing demand for settlement (FR17, FR20, FR21).

The optimizer plans hourly battery power. Settlement bills demand the way each utility
measures it: from 15 minute actual load minus the hourly battery output held flat within
the hour, averaged over the tariff's demand interval (15 minutes for PG&E B-19, 30 minutes
for PGE Schedule 85). Grid draw is floored at zero because export is not allowed.

Series conventions: 15 minute readings are labelled by interval end (UTC); battery power
is labelled by hour start (UTC), positive for discharge and negative for charge; demand
intervals are labelled by interval start (UTC).
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from edip.core.tariff import DemandCharge, Tariff
from edip.core.units import INTERVAL


class NetLoad(BaseModel):
    intervals: int
    clipped_intervals: int  # flat hourly discharge above a 15 minute reading


def net_interval_load(
    load15_kw: pd.Series, battery_kw_hourly: pd.Series
) -> tuple[pd.Series, NetLoad]:
    """Grid draw per 15 minute interval: actual load minus the hour's flat battery output."""
    hour = (load15_kw.index - INTERVAL).floor("h")
    battery = battery_kw_hourly.reindex(hour).fillna(0.0).to_numpy()
    raw = load15_kw.to_numpy() - battery
    net = pd.Series(raw, index=load15_kw.index, name="grid_kw").clip(lower=0.0)
    return net, NetLoad(intervals=len(net), clipped_intervals=int((raw < 0).sum()))


def interval_demand(kw15: pd.Series, minutes: int) -> pd.Series:
    """Average kW over aligned demand intervals of `minutes`, labelled by interval start.

    Only complete intervals count (two readings for 30 minutes, one for 15 minutes).
    """
    if minutes % 15:
        raise ValueError("demand interval must be a multiple of 15 minutes")
    start = kw15.index - INTERVAL
    groups = kw15.groupby(start.floor(f"{minutes}min"))
    demand = groups.mean()[groups.count() == minutes // 15]
    demand.index.name = "interval_start_utc"
    return demand


def local_month(index: pd.DatetimeIndex, clock: str) -> pd.PeriodIndex:
    idx = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return idx.tz_convert(clock).tz_localize(None).to_period("M")


def monthly_billing_demand(tariff: Tariff, charge: DemandCharge, demand: pd.Series) -> pd.Series:
    """Highest interval demand inside the charge's window, per local billing month."""
    in_window = tariff.in_demand_window(charge, demand.index).to_numpy()
    windowed = demand[in_window]
    return windowed.groupby(local_month(windowed.index, tariff.clock)).max()


def monthly_demand_all_hours(demand: pd.Series, clock: str) -> pd.Series:
    """Highest interval demand per local month at any hour (PGE monthly Demand)."""
    return demand.groupby(local_month(demand.index, clock)).max()


def facility_capacity_kw(
    monthly_demand: pd.Series, billed_months: pd.PeriodIndex, lookback: int = 12, top_n: int = 2
) -> pd.Series:
    """Average of the `top_n` greatest non-zero monthly Demands in the `lookback` months
    that include and end with each billed month (PGE Rule B). Every billed month needs a
    full window of history; the caller seeds months before the replay."""
    out = {}
    for month in billed_months:
        window = pd.period_range(month - (lookback - 1), month, freq="M")
        missing = window.difference(monthly_demand.index)
        if len(missing):
            raise ValueError(f"{month}: no Demand history for {[str(m) for m in missing]}")
        values = monthly_demand.reindex(window)
        values = values[values > 0].nlargest(top_n)
        out[month] = float(values.mean()) if len(values) else 0.0
    return pd.Series(out, name="facility_capacity_kw")
