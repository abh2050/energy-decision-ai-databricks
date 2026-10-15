"""Live decision workflow (FR24) across operator requests, persisted step by step.

1. `start`: operator request, then the planning proposal (one planning call).
2. `confirm`: operator confirmation or rejection; forecast, optimization, and settlement
   are the persisted 2014 replay of the confirmed battery cell (`cell_annual`,
   `cell_schedules`); risk challenge (one call), the selected stress tests read from the
   persisted stress results, and the business recommendation (one call).
3. `decide`: the operator approves, revises, or rejects.

Each step writes a checkpoint; each agent call is recorded once (Lakebase enforces one row
per agent per run). Both deterministic verdicts are stored next to the agent's
recommendation, and any disagreement is flagged for the operator.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable
from typing import Any

from edip.agents import business, planning, risk
from edip.agents.evidence import EvidencePacket
from edip.agents.llm import CallBudget, ModelClient
from edip.agents.schemas import AgentOutcome, PlanningResponse
from edip.api.data import AppData
from edip.store.models import AgentCall, Approval, Checkpoint, DecisionRun, Scenario
from edip.store.repo import Repo
from edip.workflow.decision import decide
from edip.workflow.run import apply_changes, cell_key

EVIDENCE_TABLE = "edip.eval.cell_evidence"
PROMPTS = {"planning": "planning-v1", "risk": "risk-v1", "business": "business-v2"}


class WorkflowError(Exception):
    """A request that does not fit the run's current step (HTTP 409)."""


def _hash(obj: Any) -> str:  # noqa: ANN401
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


