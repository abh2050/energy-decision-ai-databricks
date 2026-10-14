"""Time of use tariffs (FR6, FR17): typed config, period lookup, and derived stress tariffs.

Tariff windows are applied to the load's clock, Portuguese standard time (assumption:
the US tariff's local clock is mapped onto the load's standard-time hours). Fixed
charges, riders, and taxes are excluded from savings; each file lists its exclusions.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, Field, model_validator

ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]  # Monday = 0


class Source(BaseModel):
    url: str
    retrieved: date
    sha256: str
    advice_letter: str
    effective_date: date
    sheets: list[str]


class PeriodRule(BaseModel):
    """Hours [start, end) on the given weekdays (and months, if set) in one season."""

    season: str
    name: str
    hours: list[tuple[int, int]]
    weekdays: list[int] = Field(default_factory=lambda: list(ALL_DAYS))
    months: list[int] | None = None


class DemandCharge(BaseModel):
    """Monthly charge on the highest hourly kW inside the window, per season."""

    name: str
    rates_usd_per_kw: dict[str, float]
    periods: list[str] | None = None  # None = all hours
    hours: list[tuple[int, int]] | None = None  # explicit window instead of periods
    weekdays: list[int] = Field(default_factory=lambda: list(ALL_DAYS))


class Tariff(BaseModel):
    id: str
    role: Literal["anchored", "low_spread", "stress"]
    synthetic: bool
    utility: str
    schedule: str
    voltage: str
    eligibility: str
    source: Source | None
    currency: Literal["USD"] = "USD"
    seasons: dict[str, list[int]]  # season -> months
    default_period: str = "off_peak"
    period_rules: list[PeriodRule]
    energy_usd_per_kwh: dict[str, dict[str, float]]  # season -> period -> rate
    demand_charges: list[DemandCharge]
    excluded_from_savings: list[str]
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Tariff:
        months = sorted(m for ms in self.seasons.values() for m in ms)
        if months != list(range(1, 13)):
            raise ValueError("seasons must cover each month exactly once")
        for season, rates in self.energy_usd_per_kwh.items():
            if season not in self.seasons:
                raise ValueError(f"unknown season {season}")
            names = {r.name for r in self.period_rules if r.season == season}
            missing = (names | {self.default_period}) - set(rates)
            if missing:
                raise ValueError(f"{season}: no energy rate for {sorted(missing)}")
        if not self.synthetic and self.source is None:
            raise ValueError("a real tariff needs its source document")
        return self

    def season_of(self, month: int) -> str:
        return next(s for s, ms in self.seasons.items() if month in ms)

    def classify(self, hour_start: pd.DatetimeIndex) -> pd.DataFrame:
        """Season and period for each hour (hour_start on the tariff clock)."""
        season = pd.Series([self.season_of(m) for m in hour_start.month], index=hour_start)
        period = pd.Series(self.default_period, index=hour_start, dtype=object)
        for rule in self.period_rules:
            mask = (season == rule.season).to_numpy()
            mask &= hour_start.weekday.isin(rule.weekdays)
            if rule.months is not None:
                mask &= hour_start.month.isin(rule.months)
            in_hours = pd.Series(False, index=hour_start).to_numpy()
            for start, end in rule.hours:
                in_hours |= (hour_start.hour >= start) & (hour_start.hour < end)
            period[mask & in_hours] = rule.name
        return pd.DataFrame({"season": season, "period": period})

    def energy_rate(self, hour_start: pd.DatetimeIndex) -> pd.Series:
        cls = self.classify(hour_start)
        return pd.Series(
            [self.energy_usd_per_kwh[s][p] for s, p in zip(cls.season, cls.period, strict=True)],
            index=hour_start,
            name="usd_per_kwh",
        )

    def in_demand_window(self, charge: DemandCharge, hour_start: pd.DatetimeIndex) -> pd.Series:
        mask = pd.Series(hour_start.weekday.isin(charge.weekdays), index=hour_start)
        if charge.hours is not None:
            in_hours = pd.Series(False, index=hour_start)
            for start, end in charge.hours:
                in_hours |= (hour_start.hour >= start) & (hour_start.hour < end)
            mask &= in_hours
        if charge.periods is not None:
            mask &= self.classify(hour_start)["period"].isin(charge.periods)
        return mask


class DerivedStress(BaseModel):
    """A labelled synthetic tariff built from a real one by widening its energy spread."""

    id: str
    role: Literal["stress"] = "stress"
    synthetic: Literal[True] = True
    derived_from: str
    energy_spread_multiplier: float = Field(gt=1)
    reference_period: str = "off_peak"
    assumption: str


def derive_stress(base: Tariff, spec: DerivedStress) -> Tariff:
    """rate' = ref + k * (rate - ref) per season, where ref is the season's off-peak rate."""
    energy = {}
    for season, rates in base.energy_usd_per_kwh.items():
        ref = rates[spec.reference_period]
        energy[season] = {
            p: round(ref + spec.energy_spread_multiplier * (r - ref), 5) for p, r in rates.items()
        }
    return base.model_copy(
        update={
            "id": spec.id,
            "role": "stress",
            "synthetic": True,
            "energy_usd_per_kwh": energy,
            "notes": [*base.notes, spec.assumption],
        }
    )


def load_tariff(path: Path, tariffs_dir: Path | None = None) -> Tariff:
    raw = yaml.safe_load(path.read_text())
    if raw.get("status") == "pending_official_sheet":
        raise ValueError(f"{path.name}: rates not yet encoded from the official sheet")
    if "derived_from" in raw:
        spec = DerivedStress.model_validate(raw)
        base = load_tariff((tariffs_dir or path.parent) / spec.derived_from)
        return derive_stress(base, spec)
    return Tariff.model_validate(raw)
