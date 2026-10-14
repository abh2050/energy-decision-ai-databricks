"""Build load_observations from the raw UCI file (FR2 to FR5). No Databricks code here."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel

from edip.core.cleaning import (
    DstDayCheck,
    activation_time,
    check_dst_day,
    drop_pre_activation,
    march_change_day,
    october_change_day,
    to_standard_time,
)
from edip.core.selection import SelectionResult, SelectionRule, select_client
from edip.core.splits import SPLIT_NAMES, SplitBounds, assign_split
from edip.core.units import to_hourly

T = pd.Timestamp


def read_uci(path: str) -> pd.DataFrame:
    """Parse the semicolon separated, comma decimal UCI file into a wide kW frame."""
    return pd.read_csv(path, sep=";", decimal=",", index_col=0, parse_dates=True)


class SplitSummary(BaseModel):
    name: str
    start: str
    end_exclusive: str
    hours: int
    zero_hours: int
    max_kw_mean: float


class QualityReport(BaseModel):
    dataset_sha256: str
    raw_rows: int
    raw_clients: int
    raw_first_label: str
    raw_last_label: str
    selection: SelectionResult
    selection_rule: dict[str, Any]
    client_activation: str | None
    dst_checks: list[DstDayCheck]
    rows_before_series_start: int
    placeholder_rows_removed: int
    october_rows_split: int
    incomplete_hours_dropped: int
    hourly_rows: int
    splits: list[SplitSummary]


def rule_from_config(cfg: dict[str, Any]) -> SelectionRule:
    sel = cfg["client_selection"]
    return SelectionRule(
        activated_before=T(sel["activated_before"]),
        train_start=T(cfg["splits"]["train"][0]),
        train_end=T(cfg["splits"]["train"][1]),
        dst_years=cfg["timezone"]["dst_years"],
        october_doubling_ratio=tuple(sel["october_doubling_ratio"]),
        train_nonzero_share_min=sel["train_nonzero_share_min"],
        demand_kw_min_exclusive=sel["demand_kw_min_exclusive"],
        demand_kw_max_inclusive=sel["demand_kw_max_inclusive"],
        consecutive_months_above_min=sel["consecutive_months_above_min"],
    )


def bounds_from_config(cfg: dict[str, Any]) -> SplitBounds:
    s = cfg["splits"]
    return SplitBounds(
        train=(T(s["train"][0]), T(s["train"][1])),
        validation=(T(s["validation"][0]), T(s["validation"][1])),
        test=(T(s["test"][0]), T(s["test"][1])),
    )


def build(
    wide: pd.DataFrame, cfg: dict[str, Any], dataset_sha256: str
) -> tuple[pd.DataFrame, QualityReport]:
    rule = rule_from_config(cfg)
    bounds = bounds_from_config(cfg)
    years: list[int] = cfg["timezone"]["dst_years"]
    selection = select_client(wide, rule)
    client = selection.client_id
    kw = wide[client]

    checks = [check_dst_day(kw, march_change_day(y), "march") for y in years]
    checks += [check_dst_day(kw, october_change_day(y), "october") for y in years]

    active = drop_pre_activation(kw)
    std = to_standard_time(active, years)
    series_start = T(cfg["series_start"])
    before = int((std.index <= series_start).sum())
    std = std[std.index > series_start]  # interval-end labels after the start
    hourly = to_hourly(std)
    expected_hours = len(std) // 4
    split = assign_split(hourly.index, bounds)
    hourly = hourly[split.notna()]

    out = pd.DataFrame(
        {
            "client_id": client,
            "hour_start": hourly.index,
            "kw_mean": hourly["kw_mean"].to_numpy(),
            "kwh": hourly["kwh"].to_numpy(),
            "n_intervals": hourly["n_intervals"].astype("int32").to_numpy(),
            "split": split[split.notna()].to_numpy(),
            "dataset_sha256": dataset_sha256,
        }
    )
    summaries = []
    for name in SPLIT_NAMES:
        part = out[out["split"] == name]
        start, end = getattr(bounds, name)
        summaries.append(
            SplitSummary(
                name=name,
                start=start.isoformat(),
                end_exclusive=end.isoformat(),
                hours=len(part),
                zero_hours=int((part["kw_mean"] == 0).sum()),
                max_kw_mean=float(part["kw_mean"].max()),
            )
        )
    act = activation_time(kw)
    report = QualityReport(
        dataset_sha256=dataset_sha256,
        raw_rows=wide.shape[0],
        raw_clients=wide.shape[1],
        raw_first_label=wide.index[0].isoformat(),
        raw_last_label=wide.index[-1].isoformat(),
        selection=selection,
        selection_rule=cfg["client_selection"],
        client_activation=act.isoformat() if act is not None else None,
        dst_checks=checks,
        rows_before_series_start=before,
        placeholder_rows_removed=4 * len(years),
        october_rows_split=4 * len(years),
        incomplete_hours_dropped=expected_hours - len(hourly),
        hourly_rows=len(out),
        splits=summaries,
    )
    return out, report
