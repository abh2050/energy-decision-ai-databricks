"""Scenario consistency and the FR24 workflow order with a fake model."""

from pathlib import Path

import yaml

from edip.agents.llm import RawCompletion
from edip.agents.schemas import (
    BusinessResponse,
    PlanningResponse,
    RiskResponse,
    RiskTestSelection,
    ScenarioChange,
)
from edip.workflow.decision import decide
from edip.workflow.run import Scenario, agent_path, numbers_only_path

ROOT = Path(__file__).parents[2]
with (ROOT / "config" / "agent_allowlist.yaml").open() as fh:
    ALLOW = yaml.safe_load(fh)
SCENARIOS = [
    Scenario.model_validate(yaml.safe_load(p.read_text()))
    for p in sorted((ROOT / "evals" / "scenarios").glob("[sh]*.yaml"))
]
FR24 = [
    "operator_request",
    "planning_proposal",
    "operator_confirmation",
    "forecast",
    "optimization",
    "settlement_and_validation",
    "risk_challenge",
    "business_recommendation",
    "operator_decision",
]


def test_thirty_development_and_ten_held_out_scenarios_with_rule_consistent_answers():
    assert sum(s.id.startswith("s") for s in SCENARIOS) == 30
    held = [s for s in SCENARIOS if s.id.startswith("h")]
    assert len(held) == 10
    assert {s.kind for s in held} == {"objective_change", "adversarial", "scope"}
    kinds = {s.kind for s in SCENARIOS}
    assert {"standard", "objective_change", "stress", "adversarial", "scope"} <= kinds
    assert sum(s.kind == "adversarial" for s in SCENARIOS) >= 5
    for s in SCENARIOS:
        assert decide(s.cells[s.expected["target_cell"]]).decision == s.expected["decision"], s.id


class ScriptedModel:
    """Returns a fixed valid response per agent, keyed by the response schema."""

    def __init__(self):
        self.calls = []

    def complete(self, system, user, schema, max_tokens):
        title = schema.get("title")
        self.calls.append(title)
        if title == "PlanningResponse":
            body = PlanningResponse(
                interpretation="Evaluate the full-size battery",
                changes=[
                    ScenarioChange(
                        field="power_fraction",
                        new_value=1.0,
                        reason="asked",
                        quote="a battery sized to the full site peak",
                    ),
                    ScenarioChange(
                        field="duration_hours",
                        new_value=4,
                        reason="asked",
                        quote="4 hours of storage",
                    ),
                ],
            )
        elif title == "RiskResponse":
            body = RiskResponse(
                selection=RiskTestSelection(
                    tests=["forecast_error_injection", "heat_week_replay", "reserve_floor_raise"],
                    reason="all",
                )
            )
        else:
            body = BusinessResponse.model_validate_json(self._business())
        return RawCompletion(text=body.model_dump_json(), prompt_tokens=100, completion_tokens=50)

    @staticmethod
    def _business():
        return BusinessResponse(
            decision="proceed",
            rationale="r",
            claims=[
                {
                    "text": "violations",
                    "value": 0.0,
                    "evidence_ref": {"table": "t", "row_key": "summary", "column": "violations"},
                }
            ],
        ).model_dump_json()


def test_agent_path_runs_fr24_order_and_applies_confirmed_change():
    sc = next(s for s in SCENARIOS if s.id == "s09")
    model = ScriptedModel()
    result = agent_path(sc, model, ALLOW, "t")
    assert result.steps == FR24
    assert model.calls == ["PlanningResponse", "RiskResponse", "BusinessResponse"]  # one call each
    assert result.applied_settings["power_fraction"] == 1.0
    assert result.tests_run == [
        "forecast_error_injection",
        "heat_week_replay",
        "reserve_floor_raise",
    ]


def test_rejected_change_keeps_settings_and_numbers_only_is_one_call():
    sc = next(s for s in SCENARIOS if s.id == "s14")  # operator does not confirm
    result = agent_path(sc, ScriptedModel(), ALLOW, "t")
    assert result.applied_settings == sc.current_settings
    model = ScriptedModel()
    base = numbers_only_path(sc, model, ALLOW, "t")
    assert model.calls == ["BusinessResponse"]
    assert base.steps == ["operator_request", "numbers_only_recommendation"]


def test_planning_v3_quote_check():
    from edip.agents.evidence import EvidencePacket, check_planning
    from edip.agents.planning import keyword_map

    request = "Evaluate a battery sized to the full site peak with 4 hours of storage."
    ok = PlanningResponse(
        interpretation="x",
        changes=[
            ScenarioChange(
                field="power_fraction", new_value=1.0, reason="r", quote="full site peak"
            ),
            ScenarioChange(field="duration_hours", new_value=4, reason="r", quote="4 hours"),
        ],
    )
    packet = EvidencePacket(values={})
    assert check_planning(ok, ALLOW, packet, request, keyword_map()) == []
    missing = ok.model_copy(
        update={"changes": [ok.changes[0].model_copy(update={"quote": "half-size battery"})]}
    )
    assert any(
        "missing from the operator request" in r
        for r in check_planning(missing, ALLOW, packet, request, keyword_map())
    )
    unnamed = ok.model_copy(
        update={"changes": [ok.changes[1].model_copy(update={"quote": "Evaluate a battery"})]}
    )
    assert any(
        "does not name that field" in r
        for r in check_planning(unnamed, ALLOW, packet, request, keyword_map())
    )
    outside = ok.model_copy(
        update={
            "changes": [
                ScenarioChange(field="soc_min_fraction", new_value=0.0, reason="r", quote="battery")
            ]
        }
    )
    assert any(
        "outside the keyword map" in r
        for r in check_planning(outside, ALLOW, packet, request, keyword_map())
    )
