"""Gate 3 required tests: constraints (Hypothesis), clipping, no-battery bill, regret."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from edip.core.battery import BatterySpec
from edip.core.billing_demand import interval_demand
from edip.core.optimizer import DemandTerm, solve_day
from edip.core.settlement import bill_months, count_violations, settle_day
from edip.core.tariff import load_tariff

ROOT = Path(__file__).parents[2]
with (ROOT / "config" / "battery.yaml").open() as fh:
    BATTERY_CFG = yaml.safe_load(fh)
SPEC = BatterySpec.from_config(BATTERY_CFG, observed_peak_kw=800.0)
B19 = load_tariff(ROOT / "config" / "tariffs" / "anchored_tou.yaml")

loads = st.lists(st.floats(0, 1500, allow_nan=False), min_size=24, max_size=24)
powers = st.lists(st.floats(-500, 1000, allow_nan=False), min_size=24, max_size=24)
socs = st.floats(SPEC.soc_min_kwh, SPEC.soc_max_kwh, allow_nan=False)


def objective(day, price, terms, deg):
    """Cost of a settled day on actual load: energy, demand above running peak, wear."""
    g = np.asarray(day.grid_kw)
    cost = float(np.dot(price, g)) + deg * float(np.sum(day.discharge_kw))
    for t in terms:
        mask = np.asarray(t.mask)
        peak = max(t.running_peak_kw, float(g[mask].max())) if mask.any() else t.running_peak_kw
        cost += t.rate_usd_per_kw * (peak - t.running_peak_kw)
    return cost


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(charge=powers, discharge=powers, actual=loads, soc0=socs)
def test_property_settled_schedule_never_violates_constraints(charge, discharge, actual, soc0):
    """Any plan, even an infeasible one, settles into a physically valid schedule."""
    day = settle_day(np.array(charge), np.array(discharge), np.array(actual), SPEC, soc0)
    assert count_violations(day.charge_kw, day.discharge_kw, day.soc_kwh, day.grid_kw, SPEC) == 0


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(forecast=loads, actual=loads, soc0=socs)
def test_property_optimizer_plans_settle_without_violations(forecast, actual, soc0):
    price = np.where(np.arange(24) >= 16, 0.30, 0.10)
    terms = [DemandTerm(name="m", mask=[True] * 24, rate_usd_per_kw=10.0, running_peak_kw=0.0)]
    plan = solve_day(np.array(forecast), price, terms, SPEC, soc0, SPEC.terminal_reserve_kwh)
    c, d = np.array(plan.charge_kw), np.array(plan.discharge_kw)
    assert not ((c > 1e-6) & (d > 1e-6)).any()  # binary prevents simultaneous charge
    day = settle_day(c, d, np.array(actual), SPEC, soc0)
    assert count_violations(day.charge_kw, day.discharge_kw, day.soc_kwh, day.grid_kw, SPEC) == 0


def test_settlement_clips_50_kw_discharge_to_30_kw_actual_load():
    soc0 = SPEC.soc_max_kwh
    planned_d = np.zeros(24)
    planned_d[0] = 50.0
    actual = np.full(24, 100.0)
    actual[0] = 30.0
    day = settle_day(np.zeros(24), planned_d, actual, SPEC, soc0)
    assert day.discharge_kw[0] == pytest.approx(30.0)
    assert day.discharge_clipped_kw[0] == pytest.approx(20.0)
    assert day.grid_kw[0] == pytest.approx(0.0)  # no export
    assert day.soc_kwh[0] == pytest.approx(soc0 - 30.0 / SPEC.eta_discharge)


def test_no_battery_bill_equals_tariff_applied_to_raw_load():
    hours = pd.date_range("2014-07-01", periods=24 * 31, freq="h")  # July: UTC+1 in Lisbon
    hours = hours[hours < pd.Timestamp("2014-07-31 23:00")]  # local July only
    rng = np.random.default_rng(5)
    load15 = pd.Series(
        400 + 200 * rng.random(len(hours) * 4),
        index=pd.date_range(
            hours[0] + pd.Timedelta(minutes=15), periods=len(hours) * 4, freq="15min"
        ),
    )
    hourly = load15.groupby((load15.index - pd.Timedelta(minutes=15)).floor("h")).mean()
    bills = bill_months(
        B19, hours, hourly.reindex(hours).to_numpy(), load15, pd.Series(0.0, index=hours)
    )
    assert len(bills) == 1
    bill = bills[0]

    # Independent calculation: energy at the tariff rate, demand on 15 minute load.
    energy = float((hourly.reindex(hours) * B19.energy_rate(hours)).sum())
    demand15 = interval_demand(load15, 15)
    local = demand15.index.tz_localize("UTC").tz_convert("Europe/Lisbon")
    peak_mask = (local.hour >= 16) & (local.hour < 21)
    part_mask = ((local.hour >= 14) & (local.hour < 16)) | ((local.hour >= 21) & (local.hour < 23))
    expected = (
        energy
        + 37.37 * demand15.max()
        + 46.16 * demand15[peak_mask].max()
        + 10.52 * demand15[part_mask].max()
    )
    assert bill.energy_usd == pytest.approx(energy)
    assert bill.total_usd == pytest.approx(expected)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(forecast=loads, actual=loads, soc0=socs, peak0=st.floats(0, 1200))
def test_hindsight_regret_is_never_negative(forecast, actual, soc0, peak0):
    """From the same state, no settled plan beats the hindsight plan on actual load."""
    price = np.where((np.arange(24) >= 16) & (np.arange(24) < 21), 0.19, 0.12)
    mask = [(16 <= h < 21) for h in range(24)]
    terms = [
        DemandTerm(name="all", mask=[True] * 24, rate_usd_per_kw=37.37, running_peak_kw=peak0),
        DemandTerm(name="peak", mask=mask, rate_usd_per_kw=46.16, running_peak_kw=0.0),
    ]
    actual = np.array(actual)
    best = solve_day(actual, price, terms, SPEC, soc0, SPEC.terminal_reserve_kwh)
    hindsight = settle_day(
        np.array(best.charge_kw), np.array(best.discharge_kw), actual, SPEC, soc0
    )
    other = solve_day(np.array(forecast), price, terms, SPEC, soc0, SPEC.terminal_reserve_kwh)
    settled = settle_day(
        np.array(other.charge_kw), np.array(other.discharge_kw), actual, SPEC, soc0
    )
    deg = SPEC.degradation_usd_per_kwh
    regret = objective(settled, price, terms, deg) - objective(hindsight, price, terms, deg)
    assert regret >= -1e-6 * max(1.0, abs(objective(hindsight, price, terms, deg)))


def test_optimizer_respects_terminal_reserve_and_shaves_peak():
    load = np.full(24, 500.0)
    load[18] = 900.0
    price = np.full(24, 0.12)
    terms = [DemandTerm(name="m", mask=[True] * 24, rate_usd_per_kw=40.0, running_peak_kw=0.0)]
    plan = solve_day(load, price, terms, SPEC, SPEC.initial_soc_kwh, SPEC.terminal_reserve_kwh)
    assert plan.soc_kwh[-1] >= SPEC.terminal_reserve_kwh - 1e-6
    assert max(plan.grid_kw) < 900.0
