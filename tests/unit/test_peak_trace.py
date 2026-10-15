"""Peak trace: cause labels and the guard replay used to attribute excess demand."""

from pathlib import Path

import pandas as pd

from edip.core.tariff import load_tariff
from edip.replay.peak_trace import _cause, guard_states

B19 = load_tariff(Path(__file__).parents[2] / "config" / "tariffs" / "anchored_tou.yaml")


def test_cause_labels():
    assert _cause(0.0, "2014-03", "2014-05") == "no charging in the interval"
    assert _cause(50.0, "2014-05", "2014-05") == "guard limit raised earlier this month"
    assert _cause(50.0, "2014-04", "2014-05") == "guard month-start limit (previous month)"
    assert _cause(50.0, "2014-01", "2014-05") == "guard limit carried forward from 2014-01"


def test_guard_replay_tracks_where_the_limit_came_from():
    hours = pd.date_range("2014-07-31 01:00", periods=3, freq="h").append(
        pd.date_range("2014-08-01 01:00", periods=1, freq="h")
    )
    frame = pd.DataFrame(
        {"charge_kw": [0.0, 0.0, 0.0, 0.0], "discharge_kw": [0.0] * 4}, index=hours
    )
    ends = pd.date_range("2014-06-01 00:15", "2014-08-01 03:00", freq="15min")
    load = pd.Series(400.0, index=ends)
    load[(ends > "2014-06-10 00:00") & (ends <= "2014-06-10 00:15")] = 900.0  # June peak
    states = guard_states(B19, frame, load, margin=0.0)
    assert states.loc[hours[-1], "guard_cap_kw"] == 900.0
    assert states.loc[hours[-1], "guard_cap_origin_month"] == "2014-06"
