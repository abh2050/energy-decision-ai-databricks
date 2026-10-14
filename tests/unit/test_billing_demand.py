from pathlib import Path

import pandas as pd
import pytest

from edip.core.billing_demand import (
    facility_capacity_kw,
    interval_demand,
    monthly_billing_demand,
    monthly_demand_all_hours,
    net_interval_load,
)
from edip.core.tariff import load_tariff

TARIFFS = Path(__file__).parents[2] / "config" / "tariffs"
B19 = load_tariff(TARIFFS / "anchored_tou.yaml")
PGN = load_tariff(TARIFFS / "low_spread_tou.yaml")


def _hour(start_utc: str, readings: list[float]) -> pd.Series:
    """Four interval-end labelled 15 minute readings for the hour starting at start_utc."""
    idx = pd.date_range(pd.Timestamp(start_utc) + pd.Timedelta(minutes=15), periods=4, freq="15min")
    return pd.Series(readings, index=idx, dtype=float)


def _battery(start_utc: str, kw: float) -> pd.Series:
    return pd.Series([kw], index=pd.DatetimeIndex([pd.Timestamp(start_utc)]))


def test_b19_bills_15_minute_net_demand():
    # Monday 2014-07-14, 16:00 UTC = 17:00 Lisbon, B-19 summer peak.
    load = _hour("2014-07-14 16:00", [500, 900, 500, 500])  # hourly mean 600 kW
    net, info = net_interval_load(load, _battery("2014-07-14 16:00", 100.0))
    assert list(net) == [400, 800, 400, 400]  # battery held flat at 100 kW in the hour
    assert info.clipped_intervals == 0
    demand = interval_demand(net, B19.demand_charges[0].tariff_interval_minutes)
    assert demand.max() == 800  # 15 minute peak, not the 500 kW hourly mean
    peak = next(c for c in B19.demand_charges if c.name == "Maximum peak demand")
    monthly = monthly_billing_demand(B19, peak, demand)
    assert monthly.loc[pd.Period("2014-07", "M")] == 800


def test_pgn_bills_30_minute_net_demand():
    load = _hour("2014-07-14 16:00", [500, 900, 500, 500])
    net, _ = net_interval_load(load, _battery("2014-07-14 16:00", 100.0))
    charge = PGN.demand_charges[0]
    assert charge.tariff_interval_minutes == 30
    demand = interval_demand(net, 30)
    assert list(demand) == [600, 400]  # (400 + 800) / 2 and (400 + 400) / 2
    assert monthly_billing_demand(PGN, charge, demand).iloc[0] == 600


def test_thirty_minute_intervals_are_aligned_and_complete():
    load = _hour("2014-07-14 16:00", [100, 300, 500, 700])
    demand = interval_demand(load, 30)
    assert list(demand.index.minute) == [0, 30]
    assert list(demand) == [200, 600]
    assert interval_demand(load.iloc[:3], 30).tolist() == [200]  # incomplete half hour dropped


def test_charging_raises_net_demand_and_discharge_is_floored_at_zero():
    load = _hour("2014-07-14 16:00", [50, 300, 300, 300])
    net, info = net_interval_load(load, _battery("2014-07-14 16:00", 100.0))
    assert list(net) == [0, 200, 200, 200]  # no export
    assert info.clipped_intervals == 1
    charging, _ = net_interval_load(load, _battery("2014-07-14 16:00", -100.0))
    assert list(charging) == [150, 400, 400, 400]


def test_pgn_peak_demand_window_ignores_sunday():
    sunday = _hour("2014-07-13 16:00", [900, 900, 900, 900])
    monday = _hour("2014-07-14 16:00", [300, 300, 300, 300])
    demand = interval_demand(pd.concat([sunday, monday]), 30)
    monthly = monthly_billing_demand(PGN, PGN.demand_charges[0], demand)
    assert monthly.iloc[0] == 300
    assert monthly_demand_all_hours(demand, PGN.clock).iloc[0] == 900  # Facility Capacity input


def test_facility_capacity_uses_seeded_twelve_months():
    seed = pd.Series(
        [500, 520, 480, 610, 590, 700, 650, 640, 600, 580, 560],
        index=pd.period_range("2013-02", "2013-12", freq="M"),
    )  # 11 months of no-battery Demand before the first billed month
    settled = pd.Series([450, 470], index=pd.period_range("2014-01", "2014-02", freq="M"))
    fc = facility_capacity_kw(pd.concat([seed, settled]), settled.index)
    assert fc.loc[pd.Period("2014-01", "M")] == pytest.approx((700 + 650) / 2)
    assert fc.loc[pd.Period("2014-02", "M")] == pytest.approx((700 + 650) / 2)


def test_facility_capacity_requires_full_history():
    short = pd.Series([500.0], index=pd.period_range("2014-01", "2014-01", freq="M"))
    with pytest.raises(ValueError, match="no Demand history"):
        facility_capacity_kw(short, short.index)
