"""Client selection rule (FR2). Pure functions over the wide UCI frame (wall-clock labels)."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from edip.core.cleaning import block_index, check_dst_day, march_change_day, october_change_day


class SelectionRule(BaseModel):
    activated_before: pd.Timestamp
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    dst_years: list[int]
    october_doubling_ratio: tuple[float, float]
    train_nonzero_share_min: float
    demand_kw_min_exclusive: float
    demand_kw_max_inclusive: float
    consecutive_months_above_min: int

    model_config = {"arbitrary_types_allowed": True}


class SelectionStep(BaseModel):
    name: str
    remaining: int


class SelectionResult(BaseModel):
    client_id: str
    candidates: list[str]
    steps: list[SelectionStep]
    train_max_demand_kw: float
    train_nonzero_share: float


def _client_number(client_id: str) -> int:
    return int(client_id.rsplit("_", 1)[-1])


def _dst_ok(kw: pd.Series, rule: SelectionRule) -> bool:
    lo, hi = rule.october_doubling_ratio
    for year in rule.dst_years:
        if not check_dst_day(kw, march_change_day(year), "march").placeholder_zero:
            return False
        ratio = check_dst_day(kw, october_change_day(year), "october").doubling_ratio
        if ratio is None or not lo <= ratio <= hi:
            return False
    return True


def _max_consecutive(flags: pd.Series) -> int:
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def select_client(wide: pd.DataFrame, rule: SelectionRule) -> SelectionResult:
    """Apply the rule in order and return the chosen client with step counts."""
    steps: list[SelectionStep] = [SelectionStep(name="all clients", remaining=wide.shape[1])]

    first_positive = (wide > 0).idxmax().where((wide > 0).any())
    keep = [c for c in wide.columns if first_positive[c] is not pd.NaT]
    keep = [c for c in keep if first_positive[c] < rule.activated_before]
    steps.append(SelectionStep(name="activated before series start", remaining=len(keep)))

    keep = [c for c in keep if _dst_ok(wide[c], rule)]
    steps.append(SelectionStep(name="DST artifacts as documented, all years", remaining=len(keep)))

    train = wide.loc[
        (wide.index > rule.train_start) & (wide.index <= rule.train_end), keep
    ]  # interval-end labels inside the training period
    placeholders = pd.DatetimeIndex([])
    for year in rule.dst_years:
        placeholders = placeholders.append(block_index(march_change_day(year)))
    train = train.drop(index=placeholders.intersection(train.index))
    # October rows hold two hours of consumption; halve them so demand is not inflated.
    for year in rule.dst_years:
        doubled = block_index(october_change_day(year)).intersection(train.index)
        train.loc[doubled] = train.loc[doubled] / 2
    share = (train > 0).mean()
    keep = [c for c in keep if share[c] >= rule.train_nonzero_share_min]
    steps.append(SelectionStep(name="training readings all nonzero", remaining=len(keep)))

    peak = train[keep].max()
    monthly = train[keep].resample("MS").max()
    keep = [
        c
        for c in keep
        if peak[c] <= rule.demand_kw_max_inclusive
        and _max_consecutive(monthly[c] > rule.demand_kw_min_exclusive)
        >= rule.consecutive_months_above_min
    ]
    steps.append(SelectionStep(name="B-19 demand range in training", remaining=len(keep)))
    if not keep:
        raise LookupError("no client satisfies the selection rule")

    keep.sort(key=_client_number)
    chosen = keep[0]
    return SelectionResult(
        client_id=chosen,
        candidates=keep,
        steps=steps,
        train_max_demand_kw=float(peak[chosen]),
        train_nonzero_share=float(share[chosen]),
    )
