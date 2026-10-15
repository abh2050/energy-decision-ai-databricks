"""Gate 5 evaluation harness: 30 scripted scenarios through the numbers-only and the
agent-assisted interfaces (PRD section 6).

Modes:
  --prepare   write the scenario evidence rows (persisted to Delta by the load job before
              any agent reads them, rule 4)
  --run       run both paths against the Foundation Model API, trace calls to MLflow,
              score them, and write results and sanitized traces

Claims are scored on the agents' raw responses (before any fallback), so a rejected answer
still counts against the agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel, ValidationError

from edip.agents.evidence import EvidencePacket, check_claims, check_comparisons
from edip.agents.fallback import build_packet
from edip.agents.schemas import BusinessResponse, Claim, PlanningResponse, RiskResponse
from edip.core.labels import REVISED
from edip.workflow.run import Scenario, WorkflowResult, agent_path, cell_key, numbers_only_path

ROOT = Path(__file__).resolve().parents[1]
TABLE = "edip.eval.scenario_evidence"
RESULTS = ROOT / "evals" / "results"
TRACES = ROOT / "frontend" / "public" / "data" / "traces"


def load_scenarios() -> list[Scenario]:
    return [
        Scenario.model_validate(yaml.safe_load(p.read_text()))
        for p in sorted((ROOT / "evals" / "scenarios").glob("s*.yaml"))
    ]


def evidence_rows(scenarios: list[Scenario]) -> pd.DataFrame:
    rows = []
    for sc in scenarios:
        for ck, inputs in sc.cells.items():
            for k, v in build_packet(TABLE, inputs).values.items():
                table, row_key, column = k.split("|", 2)
                rows.append(
                    {
                        "scenario_id": sc.id,
                        "cell": ck,
                        "table": table,
                        "row_key": row_key,
                        "column": column,
                        "value": float(v),
                        "label": "scripted for evaluation",
                    }
                )
    return pd.DataFrame(rows)


def _parse[M: BaseModel](model: type[M], text: str | None) -> M | None:
    if not text:
        return None
    try:
        return model.model_validate_json(text)
    except (ValidationError, ValueError):
        return None


def _claim_scores(
    claims: list[Claim], packet: EvidencePacket, comparisons: list[Any] | None = None
) -> tuple[int, int, int]:
    """(claims, supported claims, claims whose citation exists in the packet). Typed
    comparisons count as claims; a comparison is cited when every reference exists."""
    comparisons = comparisons or []
    supported = sum(not check_claims([c], packet) for c in claims)
    supported += sum(not check_comparisons([c], packet) for c in comparisons)
    cited = sum(packet.get(c.evidence_ref) is not None for c in claims)
    cited += sum(
        packet.get(c.left) is not None and (c.right is None or packet.get(c.right) is not None)
        for c in comparisons
    )
    return len(claims) + len(comparisons), supported, cited


def _text(*parts: Any) -> str:  # noqa: ANN401
    return " ".join(json.dumps(p, default=str) for p in parts).lower()


def score_agent(sc: Scenario, r: WorkflowResult) -> dict[str, Any]:
    exp = sc.expected
    current = sc.cells[cell_key(sc.current_settings)]
    seen_inputs = sc.cells.get(cell_key(r.applied_settings), current)
    seen = seen_inputs.model_copy(
        update={"stress_passed": {t: seen_inputs.stress_passed[t] for t in r.tests_run}}
    )
    packets = {
        "planning": build_packet(TABLE, current),
        "risk": build_packet(TABLE, seen_inputs),
        "business": build_packet(TABLE, seen),
    }
    out = {o.agent: o for o in r.outcomes}
    raw_plan = _parse(PlanningResponse, out["planning"].raw_text)
    raw_risk = _parse(RiskResponse, out["risk"].raw_text)
    raw_bus = _parse(BusinessResponse, out["business"].raw_text)
    totals = [0, 0, 0]
    for agent, raw, claims in (
        ("planning", raw_plan, raw_plan.claims if raw_plan else []),
        ("risk", raw_risk, raw_risk.findings if raw_risk else []),
        ("business", raw_bus, raw_bus.claims if raw_bus else []),
    ):
        comps = raw.comparisons if raw else []
        for i, v in enumerate(_claim_scores(claims, packets[agent], comps)):
            totals[i] += v
    required = set(exp["required_tests"])
    selected = set(raw_risk.selection.tests) if raw_risk else set()
    risk_text = _text(raw_risk.model_dump() if raw_risk else {}, r.business.model_dump())
    proposed = {c.field for c in raw_plan.changes} if raw_plan else set()
    must_refuse = set(exp["must_refuse"])
    hard_attempt = any("hard constraint" in reason for reason in out["planning"].rejection_reasons)
    changes_ok = (
        all(
            str(r.applied_settings.get(f)) == str(v)
            or float(r.applied_settings.get(f, -1)) == float(v)
            for f, v in exp["expected_changes"].items()
        )
        if sc.operator_confirms
        else r.applied_settings == sc.current_settings
    )
    return {
        "scenario_id": sc.id,
        "kind": sc.kind,
        "path": "agent_assisted",
        "expected_decision": exp["decision"],
        "decision": r.business.decision,
        "raw_business_decision": raw_bus.decision if raw_bus else None,
        "decision_correct": r.business.decision == exp["decision"],
        "scope_correct": _scope_ok(r.business, exp),
        "claims": totals[0],
        "claims_supported": totals[1],
        "claims_cited": totals[2],
        "required_tests": sorted(required),
        "selected_tests": sorted(selected),
        "stress_selection_correct": required <= selected if required else None,
        "risks_found": all(k.lower() in risk_text for k in exp["must_find_risks"])
        if exp["must_find_risks"]
        else None,
        "prohibited_refused_by_agent": (not (proposed & must_refuse) and not hard_attempt)
        if must_refuse
        else None,
        "prohibited_blocked_by_system": (
            not any(f in r.applied_settings for f in must_refuse) if must_refuse else None
        ),
        "planning_changes_correct": changes_ok
        if exp["expected_changes"] or not sc.operator_confirms
        else None,
        "unrequested_changes": sorted(proposed - set(exp["expected_changes"]) - must_refuse),
        "fallbacks": sum(o.used_fallback for o in r.outcomes),
        "model_calls": sum(o.calls_made for o in r.outcomes),
        "prompt_tokens": sum(o.prompt_tokens or 0 for o in r.outcomes),
        "completion_tokens": sum(o.completion_tokens or 0 for o in r.outcomes),
        "latency_s": sum(o.latency_s or 0 for o in r.outcomes),
        "prompt_versions": ",".join(sorted({o.prompt_version for o in r.outcomes})),
    }


def _scope_ok(rec: BusinessResponse, exp: dict[str, Any]) -> bool:
    if exp["decision"] != "proceed":
        return rec.decision == exp["decision"]
    tariffs = {t for t, _ in exp["scope"]}
    strategies = {s for _, s in exp["scope"]}
    return set(rec.scope_tariffs) == tariffs and set(rec.scope_strategies) == strategies


def score_numbers_only(sc: Scenario, r: WorkflowResult) -> dict[str, Any]:
    exp = sc.expected
    packet = build_packet(TABLE, sc.cells[cell_key(sc.current_settings)])
    o = r.outcomes[0]
    raw = _parse(BusinessResponse, o.raw_text)
    n, sup, cit = _claim_scores(raw.claims if raw else [], packet, raw.comparisons if raw else [])
    text = _text(r.business.model_dump())
    return {
        "scenario_id": sc.id,
        "kind": sc.kind,
        "path": "numbers_only",
        "expected_decision": exp["decision"],
        "decision": r.business.decision,
        "raw_business_decision": raw.decision if raw else None,
        "decision_correct": r.business.decision == exp["decision"],
        "scope_correct": _scope_ok(r.business, exp),
        "claims": n,
        "claims_supported": sup,
        "claims_cited": cit,
        "risks_found": all(k.lower() in text for k in exp["must_find_risks"])
        if exp["must_find_risks"]
        else None,
        "fallbacks": int(o.used_fallback),
        "model_calls": o.calls_made,
        "prompt_tokens": o.prompt_tokens or 0,
        "completion_tokens": o.completion_tokens or 0,
        "latency_s": o.latency_s or 0,
        "prompt_versions": o.prompt_version,
    }


def sanitized_trace(sc: Scenario, r: WorkflowResult) -> dict[str, Any]:
    """Recorded agent responses for the public sandbox: no hosts, users, or tokens."""
    return {
        "scenario_id": sc.id,
        "title": sc.title,
        "label": "recorded from the live system (scripted evaluation scenario)",
        "result_set": REVISED,
        "operator_objective": sc.operator_objective,
        "steps": r.steps,
        "applied_settings": r.applied_settings,
        "tests_run": r.tests_run,
        "planning": r.planning.model_dump() if r.planning else None,
        "risk": r.risk.model_dump() if r.risk else None,
        "business": r.business.model_dump(),
        "agents": [
            {
                "agent": o.agent,
                "prompt_version": o.prompt_version,
                "status": o.status,
                "used_fallback": o.used_fallback,
                "latency_s": round(o.latency_s or 0, 2),
            }
            for o in r.outcomes
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--profile", default="edip")
    parser.add_argument("--endpoint", default="databricks-meta-llama-3-3-70b-instruct")
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--only", nargs="*")
    parser.add_argument(
        "--business-prompt",
        default="business_v3",
        choices=["business_v1", "business_v2", "business_v3"],
    )
    parser.add_argument("--traces", action="store_true", help="export sandbox traces from this run")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    scenarios = load_scenarios()
    if args.only:
        scenarios = [s for s in scenarios if s.id in args.only]

    if args.prepare:
        ev = evidence_rows(scenarios)
        path = RESULTS / "scenario_evidence.parquet"
        ev.to_parquet(path, index=False)
        digest = hashlib.sha256(ev.to_csv(index=False).encode()).hexdigest()
        print(json.dumps({"rows": len(ev), "sha256": digest}))
        return 0

    import mlflow

    from edip.agents.llm import DatabricksModel

    os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment("/Shared/edip/gate5_agents")
    allow = yaml.safe_load((ROOT / "config" / "agent_allowlist.yaml").read_text())
    model = DatabricksModel(args.endpoint, args.timeout, args.profile)
    rows, traces = [], {}
    start = time.time()
    bp = args.business_prompt
    with mlflow.start_run(run_name=f"evaluation-{bp}"):
        mlflow.set_tags(
            {
                "gate": "6-review",
                "endpoint": args.endpoint,
                "scenarios": str(len(scenarios)),
                "business_prompt": bp,
                "result_set": REVISED,
            }
        )
        for sc in scenarios:
            with mlflow.start_span(name=f"scenario.{sc.id}.agent_assisted"):
                ra = agent_path(sc, model, allow, TABLE, business_prompt=bp)
            with mlflow.start_span(name=f"scenario.{sc.id}.numbers_only"):
                rn = numbers_only_path(sc, model, allow, TABLE, business_prompt=bp)
            rows += [score_agent(sc, ra), score_numbers_only(sc, rn)]
            traces[sc.id] = sanitized_trace(sc, ra)
            print(
                sc.id,
                ra.business.decision,
                rn.business.decision,
                sc.expected["decision"],
                flush=True,
            )
        df = pd.DataFrame(rows).assign(business_prompt=bp, result_set=REVISED)
        out = RESULTS / f"agent_evaluations_{bp}.parquet"
        df.to_parquet(out, index=False)
        mlflow.log_artifact(str(out))
        mlflow.log_metric("wall_seconds", time.time() - start)
    kept = RESULTS / f"traces_{bp}"
    for target in [kept, TRACES] if args.traces else [kept]:
        target.mkdir(parents=True, exist_ok=True)
        for sid, t in traces.items():
            (target / f"{sid}.json").write_text(json.dumps(t, indent=2, default=str) + "\n")
    print(json.dumps({"rows": len(df), "seconds": round(time.time() - start)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
