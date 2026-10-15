"""Gate 5 required tests: hard-constraint rejection, fabricated numbers, no retry."""

from pathlib import Path

import pytest
import yaml

from edip.agents.evidence import check_business, check_planning
from edip.agents.fallback import build_packet, business_template, planning_template
from edip.agents.llm import CallBudget, ModelTimeout, RawCompletion, call_agent
from edip.agents.schemas import (
    BusinessResponse,
    Claim,
    EvidenceRef,
    PlanningResponse,
    ScenarioChange,
)
from edip.workflow.decision import DecisionInputs, StrategyEvidence, decide

ROOT = Path(__file__).parents[2]
with (ROOT / "config" / "agent_allowlist.yaml").open() as fh:
    ALLOW = yaml.safe_load(fh)
TABLE = "edip.eval.scenario_evidence"


def _inputs(**kw):
    base = dict(
        violations=0,
        coverage_pct=80.5,
        stress_passed={
            "forecast_error_injection": True,
            "heat_week_replay": True,
            "reserve_floor_raise": True,
        },
        strategies=[
            StrategyEvidence(
                tariff_id="pge_b19_secondary",
                strategy="ml_forecast",
                passes_target=True,
                net_vs_no_battery_usd=12000.0,
                net_vs_fixed_usd=9000.0,
            ),
            StrategyEvidence(
                tariff_id="pge_b19_secondary",
                strategy="robust_quantile",
                passes_target=True,
                net_vs_no_battery_usd=-3006.0,
                net_vs_fixed_usd=24911.0,
            ),
        ],
    )
    base.update(kw)
    return DecisionInputs(**base)


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, 0

    def complete(self, system, user, schema, max_tokens):
        self.calls += 1
        if self.exc:
            raise self.exc
        return RawCompletion(text=self.text, prompt_tokens=10, completion_tokens=5)


def test_planning_change_to_hard_constraint_is_rejected():
    packet = build_packet(TABLE, _inputs())
    resp = PlanningResponse(
        interpretation="Raise usable capacity",
        changes=[ScenarioChange(field="soc_min_fraction", new_value=0.0, reason="more energy")],
    )
    reasons = check_planning(resp, ALLOW, packet)
    assert any("hard constraint soc_min_fraction" in r for r in reasons)
    ok = PlanningResponse(
        interpretation="Bigger battery",
        changes=[ScenarioChange(field="power_fraction", new_value=1.0, reason="peak")],
    )
    assert check_planning(ok, ALLOW, packet) == []
    bad_value = PlanningResponse(
        interpretation="x",
        changes=[ScenarioChange(field="power_fraction", new_value=2.0, reason="x")],
    )
    assert check_planning(bad_value, ALLOW, packet)


def test_fabricated_number_triggers_fallback():
    x = _inputs()
    packet = build_packet(TABLE, x)
    ref = EvidenceRef(
        table=TABLE,
        row_key="economics/pge_b19_secondary/ml_forecast",
        column="net_vs_no_battery_usd",
    )
    fabricated = BusinessResponse(
        decision="proceed",
        rationale="ML saves a lot",
        claims=[Claim(text="ML saves 50,000 USD per year", value=50000.0, evidence_ref=ref)],
    )
    client = FakeClient(text=fabricated.model_dump_json())
    result, outcome = call_agent(
        agent="business",
        prompt_version="test",
        system="s",
        user="u",
        model_cls=BusinessResponse,
        client=client,
        budget=CallBudget(),
        validate=lambda r: check_business(r, ALLOW, packet),
        fallback=lambda: business_template(TABLE, x),
    )
    assert outcome.used_fallback and outcome.status == "fallback"
    assert any("does not match" in r for r in outcome.rejection_reasons)
    assert result.rationale.startswith("Template:")
    assert check_business(result, ALLOW, packet) == []  # the fallback itself is fully supported


