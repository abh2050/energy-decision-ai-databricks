from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from edip.replay.stress import heat_week, inject_forecast_error, raise_floor

ROOT = Path(__file__).parents[2]


def _hourly():
    idx = pd.date_range("2014-07-01", periods=24 * 20, freq="h")
    actual = 400 + 100 * np.sin(np.arange(len(idx)) / 5)
    actual[24 * 10 + 15] = 900  # the annual peak
    return pd.DataFrame(
        {
            "actual": actual,
            "seasonal": actual + 20,
            "point": actual - 10,
            "p50": actual - 10,
            "p90": actual + 30,
        },
        index=idx,
    )


def test_forecast_error_doubles_every_forecast_error():
    h = _hourly()
    s = inject_forecast_error(h, 2.0)
    assert (s["point"] - s["actual"]).abs().max() == pytest.approx(20)
    assert (s["p90"] - s["actual"]).max() == pytest.approx(60)
    assert (s["actual"] == h["actual"]).all()


def test_heat_week_scales_actual_load_only_around_the_peak():
    h = _hourly()
    l15 = pd.Series(
        1.0,
        index=pd.date_range(
            h.index[0] + pd.Timedelta(minutes=15), periods=len(h) * 4, freq="15min"
        ),
    )
    sh, s15, (start, end) = heat_week(h, l15, 1.10, 7)
    assert end - start == pd.Timedelta(days=7)
    assert start <= h["actual"].idxmax() < end
    inside = (sh.index >= start) & (sh.index < end)
    assert np.allclose(sh.loc[inside, "actual"], h.loc[inside, "actual"] * 1.10)
    assert (sh.loc[~inside, "actual"] == h.loc[~inside, "actual"]).all()
    assert (sh["point"] == h["point"]).all()  # forecasts unchanged
    assert s15.max() == pytest.approx(1.10)


def test_reserve_floor_raise_changes_only_soc_min(tmp_path):
    work = raise_floor(ROOT / "config", 0.30, tmp_path / "cfg")
    raised = yaml.safe_load((work / "battery.yaml").read_text())
    original = yaml.safe_load((ROOT / "config" / "battery.yaml").read_text())
    assert raised["base_case"]["soc_min_fraction"] == 0.30
    raised["base_case"]["soc_min_fraction"] = original["base_case"]["soc_min_fraction"]
    assert raised == original
    assert (work / "acceptance_targets.yaml").read_bytes() == (
        ROOT / "config" / "acceptance_targets.yaml"
    ).read_bytes()


def _annual(rows):
    return pd.DataFrame(rows, columns=["tariff_id", "strategy", "net_benefit_usd", "violations"])


def _monthly(rows):
    cols = [
        "tariff_id",
        "strategy",
        "month",
        "bill_usd",
        "energy_usd",
        "facility_capacity_usd",
        "demand_usd_by_charge",
        "billing_demand_kw_by_charge",
    ]
    return pd.DataFrame(rows, columns=cols)


LIMITS = {
    "min_net_benefit_retained_pct": 50,
    "max_monthly_bill_increase_vs_no_battery_pct": 1,
    "accepted_constraint_violations": 0,
}


def test_base_negative_records_null_with_reason_and_judges_absolute_change():
    from edip.replay.stress import NOT_APPLICABLE, evaluate

    base = _annual([("t", "ml", -100.0, 0), ("t", "robust", 1000.0, 0)])
    stressed = _annual([("t", "ml", -90.0, 0), ("t", "robust", 400.0, 0)])
    monthly = _monthly(
        [
            ("t", "no_battery", "2014-01", 100.0, 50.0, 0.0, "{}", "{}"),
            ("t", "ml", "2014-01", 100.5, 50.0, 0.0, "{}", "{}"),
            ("t", "robust", "2014-01", 100.0, 50.0, 0.0, "{}", "{}"),
        ]
    )
    rows = {r["strategy"]: r for r in evaluate(base, stressed, monthly, LIMITS)}
    ml, robust = rows["ml"], rows["robust"]
    assert ml["retained_pct"] is None and ml["retained_reason"] == "base_negative"
    assert ml["retained_display"] == NOT_APPLICABLE
    assert ml["absolute_change_usd"] == 10.0 and ml["passed"]  # no worse, month within 1%
    assert robust["retained_pct"] == 40.0 and not robust["passed"]  # below 50 percent retained


def test_excess_month_split_and_guard_month_start_cause():
    import json

    from edip.core.tariff import load_tariff
    from edip.replay.stress import excess_months

    b19 = load_tariff(ROOT / "config" / "tariffs" / "anchored_tou.yaml")
    l15 = pd.Series(500.0, index=pd.date_range("2013-12-01 00:15", "2014-03-01", freq="15min"))
    nb_kw = {"Maximum demand": 600.0, "Maximum peak demand": 550.0, "Maximum part-peak demand": 0.0}
    nb_usd = {
        "Maximum demand": 22422.0,
        "Maximum peak demand": 1270.5,
        "Maximum part-peak demand": 0.0,
    }
    jan_kw = {
        "Maximum demand": 800.0,
        "Maximum peak demand": 550.0,
        "Maximum part-peak demand": 0.0,
    }
    feb_kw = {
        "Maximum demand": 780.0,
        "Maximum peak demand": 550.0,
        "Maximum part-peak demand": 0.0,
    }
    feb_usd = {
        "Maximum demand": 29148.6,
        "Maximum peak demand": 1270.5,
        "Maximum part-peak demand": 0.0,
    }
    monthly = _monthly(
        [
            (
                "t",
                "no_battery",
                "2014-01",
                59692.5,
                36000.0,
                0.0,
                json.dumps(nb_usd),
                json.dumps(nb_kw),
            ),
            (
                "t",
                "no_battery",
                "2014-02",
                59692.5,
                36000.0,
                0.0,
                json.dumps(nb_usd),
                json.dumps(nb_kw),
            ),
            ("t", "ml", "2014-01", 59992.5, 36300.0, 0.0, json.dumps(nb_usd), json.dumps(jan_kw)),
            ("t", "ml", "2014-02", 66493.2, 36074.1, 0.0, json.dumps(feb_usd), json.dumps(feb_kw)),
        ]
    )
    rows = excess_months("base", monthly, {"t": b19}, l15, 0.02, 1.0)
    assert [r["month"] for r in rows] == ["2014-02"]  # January is within 1 percent
    feb = rows[0]
    parts = (
        feb["energy_usd"]
        + feb["Maximum demand usd"]
        + feb["Maximum peak demand usd"]
        + feb["Maximum part-peak demand usd"]
        + feb["facility_capacity_usd"]
    )
    assert parts == pytest.approx(feb["excess_usd"])
    # January billed 800 kW; the guard started February at 800 x 0.98 = 784 kW, above
    # February's no-battery 600 kW, and February's 780 kW is within that start limit.
    assert feb["guard_month_start_limit_caused"]
    assert feb["guard_month_start_determinants"] == ["Maximum demand"]
