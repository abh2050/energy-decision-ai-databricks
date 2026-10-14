"""Economics against the frozen acceptance targets (config/acceptance_targets.yaml).

net_benefit_gross = no-battery bill - strategy bill - degradation cost (before tax)
net_benefit       = gross minus the assumed annual operating cost for forecast-driven
                    strategies (frozen savings_basis); equal to gross otherwise
regret            = hindsight net_benefit_gross - strategy net_benefit_gross

The frozen file both deducts the operating cost inside net benefit and requires the
incremental benefit to exceed it. `passes` applies that literal, stricter reading (rule
11); `passes_single_count` applies the cost once, as the owner's approval wording reads.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from edip.core.strategies import FORECAST_DRIVEN
from edip.replay.replay import StrategyResult


class StrategyEconomics(BaseModel):
    tariff_id: str
    strategy: str
    bill_usd: float
    degradation_usd: float
    net_benefit_gross_usd: float
    operating_cost_usd: float
    net_benefit_usd: float
    regret_vs_hindsight_usd: float


class EconomicsCheck(BaseModel):
    tariff_id: str
    strategy: str
    fixed_net_benefit_usd: float
    incremental_usd: float  # frozen reading: both net of their own costs
    required_incremental_usd: float  # 10 percent of the fixed net benefit
    operating_cost_usd: float
    passes: bool  # frozen literal reading
    incremental_single_count_usd: float  # gross minus gross
    passes_single_count: bool


def economics(
    results: dict[str, StrategyResult], operating_cost_usd: float
) -> list[StrategyEconomics]:
    base = results["no_battery"].bill_usd
    hindsight_gross = base - results["hindsight"].bill_usd - results["hindsight"].degradation_usd
    out = []
    for name, r in results.items():
        gross = base - r.bill_usd - r.degradation_usd
        op = operating_cost_usd if name in FORECAST_DRIVEN else 0.0
        out.append(
            StrategyEconomics(
                tariff_id=r.tariff_id,
                strategy=name,
                bill_usd=r.bill_usd,
                degradation_usd=r.degradation_usd,
                net_benefit_gross_usd=gross,
                operating_cost_usd=op,
                net_benefit_usd=gross - op,
                regret_vs_hindsight_usd=hindsight_gross - gross,
            )
        )
    return out


def check_targets(
    econ: list[StrategyEconomics], targets: dict[str, Any], operating_cost_usd: float
) -> list[EconomicsCheck]:
    cfg = targets["dispatch_economics"]
    by = {e.strategy: e for e in econ}
    fixed = by[cfg["baseline"]]
    pct = cfg["min_incremental_pct_of_fixed_net_benefit"] / 100
    out = []
    for name in cfg["strategies"]:
        e = by[name]
        inc = e.net_benefit_usd - fixed.net_benefit_usd
        inc_single = e.net_benefit_gross_usd - fixed.net_benefit_gross_usd
        required = pct * fixed.net_benefit_usd
        required_single = pct * fixed.net_benefit_gross_usd
        out.append(
            EconomicsCheck(
                tariff_id=e.tariff_id,
                strategy=name,
                fixed_net_benefit_usd=fixed.net_benefit_usd,
                incremental_usd=inc,
                required_incremental_usd=required,
                operating_cost_usd=operating_cost_usd,
                passes=inc >= required and inc > operating_cost_usd,
                incremental_single_count_usd=inc_single,
                passes_single_count=inc_single >= required_single
                and inc_single > operating_cost_usd,
            )
        )
    return out
