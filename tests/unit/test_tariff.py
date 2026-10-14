from pathlib import Path

import pandas as pd
import pytest

from edip.core.tariff import load_tariff, load_tariffs

TARIFFS = Path(__file__).parents[2] / "config" / "tariffs"


@pytest.fixture(scope="module")
def b19():
    return load_tariff(TARIFFS / "anchored_tou.yaml")


@pytest.fixture(scope="module")
def pgn():
    return load_tariff(TARIFFS / "low_spread_tou.yaml")


def _utc_day(day):
    return pd.date_range(f"{day} 00:00", periods=24, freq="h")  # naive = UTC


def _cls(tariff, ts_utc):
    return tariff.classify(pd.DatetimeIndex([pd.Timestamp(ts_utc)])).iloc[0]


def test_march_transition_day_maps_24_utc_hours_to_23_local_hours(b19):
    # 2014-03-30, Lisbon moves from UTC+0 to UTC+1 at 01:00 UTC.
    cls = b19.classify(_utc_day("2014-03-30"))
    assert len(cls) == 24
    assert list(cls["local_hour"][:3]) == [0, 2, 3]  # local 01:00 does not exist
    assert cls["local_hour"].iloc[-1] == 0  # 23:00 UTC is 00:00 local next day
    by_utc = dict(zip(cls.index.hour, cls["period"], strict=True))
    # Winter, March: super off-peak 9:00-14:00 local = 08:00-12:00 UTC after the change.
    assert by_utc[7] == "off_peak" and by_utc[8] == "super_off_peak"
    assert by_utc[12] == "super_off_peak" and by_utc[13] == "off_peak"
    # Peak 16:00-21:00 local = 15:00-19:00 UTC.
    assert [h for h, p in by_utc.items() if p == "peak"] == [15, 16, 17, 18, 19]


def test_october_transition_day_maps_24_utc_hours_to_25_hour_local_clock(b19):
    # 2014-10-26, Lisbon moves from UTC+1 to UTC+0 at 01:00 UTC; local 01:00 repeats.
    cls = b19.classify(_utc_day("2014-10-26"))
    assert len(cls) == 24
    assert list(cls["local_hour"][:3]) == [1, 1, 2]
    by_utc = dict(zip(cls.index.hour, cls["period"], strict=True))
    assert [h for h, p in by_utc.items() if p == "peak"] == [16, 17, 18, 19, 20]
    # The day before, still on summer time, peak starts at 15:00 UTC.
    before = b19.classify(_utc_day("2014-10-25"))
    assert list(before.index.hour[before["period"] == "peak"]) == [15, 16, 17, 18, 19]


@pytest.mark.parametrize(
    ("ts_utc", "season", "period"),
    [
        ("2014-07-15 15:00", "summer", "peak"),  # 16:00 local (UTC+1)
        ("2014-07-15 13:00", "summer", "part_peak"),  # 14:00 local
        ("2014-07-15 20:00", "summer", "part_peak"),  # 21:00 local
        ("2014-07-15 12:00", "summer", "off_peak"),
        ("2014-01-15 16:00", "winter", "peak"),  # UTC+0 in winter
        ("2014-01-15 10:00", "winter", "off_peak"),
        ("2014-04-15 09:00", "winter", "super_off_peak"),  # 10:00 local
    ],
)
def test_b19_periods_from_lisbon_clock(b19, ts_utc, season, period):
    row = _cls(b19, ts_utc)
    assert (row["season"], row["period"]) == (season, period)


def test_b19_rates_and_provenance(b19):
    rate = b19.energy_rate(pd.DatetimeIndex([pd.Timestamp("2014-07-15 16:00")]))
    assert rate.iloc[0] == 0.18648
    assert {s.advice_letter for s in b19.sources} == {"7846-E", "7116-E-B"}
    assert [e.reason for e in b19.excluded] == [
        "fixed customer charge",
        "percentage taxes or franchise fees",
    ]


def test_b19_peak_demand_window_uses_local_clock(b19):
    charge = next(c for c in b19.demand_charges if c.name == "Maximum peak demand")
    hours = _utc_day("2014-07-15")
    assert list(hours[b19.in_demand_window(charge, hours)].hour) == [15, 16, 17, 18, 19]