class LiveWorkflow:
    def __init__(
        self,
        data: AppData,
        repo: Repo,
        client_factory: Callable[[], ModelClient],
        endpoint: str,
    ) -> None:
        self.data = data
        self.repo = repo
        self.client_factory = client_factory
        self.endpoint = endpoint
        self.allowlist = data.config("agent_allowlist.yaml")
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(run_id, threading.Lock())

    def _packet(self, cell: str) -> EvidencePacket:
        return EvidencePacket(values=self.data.evidence_values(cell, EVIDENCE_TABLE))

    def _checkpoint(self, run_id: str, step: str, payload: dict[str, Any]) -> None:
        self.repo.add_checkpoint(
            Checkpoint(checkpoint_id=uuid.uuid4().hex, run_id=run_id, step=step, payload=payload)
        )

    def _record(self, run_id: str, out: AgentOutcome) -> None:
        if any(c.agent == out.agent for c in self.repo.agent_calls(run_id)):
            raise WorkflowError(f"{out.agent} already called in this run")
        self.repo.add_agent_call(
            AgentCall(
                call_id=uuid.uuid4().hex,
                run_id=run_id,
                agent=out.agent,
                endpoint=self.endpoint,
                prompt_version=out.prompt_version,
                status=out.status,
                latency_ms=int((out.latency_s or 0) * 1000),
                prompt_tokens=out.prompt_tokens,
                completion_tokens=out.completion_tokens,
                mlflow_trace_id=out.trace_id,
                error_type="; ".join(out.rejection_reasons)[:500] or None,
            )
        )

    def _ensure_unused(self, run_id: str, agent: str) -> None:
        if any(c.agent == agent for c in self.repo.agent_calls(run_id)):
            raise WorkflowError(f"{agent} already called in this run (one call per agent)")

    def create_scenario(self, name: str, settings: dict[str, Any], role: str) -> Scenario:
        cell = cell_key(settings)
        if cell not in self.data.cells():
            raise WorkflowError(f"no persisted evidence for battery cell {cell}")
        s = Scenario(
            scenario_id=uuid.uuid4().hex[:12],
            name=name,
            description=None,
            settings=settings,
            settings_hash=_hash(settings),
            created_by_role=role,  # type: ignore[arg-type]
        )
        self.repo.put_scenario(s)
        return s

    def start(self, scenario_id: str, objective: str, concerns: str) -> str:
        sc = self.repo.get_scenario(scenario_id)
        if sc is None:
            raise WorkflowError("unknown scenario")
        m = self.data.manifest
        battery = self.data.config("battery.yaml")["base_case"]
        run_id = uuid.uuid4().hex[:16]
        self.repo.create_run(
            DecisionRun(
                run_id=run_id,
                scenario_id=scenario_id,
                status="requested",
                dataset_hash=m["dataset_sha256"],
                model_version=m["model_version"],
                tariff_hash=m["config_hashes"]["tariffs"],
                battery_hash=_hash({"battery": battery, "settings": sc.settings}),
                optimizer_settings=self.data.config("revised_strategy.yaml")
                | {"solver": m["solver"]},
                prompt_versions=PROMPTS,  # type: ignore[arg-type]
            )
        )
        self._checkpoint(
            run_id,
            "operator_request",
            {"objective": objective, "concerns": concerns, "settings": sc.settings},
        )
        with self._lock(run_id):
            self._ensure_unused(run_id, "planning")
            plan, out = planning.run(
                objective,
                sc.settings,
                self._packet(cell_key(sc.settings)),
                self.allowlist,
                self.client_factory(),
                CallBudget(),
            )
            self._record(run_id, out)
            self._checkpoint(
                run_id, "planning_proposal", {"planning": plan.model_dump(), "agent": _o(out)}
            )
            self.repo.set_status(run_id, "planning_proposed", _ids(out))
        return run_id

    def confirm(self, run_id: str, confirmed: bool) -> None:
        with self._lock(run_id):
            run = self._run(run_id, "planning_proposed")
            sc = self.repo.get_scenario(run.scenario_id)
            cps = {c.step: c.payload for c in self.repo.checkpoints(run_id)}
            plan = PlanningResponse.model_validate(cps["planning_proposal"]["planning"])
            req = cps["operator_request"]
            settings = apply_changes(sc.settings, plan, confirmed)
            cell = cell_key(settings)
            if cell not in self.data.cells():
                raise WorkflowError(f"no persisted evidence for battery cell {cell}")
            self._checkpoint(
                run_id,
                "operator_confirmation" if confirmed else "operator_rejected_change",
                {"applied_settings": settings, "cell": cell},
            )
            self.repo.set_status(run_id, "operator_confirmed", [])
            for step, status in (
                ("forecast", "forecasted"),
                ("optimization", "optimized"),
                ("settlement_and_validation", "settled"),
            ):
                self._checkpoint(run_id, step, self._replay_ref(step, cell, settings))
                self.repo.set_status(run_id, status, [])  # type: ignore[arg-type]
            inputs = self.data.decision_inputs(cell)
            packet = self._packet(cell)
            self._ensure_unused(run_id, "risk")
            rk, r_out = risk.run(
                settings,
                req.get("concerns", ""),
                packet,
                self.allowlist,
                self.client_factory(),
                CallBudget(),
                EVIDENCE_TABLE,
                inputs,
            )
            self._record(run_id, r_out)
            tests = sorted(set(rk.selection.tests))
            seen = inputs.model_copy(
                update={"stress_passed": {t: inputs.stress_passed[t] for t in tests}}
            )
            self._checkpoint(
                run_id,
                "risk_challenge",
                {"risk": rk.model_dump(), "tests_run": tests, "agent": _o(r_out)},
            )
            self.repo.set_status(run_id, "risk_reviewed", _ids(r_out))
            bpacket = EvidencePacket(
                values={
                    k: v
                    for k, v in packet.values.items()
                    if "|stress/" not in k or any(f"|stress/{t}|" in k for t in tests)
                }
            )
            self._ensure_unused(run_id, "business")
            rec, b_out = business.run(
                {"settings": settings, "stress_tests_run": tests, "objective": req["objective"]},
                bpacket,
                self.allowlist,
                self.client_factory(),
                CallBudget(),
                EVIDENCE_TABLE,
                seen,
            )
            self._record(run_id, b_out)
            rule_seen = decide(seen)
            verdicts = self.data.verdict(cell)
            self._checkpoint(
                run_id,
                "business_recommendation",
                {
                    "business": rec.model_dump(),
                    "agent": _o(b_out),
                    "rule_on_agent_evidence": rule_seen.model_dump(),
                    "verdicts": verdicts,
                    "agrees_with_rule": rec.decision == rule_seen.decision,
                    "agrees_with_live_verdict": rec.decision == verdicts["a1_decision"],
                },
            )
            self.repo.set_status(run_id, "recommended", _ids(b_out))

    def decide(self, run_id: str, decision: str, comment: str | None, actor_hash: str) -> None:
        with self._lock(run_id):
            self._run(run_id, "recommended")
            self.repo.add_approval(
                Approval(
                    approval_id=uuid.uuid4().hex,
                    run_id=run_id,
                    decision=decision,  # type: ignore[arg-type]
                    actor_role="operator",
                    actor_hash=actor_hash,
                    comment=comment,
                )
            )
            self._checkpoint(run_id, "operator_decision", {"decision": decision})
            self.repo.set_status(run_id, "decided", [])

    def _run(self, run_id: str, expected: str) -> DecisionRun:
        run = self.repo.get_run(run_id)
        if run is None:
            raise WorkflowError("unknown run")
        if run.status != expected:
            raise WorkflowError(f"run is {run.status}; this step needs {expected}")
        return run

    def _replay_ref(self, step: str, cell: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Pointer to the persisted replay rows this step stands for (no recomputation)."""
        tables = {
            "forecast": "forecasts",
            "optimization": "cell_schedules",
            "settlement_and_validation": "cell_annual",
        }
        t = tables[step]
        ref = self.data.manifest["tables"][t]
        out: dict[str, Any] = {
            "cell": cell,
            "source_table": ref["source"],
            "delta_version": ref["delta_version"],
            "sha256": ref["sha256"],
            "label": self.data.manifest["result_label"],
        }
        if step == "settlement_and_validation":
            a = self.data.table("cell_annual")
            a = a[(a.cell == cell) & (a.tariff_id == settings.get("tariff_id", a.tariff_id))]
            out["violations"] = int(a.violations.sum())
        return out

    def detail(self, run_id: str) -> dict[str, Any]:
        run = self.repo.get_run(run_id)
        if run is None:
            raise WorkflowError("unknown run")
        return {
            "run": run.model_dump(mode="json"),
            "scenario": (s := self.repo.get_scenario(run.scenario_id))
            and s.model_dump(mode="json"),
            "checkpoints": [c.model_dump(mode="json") for c in self.repo.checkpoints(run_id)],
            "agent_calls": [a.model_dump(mode="json") for a in self.repo.agent_calls(run_id)],
            "approvals": [
                a.model_dump(mode="json", exclude={"actor_hash"})
                for a in self.repo.approvals(run_id)
            ],
        }


def _o(out: AgentOutcome) -> dict[str, Any]:
    return out.model_dump(exclude={"raw_text"})


def _ids(out: AgentOutcome) -> list[str]:
    return [out.trace_id] if out.trace_id else []
