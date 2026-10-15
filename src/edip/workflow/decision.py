"""Deterministic pilot decision: the frozen rule plus business case amendment A1.

Frozen rule (config/acceptance_targets.yaml): withhold on any violation or a B-19
economics failure (neither ML nor robust passes); revise on a stress or coverage failure;
otherwise proceed, scoped to real tariffs where at least one of them passes.
Amendment A1 (docs/business_case.md, 2026-10-15): a strategy and tariff are in scope only
if net benefit is positive over no battery and over the fixed schedule. A1 is applied
before the stress and coverage checks: when no strategy qualifies, the result is withhold,
because revising for stress cannot fix a strategy that loses money.
"""

from __future__ import annotations

from pydantic import BaseModel

from edip.agents.schemas import Decision

STRATEGIES = ("ml_forecast", "robust_quantile")


class StrategyEvidence(BaseModel):
    tariff_id: str
    strategy: str
    passes_target: bool  # frozen economics target (strict reading)
    net_vs_no_battery_usd: float
    net_vs_fixed_usd: float


class DecisionInputs(BaseModel):
    violations: int
    coverage_pct: float
    coverage_target: float = 80.0
    coverage_tolerance: float = 5.0
    stress_passed: dict[str, bool]  # test name -> within the frozen stress limits
    strategies: list[StrategyEvidence]
    anchored_tariff: str = "pge_b19_secondary"


class DecisionResult(BaseModel):
    decision: Decision
    scope: list[tuple[str, str]]  # (tariff, strategy)
    reasons: list[str]


def decide(x: DecisionInputs) -> DecisionResult:
    reasons = []
    if x.violations > 0:
        return DecisionResult(decision="withhold", scope=[], reasons=["constraint violations"])
    anchored = [s for s in x.strategies if s.tariff_id == x.anchored_tariff]
    if not any(s.passes_target for s in anchored if s.strategy in STRATEGIES):
        return DecisionResult(
            decision="withhold", scope=[], reasons=["B-19 economics target not met"]
        )
    scope = [
        (s.tariff_id, s.strategy)
        for s in x.strategies
        if s.strategy in STRATEGIES
        and s.passes_target
        and s.net_vs_no_battery_usd > 0
        and s.net_vs_fixed_usd > 0
    ]
    if not scope:
        return DecisionResult(
            decision="withhold",
            scope=[],
            reasons=["amendment A1: no strategy beats both no battery and the fixed schedule"],
        )
    failed_stress = sorted(t for t, ok in x.stress_passed.items() if not ok)
    coverage_ok = abs(x.coverage_pct - x.coverage_target) <= x.coverage_tolerance
    if failed_stress or not coverage_ok:
        if failed_stress:
            reasons.append(f"stress limits breached: {', '.join(failed_stress)}")
        if not coverage_ok:
            reasons.append(f"forecast coverage {x.coverage_pct:.1f}% outside 80 +/- 5")
        return DecisionResult(decision="revise", scope=[], reasons=reasons)
    return DecisionResult(decision="proceed", scope=sorted(scope), reasons=["all criteria met"])
