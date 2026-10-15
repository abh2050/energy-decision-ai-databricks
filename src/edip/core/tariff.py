"""Time of use tariffs (FR6, FR17): typed config with provenance, period lookup, stress sweep.

Load and optimization run on UTC hours. Tariff periods, seasons, and weekdays come from
the wall-clock time in `clock` (Europe/Lisbon, where the load was metered), so DST
transition days map 24 UTC hours onto 23 or 25 local clock hours.

Included: every per kWh and per kW charge of the schedule and of every adjustment
schedule that applies, plus any percentage charge the owner chose to model as a multiplier
on variable charges (PGE Schedule 108). Excluded: fixed monthly customer charges and
percentage taxes or franchise fees. All savings are reported before tax.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, Field, model_validator

ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]  # Monday = 0
CLOCK = "Europe/Lisbon"


class SourceDoc(BaseModel):
    id: str
    title: str
    url: str
    sha256: str
    sheet: str
    advice_letter: str
    effective_date: date
    retrieved: date
    status: Literal["current", "superseded", "corroborating", "synthetic"] = "current"
    note: str | None = None


class PeriodRule(BaseModel):
    """Local clock hours [start, end) on the given weekdays (and months, if set)."""

    season: str
    name: str
    hours: list[tuple[int, int]]
    weekdays: list[int] = Field(default_factory=lambda: list(ALL_DAYS))
    months: list[int] | None = None


class EnergyComponent(BaseModel):
    """A per kWh charge: flat, or by season and period. Rates as printed on the sheet."""

    name: str
    source: str
    cents_per_kwh: float | None = None
    usd_per_kwh: float | None = None
    by_period_usd_per_kwh: dict[str, dict[str, float]] | None = None
    by_period_cents_per_kwh: dict[str, dict[str, float]] | None = None
    applicability_note: str | None = None

    @model_validator(mode="after")
    def _one_form(self) -> EnergyComponent:
        forms = [
            self.cents_per_kwh,
            self.usd_per_kwh,
            self.by_period_usd_per_kwh,
            self.by_period_cents_per_kwh,
        ]
        if sum(f is not None for f in forms) != 1:
            raise ValueError(f"{self.name}: give exactly one rate form")
        return self

    def usd(self, season: str, period: str) -> float:
        if self.usd_per_kwh is not None:
            return self.usd_per_kwh
        if self.cents_per_kwh is not None:
            return self.cents_per_kwh / 100
        if self.by_period_usd_per_kwh is not None:
            return self.by_period_usd_per_kwh.get(season, {}).get(period, 0.0)
        return (self.by_period_cents_per_kwh or {}).get(season, {}).get(period, 0.0) / 100


class DemandCharge(BaseModel):
    """Monthly charge on the highest demand inside the window, per season."""

    name: str
    source: str
    rates_usd_per_kw: dict[str, float]
    periods: list[str] | None = None  # None = all hours
    hours: list[tuple[int, int]] | None = None  # local clock window instead of periods
    weekdays: list[int] = Field(default_factory=lambda: list(ALL_DAYS))
    tariff_interval_minutes: int  # how the utility measures demand


class FacilityCapacityCharge(BaseModel):
    """Per kW of the average of the `top_n` greatest monthly demands in a trailing window."""

    name: str
    source: str
    definition_source: str
    tiers_usd_per_kw: list[tuple[float | None, float]]  # (upper kW bound or None, rate)
    lookback_months: int = 12
    top_n: int = 2

    def monthly_charge(self, capacity_kw: float) -> float:
        charge, lower = 0.0, 0.0
        for upper, rate in self.tiers_usd_per_kw:
            top = capacity_kw if upper is None else min(capacity_kw, upper)
            if top > lower:
                charge += (top - lower) * rate
            if upper is None or capacity_kw <= upper:
                break
            lower = upper
        return charge


class VariableChargeMultiplier(BaseModel):
    """A percentage charge applied as a factor to every modelled variable charge
    (energy, demand, and facility capacity)."""

    name: str
    source: str
    factor: float = Field(gt=1)


class Exclusion(BaseModel):
    name: str
    source: str
    reason: str


class Tariff(BaseModel):
    id: str
    role: Literal["anchored", "low_spread", "stress"]
    synthetic: bool
    utility: str
    schedule: str
    voltage: str
    eligibility: str
    clock: str = CLOCK
    currency: Literal["USD"] = "USD"
    sources: list[SourceDoc]
    seasons: dict[str, list[int]]  # season -> local months
    default_period: str = "off_peak"
    period_rules: list[PeriodRule]
    energy_components: list[EnergyComponent]
    demand_charges: list[DemandCharge]
    facility_capacity: FacilityCapacityCharge | None = None
    variable_charge_multiplier: VariableChargeMultiplier | None = None
    savings_basis: Literal["before_tax"] = "before_tax"
    excluded: list[Exclusion]
    not_modelled: list[Exclusion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Tariff:
        months = sorted(m for ms in self.seasons.values() for m in ms)
        if months != list(range(1, 13)):
            raise ValueError("seasons must cover each month exactly once")
        ids = {s.id for s in self.sources}
        cited = [c.source for c in self.energy_components]
        cited += [c.source for c in self.demand_charges]
        cited += [e.source for e in self.excluded + self.not_modelled]
        if self.facility_capacity:
            cited += [self.facility_capacity.source, self.facility_capacity.definition_source]
        if self.variable_charge_multiplier:
            cited.append(self.variable_charge_multiplier.source)
        unknown = sorted(set(cited) - ids)
        if unknown:
            raise ValueError(f"charges cite unknown sources: {unknown}")
        if not self.synthetic and not self.sources:
            raise ValueError("a real tariff needs its source documents")
        return self

    @property
    def multiplier(self) -> float:
        """Factor on all modelled variable charges (1.0 when none applies)."""
        m = self.variable_charge_multiplier
        return m.factor if m else 1.0

    def season_of(self, month: int) -> str:
        return next(s for s, ms in self.seasons.items() if month in ms)

    def local_time(self, hour_start_utc: pd.DatetimeIndex) -> pd.DatetimeIndex:
        idx = hour_start_utc
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        return idx.tz_convert(self.clock)

    def classify(self, hour_start_utc: pd.DatetimeIndex) -> pd.DataFrame:
        """Local clock hour, season, and period for each UTC hour."""
        local = self.local_time(hour_start_utc)
        season = pd.Series([self.season_of(m) for m in local.month], index=hour_start_utc)
        period = pd.Series(self.default_period, index=hour_start_utc, dtype=object)
        for rule in self.period_rules:
            mask = (season == rule.season).to_numpy() & local.weekday.isin(rule.weekdays)
            if rule.months is not None:
                mask &= local.month.isin(rule.months)
            in_hours = pd.Series(False, index=hour_start_utc).to_numpy()
            for start, end in rule.hours:
                in_hours |= (local.hour >= start) & (local.hour < end)
            period[mask & in_hours] = rule.name
        return pd.DataFrame(
            {"local_hour": local.hour, "season": season, "period": period},
            index=hour_start_utc,
        )

    def energy_rate(self, hour_start_utc: pd.DatetimeIndex) -> pd.Series:
        """Total $ per kWh for each UTC hour: all components times the multiplier."""
        cls = self.classify(hour_start_utc)
        rates = [
            self.multiplier * sum(c.usd(s, p) for c in self.energy_components)
            for s, p in zip(cls["season"], cls["period"], strict=True)
        ]
        return pd.Series(rates, index=hour_start_utc, name="usd_per_kwh")

    def in_demand_window(self, charge: DemandCharge, hour_start_utc: pd.DatetimeIndex) -> pd.Series:
        local = self.local_time(hour_start_utc)
        mask = pd.Series(local.weekday.isin(charge.weekdays), index=hour_start_utc)
        if charge.hours is not None:
            in_hours = pd.Series(False, index=hour_start_utc)
            for start, end in charge.hours:
                in_hours |= (local.hour >= start) & (local.hour < end)
            mask &= in_hours
        if charge.periods is not None:
            mask &= self.classify(hour_start_utc)["period"].isin(charge.periods)
        return mask


class StressSweep(BaseModel):
    """Labelled synthetic tariffs from a base: off-peak fixed, chosen period gaps multiplied."""

    id_prefix: str
    role: Literal["stress"] = "stress"
    synthetic: Literal[True] = True
    derived_from: str
    widened_periods: list[str]
    reference_period: str = "off_peak"
    gap_multipliers: list[float]
    assumption: str


def expand_sweep(base: Tariff, sweep: StressSweep) -> list[Tariff]:
    """One tariff per multiplier m. In every season, for each widened period p:
    rate(p) = off_peak + m x (rate(p) - off_peak). Other rates and charges unchanged.

    Implemented as a synthetic uplift component so the base components stay intact.
    """
    synthetic_src = SourceDoc(
        id="synthetic",
        title=f"Synthetic stress tariff derived from {base.id}",
        url="config/tariffs/synthetic_high_spread.yaml",
        sha256="n/a",
        sheet="n/a",
        advice_letter="n/a",
        effective_date=date(1970, 1, 1),
        retrieved=date(1970, 1, 1),
        status="synthetic",
    )
    gaps: dict[str, dict[str, float]] = {}
    for season in base.seasons:
        ref = sum(c.usd(season, sweep.reference_period) for c in base.energy_components)
        for period in sweep.widened_periods:
            names = {r.name for r in base.period_rules if r.season == season}
            if period in names:
                rate = sum(c.usd(season, period) for c in base.energy_components)
                gaps.setdefault(season, {})[period] = rate - ref
    out = []
    for m in sweep.gap_multipliers:
        uplift = EnergyComponent(
            name=f"synthetic gap x{m:g} on {', '.join(sweep.widened_periods)}",
            source="synthetic",
            by_period_usd_per_kwh={
                s: {p: (m - 1) * g for p, g in per.items()} for s, per in gaps.items()
            },
        )
        out.append(
            base.model_copy(
                update={
                    "id": f"{sweep.id_prefix}_m{m:g}".replace(".", "_"),
                    "role": "stress",
                    "synthetic": True,
                    "sources": [*base.sources, synthetic_src],
                    "energy_components": [*base.energy_components, uplift],
                    "notes": [*base.notes, sweep.assumption, f"gap multiplier = {m:g}"],
                }
            )
        )
    return out


def load_tariffs(path: Path) -> list[Tariff]:
    """Load one tariff file; a sweep file returns one tariff per multiplier."""
    raw = yaml.safe_load(path.read_text())
    if "derived_from" in raw:
        sweep = StressSweep.model_validate(raw)
        (base,) = load_tariffs(path.parent / sweep.derived_from)
        return expand_sweep(base, sweep)
    return [Tariff.model_validate(raw)]


def load_tariff(path: Path) -> Tariff:
    (tariff,) = load_tariffs(path)
    return tariff


def scale_demand(tariff: Tariff, factor: float) -> Tariff:
    """Copy with every demand charge and Facility Capacity rate multiplied by `factor`
    (sensitivity grid dimension; factor 1.0 returns an equal tariff)."""
    charges = [
        c.model_copy(
            update={"rates_usd_per_kw": {s: r * factor for s, r in c.rates_usd_per_kw.items()}}
        )
        for c in tariff.demand_charges
    ]
    update: dict = {"demand_charges": charges}
    if tariff.facility_capacity is not None:
        fc = tariff.facility_capacity
        update["facility_capacity"] = fc.model_copy(
            update={"tiers_usd_per_kw": [(u, r * factor) for u, r in fc.tiers_usd_per_kw]}
        )
    if factor != 1.0:
        update["notes"] = [*tariff.notes, f"SENSITIVITY: demand charges x{factor:g}"]
    return tariff.model_copy(update=update)
