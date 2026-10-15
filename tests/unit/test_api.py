"""Live app API: sign-in, server-side roles, the full decision flow, persistence, and the
one-call-per-agent rule (Gate 6). Synthetic snapshot; agents use the template fallback."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from edip.api.auth import identity_hash
from edip.api.data import AppData
from edip.api.main import NullModel, create_app
from edip.store.models import AgentCall
from edip.store.repo import DuplicateAgentCall, MemoryRepo

sys.path.insert(0, str(Path(__file__).parents[1]))
from fixture_data import build

OPERATOR = {"X-Forwarded-Email": "operator@example.com"}
VIEWER = {"X-Forwarded-Email": "viewer@example.com"}
SETTINGS = {
    "name": "base",
    "tariff_id": "pge_b19_secondary",
    "strategy": "robust_quantile",
    "power_fraction": 0.5,
    "duration_hours": 2,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EDIP_OPERATOR_HASHES", identity_hash("operator@example.com"))
    repo = MemoryRepo()
    app = create_app(AppData(build(tmp_path / "data")), repo, lambda: NullModel())
    c = TestClient(app)
    c.repo = repo
    return c


def test_sign_in_required(client):
    assert client.get("/api/meta").status_code == 401
    assert client.get("/api/meta", headers=VIEWER).json()["role"] == "viewer"
    assert client.get("/api/meta", headers=OPERATOR).json()["role"] == "operator"


def test_viewer_cannot_write(client):
    assert client.post("/api/scenarios", json=SETTINGS, headers=VIEWER).status_code == 403
    sid = client.post("/api/scenarios", json=SETTINGS, headers=OPERATOR).json()["scenario_id"]
    body = {"scenario_id": sid, "objective": "cut demand charges"}
    assert client.post("/api/runs", json=body, headers=VIEWER).status_code == 403


def test_hard_constraint_settings_rejected(client):
    bad = SETTINGS | {"power_fraction": 0.75}
    assert client.post("/api/scenarios", json=bad, headers=OPERATOR).status_code == 422


def test_full_decision_flow_persists(client):
    sid = client.post("/api/scenarios", json=SETTINGS, headers=OPERATOR).json()["scenario_id"]
    run = client.post(
        "/api/runs",
        json={"scenario_id": sid, "objective": "cut demand charges"},
        headers=OPERATOR,
    ).json()
    rid = run["run"]["run_id"]
    assert run["run"]["status"] == "planning_proposed"
    r = client.post(f"/api/runs/{rid}/confirm", json={"confirmed": True}, headers=OPERATOR)
    assert r.status_code == 200 and r.json()["run"]["status"] == "recommended"
    steps = [c["step"] for c in r.json()["checkpoints"]]
    assert steps == [
        "operator_request",
        "planning_proposal",
        "operator_confirmation",
        "forecast",
        "optimization",
        "settlement_and_validation",
        "risk_challenge",
        "business_recommendation",
    ]
    rec = r.json()["checkpoints"][-1]["payload"]
    assert rec["verdicts"]["display"].startswith("Frozen rule: ")
    assert rec["business"]["decision"] == rec["rule_on_agent_evidence"]["decision"]  # template
    # A second confirm is refused: each agent is called once per run.
    again = client.post(f"/api/runs/{rid}/confirm", json={"confirmed": True}, headers=OPERATOR)
    assert again.status_code == 409
    assert (
        client.post(
            f"/api/runs/{rid}/decision", json={"decision": "approve"}, headers=VIEWER
        ).status_code
        == 403
    )
    d = client.post(
        f"/api/runs/{rid}/decision",
        json={"decision": "approve", "comment": "pilot"},
        headers=OPERATOR,
    ).json()
    assert d["run"]["status"] == "decided" and d["approvals"][0]["decision"] == "approve"
    assert "actor_hash" not in d["approvals"][0]
    stored = client.repo.approvals(rid)[0]
    assert stored.actor_hash == identity_hash("operator@example.com")
    assert len(client.repo.agent_calls(rid)) == 3


def test_repo_enforces_one_call_per_agent():
    repo = MemoryRepo()
    call = AgentCall(
        call_id="a",
        run_id="r",
        agent="risk",
        endpoint="e",
        prompt_version="risk-v1",
        status="valid",
    )
    repo.add_agent_call(call)
    with pytest.raises(DuplicateAgentCall):
        repo.add_agent_call(call.model_copy(update={"call_id": "b"}))


def test_views_return_provenance(client):
    s = client.get("/api/strategies?cell=0.5/2", headers=VIEWER).json()
    assert len(s["rows"]) == 12 and s["source"]["sha256"]
    o = client.get("/api/operating?cell=0.5/2", headers=VIEWER).json()
    assert len(o["rows"]) == 24 and o["rows"][0]["p10"] is not None
    b = client.get("/api/business-case?cell=0.5/2", headers=VIEWER).json()
    assert b["verdicts"]["display"] == (
        "Frozen rule: revise. With amendment A1 (dated, stricter): withhold."
    )
    assert b["stress"][0]["retained_display"] == "not applicable, base case already loses money"
    m = client.get("/api/meta", headers=VIEWER).json()
    assert m["provenance"]["assumed"] and m["provenance"]["measured"]
