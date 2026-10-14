import numpy as np
import pandas as pd
import pytest

from edip.core.selection import SelectionRule, select_client
from edip.core.splits import SplitBounds, assign_split

T = pd.Timestamp


def _bounds():
    return SplitBounds(
        train=(T("2012-01-01"), T("2013-07-01")),
        validation=(T("2013-07-01"), T("2014-01-01")),
        test=(T("2014-01-01"), T("2015-01-01")),
    )


def test_test_partition_timestamps_never_in_train_or_validation():
    hours = pd.date_range("2012-01-01", "2014-12-31 23:00", freq="h")
    labels = assign_split(hours, _bounds())
    test = set(hours[labels == "test"])
    other = set(hours[labels.isin(["train", "validation"])])
    assert test and other
    assert test.isdisjoint(other)
    assert max(other) < min(test)
    assert labels.notna().all()


def test_boundary_hour_belongs_to_later_split():
    labels = assign_split(
        pd.DatetimeIndex([T("2013-07-01 00:00"), T("2013-06-30 23:00")]), _bounds()
    )
    assert list(labels) == ["validation", "train"]


def test_overlapping_bounds_rejected():
    with pytest.raises(ValueError):
        SplitBounds(
            train=(T("2012-01-01"), T("2013-08-01")),
            validation=(T("2013-07-01"), T("2014-01-01")),
            test=(T("2014-01-01"), T("2015-01-01")),
        )


def _rule(**kw):
    base = dict(
        activated_before=T("2012-01-01"),
        train_start=T("2012-01-01"),
        train_end=T("2013-07-01"),
        dst_years=[2012],
        october_doubling_ratio=(1.6, 2.5),
        train_nonzero_share_min=1.0,
        demand_kw_min_exclusive=499,
        demand_kw_max_inclusive=999,
        consecutive_months_above_min=3,
    )
    base.update(kw)
    return SelectionRule(**base)


def _wide():
    idx = pd.date_range("2011-12-01 00:15", "2013-07-01 00:00", freq="15min")
    rng = np.random.default_rng(0)
    base = 300 + 50 * rng.random(len(idx))
    df = pd.DataFrame(
        {
            "MT_009": base + 300,  # in B-19 range, valid
            "MT_002": base + 300,  # same, lower number wins
            "MT_003": base,  # never above 499 kW
            "MT_004": base + 800,  # above 999 kW
        },
        index=idx,
    )
    df.loc[:"2011-12-15", "MT_002"] = 0.0  # leading zeros, still activated before 2012
    for c in df.columns:
        df.loc[[T(f"2012-03-25 {t}") for t in ("01:00", "01:15", "01:30", "01:45")], c] = 0.0
        oct_block = [T(f"2012-10-28 {t}") for t in ("01:00", "01:15", "01:30", "01:45")]
        df.loc[oct_block, c] = df.loc[oct_block, c] * 2
    return df


def test_selection_applies_rule_and_tie_break():
    result = select_client(_wide(), _rule())
    assert result.candidates == ["MT_002", "MT_009"]
    assert result.client_id == "MT_002"
    assert [s.remaining for s in result.steps] == [4, 4, 4, 4, 2]
    assert 499 < result.train_max_demand_kw <= 999


def test_selection_rejects_missing_dst_placeholders():
    df = _wide()
    df.loc[T("2012-03-25 01:15"), "MT_002"] = 5.0
    assert select_client(df, _rule()).client_id == "MT_009"
