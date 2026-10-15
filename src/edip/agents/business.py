"""Business decision agent (FR24, FR25).

Prompts v1 and v2 ask the model to apply the decision rule. Prompt v3 (Gate 6 review,
2026-10-15) gives the model both deterministic verdicts and asks only for the explanation,
scope, and evidence; a response whose recommendation differs from the A1 verdict is
rejected and the template answers.
"""

from __future__ import annotations

from typing import Any

from edip.agents.evidence import EvidencePacket, check_business
from edip.agents.fallback import business_template
from edip.agents.llm import CallBudget, ModelClient, call_agent
from edip.agents.prompting import load_prompt, user_message
from edip.agents.schemas import AgentOutcome, BusinessResponse
from edip.workflow.decision import DecisionInputs, DecisionResult

VERDICT_PROMPTS = {"business_v3"}


def verdict_context(v: DecisionResult) -> dict[str, Any]:
    return {
        "frozen_rule": {
            "decision": v.frozen_decision,
            "reasons": v.frozen_reasons,
            "scope": [list(s) for s in v.frozen_scope],
        },
        "amendment_a1": {
            "decision": v.decision,
            "reasons": v.reasons,
            "scope": [list(s) for s in v.scope],
            "note": "stricter; this is the recommendation",
        },
    }


def run(
    context: dict[str, Any],
    packet: EvidencePacket,
    allowlist: dict[str, Any],
    client: ModelClient,
    budget: CallBudget,
    table: str,
    inputs: DecisionInputs,
    prompt: str = "business_v3",
    verdict: DecisionResult | None = None,
) -> tuple[BusinessResponse, AgentOutcome]:
    """`verdict`: the deterministic verdicts for the cell (required for v3)."""
    version, system = load_prompt(prompt)
    sections: dict[str, Any] = {"Context": context}
    required = None
    if prompt in VERDICT_PROMPTS:
        if verdict is None:
            raise ValueError(f"{prompt} needs the deterministic verdicts")
        sections["Deterministic verdicts"] = verdict_context(verdict)
        required = verdict.decision
    sections["Evidence rows"] = packet.as_prompt_rows()
    return call_agent(
        agent="business",
        prompt_version=version,
        system=system,
        user=user_message(sections),
        model_cls=BusinessResponse,
        client=client,
        budget=budget,
        validate=lambda r: check_business(r, allowlist, packet, required_decision=required),
        fallback=lambda: business_template(table, inputs, verdict if required else None),
    )
