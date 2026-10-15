"""Deterministic decision workflow (FR24): operator request, planning proposal, operator
confirmation, forecast, optimization, settlement and validation, risk challenge, business
recommendation, operator decision. Numbers come from persisted evidence; agents only read.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from edip.agents import business, planning, risk
from edip.agents.evidence import check_business
from edip.agents.fallback import build_packet, business_template
from edip.agents.llm import CallBudget, ModelClient, call_agent
from edip.agents.prompting import load_prompt, user_message
from edip.agents.schemas import AgentOutcome, BusinessResponse, PlanningResponse, RiskResponse
from edip.workflow.decision import DecisionInputs

CELL_FIELDS = ("power_fraction", "duration_hours")


class Scenario(BaseModel):
    id: str
    title: str
    kind: str  # e.g. standard, objective_change, adversarial
    operator_objective: str
    operator_concerns: str = ""
    operator_confirms: bool = True
    current_settings: dict[str, Any]
    cells: dict[str, DecisionInputs]  # key "power_fraction/duration_hours"
    expected: dict[str, Any]


def cell_key(settings: dict[str, Any]) -> str:
    return f"{float(settings['power_fraction']):g}/{int(settings['duration_hours'])}"


class WorkflowResult(BaseModel):
    scenario_id: str
    steps: list[str]
    planning: PlanningResponse | None = None
    applied_settings: dict[str, Any]
    risk: RiskResponse | None = None
    tests_run: list[str]
    business: BusinessResponse
    outcomes: list[AgentOutcome]


def apply_changes(
    settings: dict[str, Any], resp: PlanningResponse, confirmed: bool
) -> dict[str, Any]:
    out = dict(settings)
    if not confirmed:
        return out
    for change in resp.changes:
        if change.field in CELL_FIELDS or change.field in ("tariff_id", "strategy"):
            out[change.field] = change.new_value
    return out


def agent_path(
    sc: Scenario, client: ModelClient, allowlist: dict[str, Any], table: str
) -> WorkflowResult:
    budget = CallBudget()
    steps = ["operator_request"]
    current = sc.cells[cell_key(sc.current_settings)]
    plan_packet = build_packet(table, current)
    plan, p_out = planning.run(
        sc.operator_objective, sc.current_settings, plan_packet, allowlist, client, budget
    )
    steps += [
        "planning_proposal",
        "operator_confirmation" if sc.operator_confirms else "operator_rejected",
    ]
    settings = apply_changes(sc.current_settings, plan, sc.operator_confirms)
    key = cell_key(settings)
    inputs = sc.cells.get(key, current)
    steps += ["forecast", "optimization", "settlement_and_validation"]
    packet = build_packet(table, inputs)
    rk, r_out = risk.run(
        settings, sc.operator_concerns, packet, allowlist, client, budget, table, inputs
    )
    tests = sorted(set(rk.selection.tests))
    steps.append("risk_challenge")
    seen = inputs.model_copy(update={"stress_passed": {t: inputs.stress_passed[t] for t in tests}})
    bpacket = build_packet(table, seen)
    rec, b_out = business.run(
        {"settings": settings, "stress_tests_run": tests, "objective": sc.operator_objective},
        bpacket,
        allowlist,
        client,
        budget,
        table,
        seen,
    )
    steps += ["business_recommendation", "operator_decision"]
    return WorkflowResult(
        scenario_id=sc.id,
        steps=steps,
        planning=plan,
        applied_settings=settings,
        risk=rk,
        tests_run=tests,
        business=rec,
        outcomes=[p_out, r_out, b_out],
    )


def numbers_only_path(
    sc: Scenario, client: ModelClient, allowlist: dict[str, Any], table: str
) -> WorkflowResult:
    """Baseline: one call that sees the current settings' numbers, all stress results
    included, and the operator's objective, with no planning or risk agent."""
    budget = CallBudget()
    inputs = sc.cells[cell_key(sc.current_settings)]
    packet = build_packet(table, inputs)
    version, system = load_prompt("business_v2")
    user = user_message(
        {
            "Context": {"settings": sc.current_settings, "objective": sc.operator_objective},
            "Evidence rows": packet.as_prompt_rows(),
        }
    )
    rec, out = call_agent(
        agent="business",
        prompt_version=version + "+numbers-only",
        system=system,
        user=user,
        model_cls=BusinessResponse,
        client=client,
        budget=budget,
        validate=lambda r: check_business(r, allowlist, packet),
        fallback=lambda: business_template(table, inputs),
    )
    return WorkflowResult(
        scenario_id=sc.id,
        steps=["operator_request", "numbers_only_recommendation"],
        applied_settings=sc.current_settings,
        tests_run=sorted(inputs.stress_passed),
        business=rec,
        outcomes=[out],
    )
