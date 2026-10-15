"""Business decision agent: proceed, revise, or withhold with row citations (FR24, FR25)."""

from __future__ import annotations

from typing import Any

from edip.agents.evidence import EvidencePacket, check_business
from edip.agents.fallback import business_template
from edip.agents.llm import CallBudget, ModelClient, call_agent
from edip.agents.prompting import load_prompt, user_message
from edip.agents.schemas import AgentOutcome, BusinessResponse
from edip.workflow.decision import DecisionInputs


def run(
    context: dict[str, Any],
    packet: EvidencePacket,
    allowlist: dict[str, Any],
    client: ModelClient,
    budget: CallBudget,
    table: str,
    inputs: DecisionInputs,
) -> tuple[BusinessResponse, AgentOutcome]:
    version, system = load_prompt("business_v2")
    user = user_message({"Context": context, "Evidence rows": packet.as_prompt_rows()})
    return call_agent(
        agent="business",
        prompt_version=version,
        system=system,
        user=user,
        model_cls=BusinessResponse,
        client=client,
        budget=budget,
        validate=lambda r: check_business(r, allowlist, packet),
        fallback=lambda: business_template(table, inputs),
    )
