"""Tariff applicability checks on the cleaned 15 minute series (UTC, interval-end labels)."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from edip.core.billing_demand import interval_demand, monthly_demand_all_hours


def monthly_max_demand(kw15: pd.Series, interval_minutes: int, clock: str) -> pd.Series:
    """Highest average kW over the utility's demand interval, per local calendar month."""
    return monthly_demand_all_hours(interval_demand(kw15, interval_minutes), clock)


class WindowCheck(BaseModel):
    window_end: str  # last month of the window
    months: int
    months_above_min: int
    months_above_max: int
    passed: bool


class EligibilityResult(BaseModel):
    tariff: str
    rule: str
    interval_minutes: int
    monthly_demand_kw_min: float
    monthly_demand_kw_max: float
    windows_checked: int
    windows_passed: int
    passed: bool
    worst_window: WindowCheck


def count_rule(
    monthly: pd.Series,
    *,
    tariff: str,
    rule: str,
    interval_minutes: int,
    window_months: int,
    above_kw: float,
    min_count_exclusive: int,
    cap_kw: float,
    cap_max_count: int,
) -> EligibilityResult:
    """Every full window: months with demand > above_kw must exceed min_count_exclusive,
    and months with demand > cap_kw must not exceed cap_max_count."""
    checks = []
    for end in range(window_months, len(monthly) + 1):
        win = monthly.iloc[end - window_months : end]
        above = int((win > above_kw).sum())
        over = int((win > cap_kw).sum())
        checks.append(
            WindowCheck(
                window_end=str(win.index[-1]),
                months=len(win),
                months_above_min=above,
                months_above_max=over,
                passed=above > min_count_exclusive and over <= cap_max_count,
            )
        )
    if not checks:
        raise ValueError("series shorter than one window")
    worst = min(checks, key=lambda c: (c.passed, c.months_above_min, -c.months_above_max))
    return EligibilityResult(
        tariff=tariff,
        rule=rule,
        interval_minutes=interval_minutes,
        monthly_demand_kw_min=float(monthly.min()),
        monthly_demand_kw_max=float(monthly.max()),
        windows_checked=len(checks),
        windows_passed=sum(c.passed for c in checks),
        passed=all(c.passed for c in checks),
        worst_window=worst,
    )


def pgn_schedule_85(kw15: pd.Series, clock: str) -> EligibilityResult:
    """Secondary: Demand > 200 kW more than six times in the preceding 13 months and
    not > 4,000 kW more than once (PGE Schedule 85; Demand is 30 minute, Rule B)."""
    monthly = monthly_max_demand(kw15, 30, clock)
    return count_rule(
        monthly,
        tariff="PGE Schedule 85 secondary",
        rule="Demand > 200 kW more than 6 times and > 4,000 kW at most once in 13 months",
        interval_minutes=30,
        window_months=13,
        above_kw=200,
        min_count_exclusive=6,
        cap_kw=4000,
        cap_max_count=1,
    )


def pge_b19(kw15: pd.Series, clock: str) -> tuple[EligibilityResult, int]:
    """Mandatory B-19: 15 minute demand > 499 kW in at least three consecutive months of
    the last 12, and below the B-20 threshold (1,000 kW) in every month (conservative).

    Returns the window result for the cap and the longest run of months above 499 kW.
    """
    monthly = monthly_max_demand(kw15, 15, clock)
    result = count_rule(
        monthly,
        tariff="PG&E B-19 secondary",
        rule="15 minute demand at most 999 kW in every month of each 12 month window",
        interval_minutes=15,
        window_months=12,
        above_kw=-1.0,
        min_count_exclusive=-1,
        cap_kw=999,
        cap_max_count=0,
    )
    run = best = 0
    for value in monthly:
        run = run + 1 if value > 499 else 0
        best = max(best, run)
    return result, best
