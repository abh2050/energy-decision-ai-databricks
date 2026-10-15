"""Planning agent: plain-language objective to a typed scenario change (FR24, FR25)."""

from __future__ import annotations

from typing import Any

from edip.agents.evidence import EvidencePacket, check_planning
from edip.agents.fallback import planning_template
from edip.agents.llm import CallBudget, ModelClient, call_agent
from edip.agents.prompting import load_prompt, user_message
from edip.agents.schemas import AgentOutcome, PlanningResponse


def run(
    objective: str,
    settings: dict[str, Any],
    packet: EvidencePacket,
    allowlist: dict[str, Any],
    client: ModelClient,
    budget: CallBudget,
) -> tuple[PlanningResponse, AgentOutcome]:
    cfg = allowlist["planning_agent"]
    version, system = load_prompt(
        "planning_v1",
        allowed_fields=cfg["allowed_fields"],
        hard_constraints=cfg["hard_constraints"],
    )
    user = user_message(
        {
            "Operator objective": objective,
            "Current settings": settings,
            "Evidence rows": packet.as_prompt_rows(),
        }
    )
    return call_agent(
        agent="planning",
        prompt_version=version,
        system=system,
        user=user,
        model_cls=PlanningResponse,
        client=client,
        budget=budget,
        validate=lambda r: check_planning(r, allowlist, packet),
        fallback=planning_template,
    )
