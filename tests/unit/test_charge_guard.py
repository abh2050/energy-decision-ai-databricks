"""Charge guard: month-start limit, 15 minute headroom, both B-19 determinants, PGE FC."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from edip.core.battery import BatterySpec
from edip.core.charge_guard import ChargeGuard, determinants
from edip.core.settlement import settle_day
from edip.core.tariff import load_tariff

ROOT = Path(__file__).parents[2]
B19 = load_tariff(ROOT / "config" / "tariffs" / "anchored_tou.yaml")
PGN = load_tariff(ROOT / "config" / "tariffs" / "low_spread_tou.yaml")
with (ROOT / "config" / "battery.yaml").open() as fh:
    SPEC = BatterySpec.from_config(yaml.safe_load(fh), observed_peak_kw=800.0)  # 400 kW
T = pd.Timestamp
MAX, PEAK, PART = "Maximum demand", "Maximum peak demand", "Maximum part-peak demand"


def _guard(start, tariff=B19, margin=0.0):
    return ChargeGuard(tariff, start, margin)


def test_month_start_limit_is_previous_month_billed_demand():
    guard = _guard({MAX: 700.0, PEAK: 650.0, PART: 600.0})
    # July 2014, 03:00 UTC = 04:00 Lisbon, off-peak: only Maximum demand is in effect.
    hour = T("2014-07-01 03:00")
    assert guard.cap_kw(hour) == 700.0
    assert guard.allowed_charge_kw(hour, np.array([500, 500, 500, 500])) == 200.0


def test_next_month_starts_at_this_months_billed_demand():
    guard = _guard({MAX: 700.0, PEAK: 650.0, PART: 600.0})
    july = T("2014-07-31 03:00")
    guard.cap_kw(july)
    guard.update(july, np.array([720, 760, 740, 730]))  # new July peak 760 kW
    august = T("2014-08-01 03:00")
    assert guard.cap_kw(august) == 760.0  # not reset to zero or to June's 700


def test_headroom_is_smallest_across_the_hours_15_minute_intervals():
    guard = _guard({MAX: 700.0, PEAK: 650.0, PART: 600.0})
    hour = T("2014-07-01 03:00")
    # Hourly mean 500 kW would allow 200 kW; the 640 kW interval allows only 60 kW.
    loads = np.array([400, 640, 460, 500])
    assert guard.allowed_charge_kw(hour, loads) == pytest.approx(60.0)
    assert guard.allowed_charge_kw(hour, np.array([710, 400, 400, 400])) == 0.0


def test_b19_maximum_and_peak_period_determinants_both_bind():
    guard = _guard({MAX: 800.0, PEAK: 600.0, PART: 700.0})
    loads = np.full(4, 500.0)
    # 17:00 Lisbon in July (16:00 UTC) is the B-19 peak period: the 600 kW peak-period
    # determinant binds below the 800 kW maximum demand.
    assert guard.cap_kw(T("2014-07-01 16:00")) == 600.0
    assert guard.allowed_charge_kw(T("2014-07-01 16:00"), loads) == 100.0
    # 05:00 Lisbon is off-peak: only maximum demand applies.
    assert guard.cap_kw(T("2014-07-01 04:00")) == 800.0
    # 15:00 Lisbon is summer part-peak: part-peak and maximum demand apply.
    assert guard.cap_kw(T("2014-07-01 14:00")) == 700.0


def test_pgn_facility_capacity_determinant_applies_on_sunday():
    names = [d.name for d in determinants(PGN)]
    assert "Facility Capacity Demand" in names
    start = {d.name: 650.0 for d in determinants(PGN)}
    start["Facility Capacity Demand"] = 700.0
    guard = _guard(start, PGN)
    assert guard.cap_kw(T("2014-07-13 15:00")) == 700.0  # Sunday: only FC Demand
    assert guard.cap_kw(T("2014-07-14 15:00")) == 650.0  # Monday 16:00: window demand too


def test_settlement_guard_reduces_charge_only_and_records_clipping():
    hours = pd.date_range("2014-07-01 00:00", periods=24, freq="h")
    load15 = np.full((24, 4), 500.0)
    actual = load15.mean(axis=1)
    planned_c = np.zeros(24)
    planned_c[2] = 350.0  # 03:00 Lisbon; maximum demand cap 700 allows 200 kW
    guard = _guard({MAX: 700.0, PEAK: 650.0, PART: 600.0})
    day = settle_day(
        planned_c,
        np.zeros(24),
        actual,
        SPEC,
        SPEC.soc_min_kwh,
        guard=guard,
        hours_utc=hours,
        load15_kw=load15,
    )
    assert day.charge_kw[2] == pytest.approx(200.0)
    assert day.guard_clipped_kw[2] == pytest.approx(150.0)
    assert guard.clipped_kwh == pytest.approx(150.0)
    assert sum(day.discharge_kw) == 0.0  # never adds discharge
    assert max(day.grid_kw) <= 700.0 + 1e-9


def test_month_start_is_previous_months_billed_demand_over_three_months():
    """Specified rule (corrected 2026-10-15): month 2's peak falls below month 1's, and
    month 3 starts at month 2's billed demand, not at month 1's carried-forward peak."""
    guard = _guard({MAX: 700.0, PEAK: 650.0, PART: 600.0})  # June billed demand (seed)
    july = T("2014-07-31 03:00")
    guard.cap_kw(july)
    guard.update(july, np.array([720, 760, 740, 730]))  # month 1 (July) billed: 760 kW
    august = T("2014-08-15 03:00")
    assert guard.cap_kw(august) == 760.0  # month 2 starts at July's billed demand
    guard.update(august, np.array([480, 500, 490, 470]))  # month 2 (August) peak: 500 kW
    assert guard.cap_kw(T("2014-08-31 03:00")) == 760.0  # within August the limit holds
    september = T("2014-09-01 03:00")
    assert guard.cap_kw(september) == 500.0  # month 3 starts at August's billed demand


def test_month_with_no_settled_hours_bills_zero_demand_for_the_next_start():
    guard = _guard({MAX: 700.0, PEAK: 650.0, PART: 600.0})
    guard.cap_kw(T("2014-07-31 03:00"))  # July opened, nothing settled
    assert guard.cap_kw(T("2014-08-01 03:00")) == 0.0
