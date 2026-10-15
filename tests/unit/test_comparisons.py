"""Typed comparison claims and the business v3 verdict check (Gate 6 review, 2026-10-15)."""

from pathlib import Path

import yaml

from edip.agents.evidence import EvidencePacket, check_business, check_comparisons, check_planning
from edip.agents.schemas import (
    BusinessResponse,
    Claim,
    Comparison,
    EvidenceRef,
    PlanningResponse,
)

ROOT = Path(__file__).parents[2]
ALLOW = yaml.safe_load((ROOT / "config" / "agent_allowlist.yaml").read_text())
T = "edip.eval.cell_evidence"
ML = EvidenceRef(
    table=T, row_key="economics/pge_b19_secondary/ml_forecast", column="net_vs_fixed_usd"
)
ROBUST = EvidenceRef(
    table=T, row_key="economics/pge_b19_secondary/robust_quantile", column="net_vs_fixed_usd"
)
# The evidence the deployed planning agent saw in run 3d28cd3e9f3e4c49 (guard defect set).
PACKET = EvidencePacket(
    values={
        f"{T}|{ML.row_key}|{ML.column}": 17758.46,
        f"{T}|{ROBUST.row_key}|{ROBUST.column}": 24784.19,
    }
)


def test_regression_deployed_higher_net_savings_claim_is_rejected():
    """Deployed error: 'The ml_forecast strategy has a higher net savings.' citing 17,758
    USD, which is lower than robust's 24,784 USD."""
    untyped = PlanningResponse(
        interpretation="Consider ml_forecast.",
        claims=[
            Claim(
                text="The ml_forecast strategy has a higher net savings.",
                value=17758.46,
                evidence_ref=ML,
            )
        ],
    )
    reasons = check_planning(untyped, ALLOW, PACKET)
    assert any("untyped comparison" in r for r in reasons)

    typed = untyped.model_copy(
        update={
            "claims": [],
            "comparisons": [
                Comparison(
                    text="ml_forecast has a higher net savings than robust_quantile.",
                    left=ML,
                    operator=">",
                    right=ROBUST,
                )
            ],
        }
    )
    reasons = check_planning(typed, ALLOW, PACKET)
    assert any(r.startswith("false comparison") for r in reasons)


def test_true_comparisons_pass():
    ok = [
        Comparison(
            text="Robust beats ML against the fixed schedule.", left=ROBUST, operator=">", right=ML
        ),
        Comparison(text="ML net is above zero.", left=ML, operator=">", right_value=0.0),
        Comparison(text="Robust is 24,784 USD.", left=ROBUST, operator=">=", right=ML),
    ]
    assert check_comparisons(ok, PACKET) == []


def test_comparison_errors():
    missing = EvidenceRef(table=T, row_key="economics/x/y", column="net_vs_fixed_usd")
    assert check_comparisons(
        [Comparison(text="x", left=missing, operator=">", right_value=0.0)], PACKET
    )
    assert check_comparisons([Comparison(text="x", left=ML, operator=">")], PACKET)
    wrong_number = Comparison(text="ML is 99,999 USD.", left=ML, operator="<", right=ROBUST)
    assert any("99999" in r for r in check_comparisons([wrong_number], PACKET))


def test_plain_claims_without_comparisons_still_pass():
    claim = Claim(
        text="ML net against the fixed schedule is 17,758 USD.", value=17758.46, evidence_ref=ML
    )
    assert (
        check_planning(PlanningResponse(interpretation="No change.", claims=[claim]), ALLOW, PACKET)
        == []
    )


def test_business_v3_rejects_a_recommendation_that_differs_from_the_a1_verdict():
    resp = BusinessResponse(
        decision="revise",
        rationale="Stress limits are breached.",
        claims=[Claim(text="ML net against fixed.", value=17758.46, evidence_ref=ML)],
    )
    reasons = check_business(resp, ALLOW, PACKET, required_decision="withhold")
    assert any("differs from the A1 verdict withhold" in r for r in reasons)
    assert check_business(resp, ALLOW, PACKET, required_decision="revise") == []
    assert check_business(resp, ALLOW, PACKET) == []  # v1 and v2: no required decision
