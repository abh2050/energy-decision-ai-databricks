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
