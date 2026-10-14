"""Battery specification from config/battery.yaml and the measured training peak (FR15)."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


class BatterySpec(BaseModel):
    power_kw: float = Field(gt=0)
    energy_kwh: float = Field(gt=0)
    eta_charge: float = Field(gt=0, le=1)
    eta_discharge: float = Field(gt=0, le=1)
    soc_min_kwh: float = Field(ge=0)
    soc_max_kwh: float = Field(gt=0)
    initial_soc_kwh: float = Field(ge=0)
    terminal_reserve_kwh: float = Field(ge=0)
    degradation_usd_per_kwh: float = Field(ge=0)

    @classmethod
    def from_config(
        cls,
        cfg: dict[str, Any],
        observed_peak_kw: float,
        *,
        power_fraction: float | None = None,
        duration_hours: float | None = None,
        round_trip_efficiency: float | None = None,
        degradation_usd_per_kwh: float | None = None,
    ) -> BatterySpec:
        base = cfg["base_case"]
        power = observed_peak_kw * (power_fraction or base["power_fraction_of_observed_peak"])
        energy = power * (duration_hours or base["duration_hours"])
        eta = math.sqrt(round_trip_efficiency or base["round_trip_efficiency"])
        deg = (
            degradation_usd_per_kwh
            if degradation_usd_per_kwh is not None
            else base["degradation_cost_usd_per_kwh_discharged"]
        )
        return cls(
            power_kw=power,
            energy_kwh=energy,
            eta_charge=eta,
            eta_discharge=eta,
            soc_min_kwh=energy * base["soc_min_fraction"],
            soc_max_kwh=energy * base["soc_max_fraction"],
            initial_soc_kwh=energy * base["initial_soc_fraction"],
            terminal_reserve_kwh=energy * base["terminal_reserve_fraction"],
            degradation_usd_per_kwh=deg,
        )

    def full_power_hours_to_empty(self) -> int:
        """Whole hours of full-power discharge needed to go from soc_max to soc_min."""
        usable = (self.soc_max_kwh - self.soc_min_kwh) * self.eta_discharge
        return math.ceil(usable / self.power_kw - 1e-9)
