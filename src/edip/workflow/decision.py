"""Deterministic pilot decision: two verdicts, computed independently.

Frozen rule (config/acceptance_targets.yaml): withhold on any violation or a B-19
economics failure (neither ML nor robust passes); revise on a stress or coverage failure;
otherwise proceed, scoped to real tariffs where at least one of them passes.
Amendment A1 (docs/business_case.md, 2026-10-15, stricter): a strategy and tariff are in
scope only if net benefit is positive over no battery and over the fixed schedule; with no
such strategy the A1 verdict is withhold. Every check (violations, economics, A1, stress,
coverage) is always evaluated and reported; neither verdict short-circuits the others.
The A1 verdict is the live recommendation; the frozen verdict is shown next to it.
"""

from __future__ import annotations

from pydantic import BaseModel

from edip.agents.schemas import Decision

STRATEGIES = ("ml_forecast", "robust_quantile")
A1_REF = "docs/business_case.md#amendment-a1-2026-10-15-owner-decision"
_SEVERITY = {"proceed": 0, "revise": 1, "withhold": 2}


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


class Checks(BaseModel):
    violations: bool  # True = check passed
    b19_economics: bool
    a1_scope: list[tuple[str, str]]
    frozen_scope: list[tuple[str, str]]
    failed_stress: list[str]
    coverage_ok: bool


class DecisionResult(BaseModel):
    decision: Decision  # live: the A1 verdict
    scope: list[tuple[str, str]]  # (tariff, strategy), A1 scope
    reasons: list[str]
    frozen_decision: Decision
    frozen_scope: list[tuple[str, str]]
    frozen_reasons: list[str]
    a1_ref: str = A1_REF
    display: str


def checks(x: DecisionInputs) -> Checks:
    anchored = [s for s in x.strategies if s.tariff_id == x.anchored_tariff]
    target = [s for s in x.strategies if s.strategy in STRATEGIES and s.passes_target]
    return Checks(
        violations=x.violations == 0,
        b19_economics=any(s.passes_target for s in anchored if s.strategy in STRATEGIES),
        frozen_scope=sorted((s.tariff_id, s.strategy) for s in target),
        a1_scope=sorted(
            (s.tariff_id, s.strategy)
            for s in target
            if s.net_vs_no_battery_usd > 0 and s.net_vs_fixed_usd > 0
        ),
        failed_stress=sorted(t for t, ok in x.stress_passed.items() if not ok),
        coverage_ok=abs(x.coverage_pct - x.coverage_target) <= x.coverage_tolerance,
    )


def _frozen(c: Checks, x: DecisionInputs) -> tuple[Decision, list[str]]:
    reasons = []
    if not c.violations:
        reasons.append("constraint violations")
    if not c.b19_economics:
        reasons.append("B-19 economics target not met")
    if c.failed_stress:
        reasons.append(f"stress limits breached: {', '.join(c.failed_stress)}")
    if not c.coverage_ok:
        reasons.append(f"forecast coverage {x.coverage_pct:.1f}% outside 80 +/- 5")
    if not c.violations or not c.b19_economics:
        return "withhold", reasons
    if c.failed_stress or not c.coverage_ok:
        return "revise", reasons
    return "proceed", ["all criteria met"]


def decide(x: DecisionInputs) -> DecisionResult:
    c = checks(x)
    frozen, frozen_reasons = _frozen(c, x)
    a1: Decision = "withhold" if not c.a1_scope else "proceed"
    a1_reason = (
        ["amendment A1: no strategy beats both no battery and the fixed schedule"]
        if not c.a1_scope
        else []
    )
    live: Decision = max(frozen, a1, key=_SEVERITY.__getitem__)
    reasons = [r for r in frozen_reasons if r != "all criteria met"] + a1_reason
    return DecisionResult(
        decision=live,
        scope=c.a1_scope if live == "proceed" else [],
        reasons=reasons or ["all criteria met"],
        frozen_decision=frozen,
        frozen_scope=c.frozen_scope if frozen == "proceed" else [],
        frozen_reasons=frozen_reasons,
        display=f"Frozen rule: {frozen}. With amendment A1 (dated, stricter): {live}.",
    )