def test_supported_claim_passes_validation():
    x = _inputs()
    packet = build_packet(TABLE, x)
    ref = EvidenceRef(
        table=TABLE,
        row_key="economics/pge_b19_secondary/ml_forecast",
        column="net_vs_no_battery_usd",
    )
    good = BusinessResponse(
        decision="proceed",
        rationale="ML beats both baselines",
        claims=[
            Claim(
                text="ML net benefit over no battery is 12,000 USD per year",
                value=12000.0,
                evidence_ref=ref,
            )
        ],
    )
    assert check_business(good, ALLOW, packet) == []


def test_simulated_timeout_makes_no_second_call():
    client = FakeClient(exc=ModelTimeout("deadline"))
    budget = CallBudget()
    result, outcome = call_agent(
        agent="planning",
        prompt_version="test",
        system="s",
        user="u",
        model_cls=PlanningResponse,
        client=client,
        budget=budget,
        validate=lambda r: [],
        fallback=planning_template,
    )
    assert client.calls == 1
    assert outcome.calls_made == 1 and outcome.used_fallback
    assert "timeout" in outcome.rejection_reasons[0]
    with pytest.raises(RuntimeError):  # the workflow cannot call the same agent again
        call_agent(
            agent="planning",
            prompt_version="test",
            system="s",
            user="u",
            model_cls=PlanningResponse,
            client=client,
            budget=budget,
            validate=lambda r: [],
            fallback=planning_template,
        )
    assert client.calls == 1
    assert result.changes == []


def test_decision_rule_with_amendment():
    assert decide(_inputs()).decision == "proceed"
    assert decide(_inputs()).scope == [
        ("pge_b19_secondary", "ml_forecast")
    ]  # robust loses to no battery
    assert decide(_inputs(violations=1)).decision == "withhold"
    stressed = _inputs(
        stress_passed={
            "forecast_error_injection": False,
            "heat_week_replay": True,
            "reserve_floor_raise": True,
        }
    )
    assert decide(stressed).decision == "revise"
    assert decide(_inputs(coverage_pct=72.9)).decision == "revise"
    losing = _inputs(
        strategies=[
            StrategyEvidence(
                tariff_id="pge_b19_secondary",
                strategy="ml_forecast",
                passes_target=True,
                net_vs_no_battery_usd=-10624.0,
                net_vs_fixed_usd=17293.0,
            )
        ]
    )
    assert (
        decide(losing).decision == "withhold"
    )  # A1: passes the frozen target, loses to no battery


def test_both_verdicts_computed_independently():
    # Base-case shape: passes the frozen target, loses to no battery, stress fails.
    losing_stressed = _inputs(
        stress_passed={
            "forecast_error_injection": False,
            "heat_week_replay": False,
            "reserve_floor_raise": True,
        },
        strategies=[
            StrategyEvidence(
                tariff_id="pge_b19_secondary",
                strategy="robust_quantile",
                passes_target=True,
                net_vs_no_battery_usd=-3133.0,
                net_vs_fixed_usd=24784.0,
            )
        ],
    )
    r = decide(losing_stressed)
    assert r.frozen_decision == "revise" and r.decision == "withhold"
    assert r.display == "Frozen rule: revise. With amendment A1 (dated, stricter): withhold."
    # A1 does not short-circuit the stress check: the breach is still reported.
    assert any("forecast_error_injection, heat_week_replay" in x for x in r.reasons)
    assert any("amendment A1" in x for x in r.reasons)
    assert r.a1_ref.endswith("#amendment-a1-2026-10-15-owner-decision")
    ok = decide(_inputs())
    assert ok.frozen_decision == ok.decision == "proceed"
    assert ok.frozen_scope == [
        ("pge_b19_secondary", "ml_forecast"),
        ("pge_b19_secondary", "robust_quantile"),
    ]  # frozen scope uses the target only
    assert ok.scope == [("pge_b19_secondary", "ml_forecast")]  # A1 scope