def test_pgn_periods_weekdays_and_sunday(pgn):
    assert _cls(pgn, "2014-07-14 15:00")["period"] == "on_peak"  # Monday 16:00 local
    assert _cls(pgn, "2014-07-14 05:00")["period"] == "mid_peak"  # Monday 06:00 local
    assert _cls(pgn, "2014-07-14 21:00")["period"] == "off_peak"  # Monday 22:00 local
    assert _cls(pgn, "2014-07-13 15:00")["period"] == "off_peak"  # Sunday


def test_pgn_energy_rate_sums_all_components_times_schedule_108(pgn):
    on = pgn.energy_rate(pd.DatetimeIndex([pd.Timestamp("2014-07-14 15:00")])).iloc[0]
    off = pgn.energy_rate(pd.DatetimeIndex([pd.Timestamp("2014-07-13 15:00")])).iloc[0]
    flat_cents = sum(c.cents_per_kwh for c in pgn.energy_components if c.cents_per_kwh is not None)
    assert pgn.multiplier == 1.015
    assert pgn.variable_charge_multiplier.source == "pge_108"
    assert on == pytest.approx(1.015 * (5.808 + flat_cents) / 100)
    assert on - off == pytest.approx(1.015 * (5.808 - 3.901) / 100)
    cited = {c.source for c in pgn.energy_components}
    assert {"pge_85", "pge_125", "pge_109", "pge_151"} <= cited


def test_pgn_provenance_labels(pgn):
    status = {s.id: s.status for s in pgn.sources}
    assert status["pge_85_periods_2026_01"] == "superseded"
    assert status["pge_38_corroborating"] == "corroborating"
    assert status["pge_85"] == "current"
    s126 = next(c for c in pgn.energy_components if c.source == "pge_126")
    assert "Schedule 100" in s126.applicability_note
    assert all(e.source != "pge_108" for e in pgn.excluded)
    assert pgn.savings_basis == "before_tax"


def test_b19_has_no_multiplier(b19):
    assert b19.multiplier == 1.0


def test_pgn_facility_capacity_tiers(pgn):
    fc = pgn.facility_capacity
    assert fc.monthly_charge(150) == pytest.approx(150 * 3.52)
    assert fc.monthly_charge(800) == pytest.approx(200 * 3.52 + 600 * 3.42)


def test_pgn_peak_demand_window_monday_to_saturday(pgn):
    charge = pgn.demand_charges[0]
    sunday = _utc_day("2014-07-13")
    monday = _utc_day("2014-07-14")
    assert not pgn.in_demand_window(charge, sunday).any()
    assert list(monday[pgn.in_demand_window(charge, monday)].hour) == list(range(5, 21))


def test_synthetic_sweep_widens_peak_and_part_peak_in_both_seasons(b19):
    sweep = load_tariffs(TARIFFS / "synthetic_high_spread.yaml")
    assert [t.id for t in sweep] == [
        "synthetic_high_spread_m1",
        "synthetic_high_spread_m1_5",
        "synthetic_high_spread_m2",
        "synthetic_high_spread_m3",
    ]
    hours = {  # UTC hours; July is UTC+1 in Lisbon, January UTC+0, April UTC+1
        ("summer", "peak"): "2014-07-15 16:00",
        ("summer", "part_peak"): "2014-07-15 14:00",
        ("summer", "off_peak"): "2014-07-15 02:00",
        ("winter", "peak"): "2014-01-15 17:00",
        ("winter", "off_peak"): "2014-01-15 02:00",
        ("winter", "super_off_peak"): "2014-04-15 10:00",
    }

    def rate(t, key):
        return t.energy_rate(pd.DatetimeIndex([pd.Timestamp(hours[key])])).iloc[0]

    for t, m in zip(sweep, [1.0, 1.5, 2.0, 3.0], strict=True):
        assert t.synthetic and t.role == "stress"
        for season in ("summer", "winter"):
            off = (season, "off_peak")
            assert rate(t, off) == rate(b19, off)  # off-peak held fixed
            peak = (season, "peak")
            assert rate(t, peak) - rate(t, off) == pytest.approx(
                m * (rate(b19, peak) - rate(b19, off))
            )
        pp, off = ("summer", "part_peak"), ("summer", "off_peak")
        assert rate(t, pp) - rate(t, off) == pytest.approx(m * (rate(b19, pp) - rate(b19, off)))
        sop = ("winter", "super_off_peak")
        assert rate(t, sop) == rate(b19, sop)  # not widened
