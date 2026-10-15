"""Deterministic template summaries used when an agent call fails or is rejected (FR26).

Numerical results stay usable: every template claim cites a row of the evidence packet,
and the business template applies the same decision rule the evaluation scores against.
"""

from __future__ import annotations

from edip.agents.evidence import EvidencePacket
from edip.agents.schemas import (
    BusinessResponse,
    Claim,
    EvidenceRef,
    PlanningResponse,
    RiskResponse,
    RiskTestSelection,
)
from edip.workflow.decision import DecisionInputs, DecisionResult, decide

STRESS_TESTS = ["forecast_error_injection", "heat_week_replay", "reserve_floor_raise"]


def build_packet(
    table: str, x: DecisionInputs, extra: dict[str, float | str] | None = None
) -> EvidencePacket:
    """Standard evidence rows: table|row_key|column -> value."""
    values: dict[str, float | str] = {
        f"{table}|summary|violations": float(x.violations),
        f"{table}|summary|coverage_pct": x.coverage_pct,
    }
    for test, ok in x.stress_passed.items():
        values[f"{table}|stress/{test}|passed"] = 1.0 if ok else 0.0
    for s in x.strategies:
        row = f"economics/{s.tariff_id}/{s.strategy}"
        values[f"{table}|{row}|passes_target"] = 1.0 if s.passes_target else 0.0
        values[f"{table}|{row}|net_vs_no_battery_usd"] = s.net_vs_no_battery_usd
        values[f"{table}|{row}|net_vs_fixed_usd"] = s.net_vs_fixed_usd
    values.update(extra or {})
    return EvidencePacket(values=values)


def _ref(table: str, row: str, column: str) -> EvidenceRef:
    return EvidenceRef(table=table, row_key=row, column=column)


def planning_template() -> PlanningResponse:
    return PlanningResponse(
        interpretation="Template: no scenario change proposed; the operator's settings stand.",
        changes=[],
        refused=[],
        claims=[],
    )


def risk_template(table: str, x: DecisionInputs) -> RiskResponse:
    findings = [
        Claim(
            text=f"Template: stress test {t} {'passed' if ok else 'breached'} the frozen limits.",
            value=1.0 if ok else 0.0,
            evidence_ref=_ref(table, f"stress/{t}", "passed"),
        )
        for t, ok in x.stress_passed.items()
    ]
    return RiskResponse(
        selection=RiskTestSelection(tests=list(STRESS_TESTS), reason="Template: run every test."),
        findings=findings,
        unresolved_risks=[f"{t} breached its limit" for t, ok in x.stress_passed.items() if not ok],
    )


def business_template(
    table: str, x: DecisionInputs, verdict: DecisionResult | None = None
) -> BusinessResponse:
    """`verdict`: the deterministic verdicts to restate (business prompt v3); otherwise the
    rule is applied to `x`."""
    result = verdict or decide(x)
    claims = [
        Claim(
            text="Template: accepted constraint violations.",
            value=float(x.violations),
            evidence_ref=_ref(table, "summary", "violations"),
        )
    ]
    for s in x.strategies:
        row = f"economics/{s.tariff_id}/{s.strategy}"
        claims.append(
            Claim(
                text=(
                    f"Template: {s.strategy} on {s.tariff_id}, "
                    "net benefit over no battery (USD per year)."
                ),
                value=s.net_vs_no_battery_usd,
                evidence_ref=_ref(table, row, "net_vs_no_battery_usd"),
            )
        )
    return BusinessResponse(
        decision=result.decision,
        scope_tariffs=sorted({t for t, _ in result.scope}),
        scope_strategies=sorted({s for _, s in result.scope}),
        rationale=f"Template: {result.display} " + "; ".join(result.reasons),
        claims=claims[:8],
    )
