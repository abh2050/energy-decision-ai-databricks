"""Planning agent: plain-language objective to a typed scenario change (FR24, FR25)."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

from edip.agents.evidence import EvidencePacket, check_planning
from edip.agents.fallback import planning_template
from edip.agents.llm import CallBudget, ModelClient, call_agent
from edip.agents.prompting import load_prompt, user_message
from edip.agents.schemas import AgentOutcome, PlanningResponse

QUOTE_PROMPTS = {"planning_v3"}
KEYWORDS = Path(__file__).resolve().parents[3] / "config" / "planning_keywords.yaml"


@cache
def keyword_map() -> dict[str, list[str]]:
    return yaml.safe_load(KEYWORDS.read_text())["fields"]


def run(
    objective: str,
    settings: dict[str, Any],
    packet: EvidencePacket,
    allowlist: dict[str, Any],
    client: ModelClient,
    budget: CallBudget,
    prompt: str = "planning_v3",
) -> tuple[PlanningResponse, AgentOutcome]:
    """Planning v3 also requires each change to quote the objective (keyword map)."""
    cfg = allowlist["planning_agent"]
    version, system = load_prompt(
        prompt,
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
        validate=lambda r: check_planning(
            r,
            allowlist,
            packet,
            request=objective if prompt in QUOTE_PROMPTS else None,
            keyword_map=keyword_map() if prompt in QUOTE_PROMPTS else None,
        ),
        fallback=planning_template,
    )
