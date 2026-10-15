"""Risk agent: chooses predefined stress tests and lists open risks (FR24, FR25).

One model call per workflow (PRD 3.6): the agent selects tests from the plan evidence; the
workflow then runs the selected tests deterministically and passes their results to the
business agent.
"""

from __future__ import annotations

from typing import Any

from edip.agents.evidence import EvidencePacket, check_risk
from edip.agents.fallback import risk_template
from edip.agents.llm import CallBudget, ModelClient, call_agent
from edip.agents.prompting import load_prompt, user_message
from edip.agents.schemas import AgentOutcome, RiskResponse
from edip.workflow.decision import DecisionInputs


def run(
    plan_summary: dict[str, Any],
    concerns: str,
    packet: EvidencePacket,
    allowlist: dict[str, Any],
    client: ModelClient,
    budget: CallBudget,
    table: str,
    inputs: DecisionInputs,
) -> tuple[RiskResponse, AgentOutcome]:
    version, system = load_prompt(
        "risk_v1", allowed_tests=allowlist["risk_agent"]["allowed_stress_tests"]
    )
    user = user_message(
        {
            "Plan": plan_summary,
            "Operator concerns": concerns,
            "Evidence rows": packet.as_prompt_rows(),
        }
    )
    return call_agent(
        agent="risk",
        prompt_version=version,
        system=system,
        user=user,
        model_cls=RiskResponse,
        client=client,
        budget=budget,
        validate=lambda r: check_risk(r, allowlist, packet),
        fallback=lambda: risk_template(table, inputs),
    )
