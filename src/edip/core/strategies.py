"""The six dispatch strategies under equal physical constraints (FR16).

no_battery        no battery
fixed_schedule    forecast-free rule (config/battery.yaml#fixed_schedule)
seasonal_forecast optimizer on the previous-week forecast
ml_forecast       optimizer on the LightGBM point forecast
robust_quantile   optimizer on P90 in the protected periods, P50 otherwise
hindsight         optimizer on actual load (benchmark)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from edip.core.battery import BatterySpec
from edip.core.tariff import DemandCharge, Tariff

STRATEGIES = (
    "no_battery",
    "fixed_schedule",
    "seasonal_forecast",
    "ml_forecast",
    "robust_quantile",
    "hindsight",
)
OPTIMIZED = ("seasonal_forecast", "ml_forecast", "robust_quantile", "hindsight")
FORECAST_DRIVEN = ("seasonal_forecast", "ml_forecast", "robust_quantile")
OFF_PEAK_PERIODS = ("off_peak", "super_off_peak")


def planning_load(
    strategy: str,
    day: pd.DataFrame,
    tariff: Tariff,
    protected_periods: list[str],
) -> np.ndarray:
    """The hourly load a strategy plans on. `day` has 24 rows indexed by UTC hour with
    columns actual, seasonal, point, p50, p90."""
    if strategy == "seasonal_forecast":
        return day["seasonal"].to_numpy()
    if strategy == "ml_forecast":
        return day["point"].to_numpy()
    if strategy == "robust_quantile":
        protected = tariff.classify(day.index)["period"].isin(protected_periods).to_numpy()
        return np.where(protected, day["p90"].to_numpy(), day["p50"].to_numpy())
    if strategy == "hindsight":
        return day["actual"].to_numpy()
    raise ValueError(f"{strategy} does not plan on a load")


class FixedRule(BaseModel):
    """Local hours to discharge at full power, per season, and the window's charge name."""

    tariff_id: str
    window_charge: str
    discharge_hours: dict[str, list[int]]


def demand_window_charge(tariff: Tariff, window: str) -> DemandCharge:
    """The demand charge whose window defines the fixed schedule's discharge hours."""
    if window == "peak_demand_hours":
        return next(c for c in tariff.demand_charges if c.hours is not None)
    return next(c for c in tariff.demand_charges if c.periods == [window])


def fixed_rule(tariff: Tariff, window: str, train_kw: pd.Series, spec: BatterySpec) -> FixedRule:
    """Rank local hours inside the demand window by training-period average load, per
    season, and keep as many as a full-power discharge from soc_max to soc_min needs."""
    charge = demand_window_charge(tariff, window)
    idx = train_kw.index
    in_window = tariff.in_demand_window(charge, idx).to_numpy()
    local = tariff.local_time(idx)
    seasons = np.array([tariff.season_of(m) for m in local.month])
    frame = pd.DataFrame({"kw": train_kw.to_numpy(), "hour": local.hour, "season": seasons})
    frame = frame[in_window]
    k = spec.full_power_hours_to_empty()
    hours = {}
    for season in tariff.seasons:
        avg = frame[frame.season == season].groupby("hour")["kw"].mean()
        hours[season] = sorted(int(h) for h in avg.sort_values(ascending=False).index[:k])
    return FixedRule(tariff_id=tariff.id, window_charge=charge.name, discharge_hours=hours)


def fixed_plan(
    hours_utc: pd.DatetimeIndex, tariff: Tariff, rule: FixedRule, spec: BatterySpec, soc0: float
) -> tuple[np.ndarray, np.ndarray]:
    """Charge at full power from 00:00 local in off-peak hours until soc_max (before the
    first discharge hour); discharge at full power in the ranked hours until soc_min."""
    charge = next(c for c in tariff.demand_charges if c.name == rule.window_charge)
    window = tariff.in_demand_window(charge, hours_utc).to_numpy()
    cls = tariff.classify(hours_utc)
    c = np.zeros(len(hours_utc))
    d = np.zeros(len(hours_utc))
    soc = soc0
    for t in range(len(hours_utc)):
        season, hour = cls["season"].iloc[t], int(cls["local_hour"].iloc[t])
        ranked = rule.discharge_hours.get(season, [])
        if window[t] and hour in ranked:
            d[t] = min(spec.power_kw, max(soc - spec.soc_min_kwh, 0.0) * spec.eta_discharge)
            soc -= d[t] / spec.eta_discharge
        elif cls["period"].iloc[t] in OFF_PEAK_PERIODS and hour < min(ranked or [24]):
            c[t] = min(spec.power_kw, max(spec.soc_max_kwh - soc, 0.0) / spec.eta_charge)
            soc += spec.eta_charge * c[t]
    return c, d
