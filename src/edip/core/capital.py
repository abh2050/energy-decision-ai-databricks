"""Capital layer for the business case (owner decision 2026-10-15): installed cost from
the NREL/NLR 2025 ATB, simple payback, and NPV. Evidence only, not a gate."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel


class UnitCosts(BaseModel):
    case: str  # low, mid, high
    atb_scenario: str
    usd_per_kwh: float
    usd_per_kw: float


def unit_costs(capex: pd.DataFrame, cases: dict[str, str]) -> list[UnitCosts]:
    """Per-kWh and per-kW costs from ATB CAPEX ($/kW) at 2 and 4 hours."""
    out = []
    for case, scenario in cases.items():
        rows = capex[capex.scenario == scenario].set_index("techdetail")["value"]
        c2, c4 = float(rows["2Hr Battery Storage"]), float(rows["4Hr Battery Storage"])
        per_kwh = (c4 - c2) / 2
        out.append(
            UnitCosts(
                case=case, atb_scenario=scenario, usd_per_kwh=per_kwh, usd_per_kw=c2 - 2 * per_kwh
            )
        )
    return out


def installed_cost(costs: UnitCosts, power_kw: float, energy_kwh: float) -> float:
    return costs.usd_per_kwh * energy_kwh + costs.usd_per_kw * power_kw


def simple_payback_years(capex_usd: float, annual_net_benefit_usd: float) -> float | None:
    """Years to recover the installed cost; None when the annual net benefit is not positive."""
    return capex_usd / annual_net_benefit_usd if annual_net_benefit_usd > 0 else None


def npv(capex_usd: float, annual_net_benefit_usd: float, life_years: int, rate: float) -> float:
    annuity = sum(1 / (1 + rate) ** t for t in range(1, life_years + 1))
    return -capex_usd + annual_net_benefit_usd * annuity
