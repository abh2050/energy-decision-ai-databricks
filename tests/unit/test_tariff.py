from pathlib import Path

import pandas as pd
import pytest

from edip.core.tariff import load_tariff

TARIFFS = Path(__file__).parents[2] / "config" / "tariffs"


@pytest.fixture(scope="module")
def b19():
    return load_tariff(TARIFFS / "anchored_tou.yaml")


def _period(tariff, ts):
    row = tariff.classify(pd.DatetimeIndex([pd.Timestamp(ts)])).iloc[0]
    return row["season"], row["period"]


@pytest.mark.parametrize(
    ("ts", "expected"),
    [
        ("2014-07-15 16:00", ("summer", "peak")),
        ("2014-07-15 20:00", ("summer", "peak")),
        ("2014-07-15 21:00", ("summer", "part_peak")),
        ("2014-07-15 14:00", ("summer", "part_peak")),
        ("2014-07-15 13:00", ("summer", "off_peak")),
        ("2014-07-13 17:00", ("summer", "peak")),  # Sunday: every day includes weekends
        ("2014-01-15 10:00", ("winter", "off_peak")),
        ("2014-04-15 10:00", ("winter", "super_off_peak")),
        ("2014-04-15 18:00", ("winter", "peak")),
        ("2014-10-01 00:00", ("winter", "off_peak")),
    ],
)
def test_b19_periods(b19, ts, expected):
    assert _period(b19, ts) == expected


def test_b19_energy_rates_from_sheet(b19):
    rate = b19.energy_rate(pd.DatetimeIndex([pd.Timestamp("2014-07-15 17:00")]))
    assert rate.iloc[0] == 0.18648
    assert b19.source.advice_letter == "7846-E"
    assert not b19.synthetic


def test_b19_peak_demand_window(b19):
    hours = pd.date_range("2014-07-15 00:00", periods=24, freq="h")
    charge = next(c for c in b19.demand_charges if c.name == "maximum_peak_demand")
    window = b19.in_demand_window(charge, hours)
    assert list(hours[window].hour) == [16, 17, 18, 19, 20]


def test_synthetic_widens_spread_and_is_labelled(b19):
    stress = load_tariff(TARIFFS / "synthetic_high_spread.yaml")
    assert stress.synthetic and stress.role == "stress"
    base, wide = b19.energy_usd_per_kwh["summer"], stress.energy_usd_per_kwh["summer"]
    assert wide["off_peak"] == base["off_peak"]
    assert wide["peak"] - wide["off_peak"] == pytest.approx(
        3 * (base["peak"] - base["off_peak"]), abs=1e-5
    )
    assert any("SYNTHETIC" in n for n in stress.notes)


def test_pending_tariff_refuses_to_load():
    with pytest.raises(ValueError, match="not yet encoded"):
        load_tariff(TARIFFS / "low_spread_tou.yaml")
