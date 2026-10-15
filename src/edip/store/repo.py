"""Operational state for the live app: scenarios, decision runs, checkpoints, approvals,
and agent calls (PRD section 5). `LakebaseRepo` is the deployed store; `MemoryRepo` has
the same behaviour (including one agent call per agent per run) for tests and local runs.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from edip.store.models import AgentCall, Approval, Checkpoint, DecisionRun, RunStatus, Scenario


class DuplicateAgentCall(Exception):
    """A second call record for the same agent in one run (one call per agent, FR27)."""


class Repo(Protocol):
    def put_scenario(self, s: Scenario) -> None: ...
    def get_scenario(self, scenario_id: str) -> Scenario | None: ...
    def list_scenarios(self) -> list[Scenario]: ...
    def create_run(self, r: DecisionRun) -> None: ...
    def set_status(self, run_id: str, status: RunStatus, trace_ids: list[str]) -> None: ...
    def get_run(self, run_id: str) -> DecisionRun | None: ...
    def list_runs(self, limit: int = 50) -> list[DecisionRun]: ...
    def add_checkpoint(self, c: Checkpoint) -> None: ...
    def checkpoints(self, run_id: str) -> list[Checkpoint]: ...
    def add_agent_call(self, a: AgentCall) -> None: ...
    def agent_calls(self, run_id: str) -> list[AgentCall]: ...
    def add_approval(self, a: Approval) -> None: ...
    def approvals(self, run_id: str) -> list[Approval]: ...


def _now() -> datetime:
    return datetime.now(UTC)


class MemoryRepo:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.scenarios: dict[str, Scenario] = {}
        self.runs: dict[str, DecisionRun] = {}
        self._checkpoints: list[Checkpoint] = []
        self._calls: list[AgentCall] = []
        self._approvals: list[Approval] = []

    def put_scenario(self, s: Scenario) -> None:
        with self._lock:
            self.scenarios[s.scenario_id] = s.model_copy(update={"created_at": _now()})

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        return self.scenarios.get(scenario_id)

    def list_scenarios(self) -> list[Scenario]:
        return sorted(self.scenarios.values(), key=lambda s: s.created_at or _now())

    def create_run(self, r: DecisionRun) -> None:
        with self._lock:
            now = _now()
            self.runs[r.run_id] = r.model_copy(update={"created_at": now, "updated_at": now})

    def set_status(self, run_id: str, status: RunStatus, trace_ids: list[str]) -> None:
        with self._lock:
            r = self.runs[run_id]
            ids = list(dict.fromkeys([*r.mlflow_trace_ids, *trace_ids]))
            self.runs[run_id] = r.model_copy(
                update={"status": status, "mlflow_trace_ids": ids, "updated_at": _now()}
            )

    def get_run(self, run_id: str) -> DecisionRun | None:
        return self.runs.get(run_id)

    def list_runs(self, limit: int = 50) -> list[DecisionRun]:
        runs = sorted(self.runs.values(), key=lambda r: r.created_at or _now(), reverse=True)
        return runs[:limit]

    def add_checkpoint(self, c: Checkpoint) -> None:
        with self._lock:
            self._checkpoints.append(c.model_copy(update={"created_at": _now()}))

    def checkpoints(self, run_id: str) -> list[Checkpoint]:
        return [c for c in self._checkpoints if c.run_id == run_id]

    def add_agent_call(self, a: AgentCall) -> None:
        with self._lock:
            if any(c.run_id == a.run_id and c.agent == a.agent for c in self._calls):
                raise DuplicateAgentCall(f"{a.agent} already called in run {a.run_id}")
            self._calls.append(a.model_copy(update={"created_at": _now()}))

    def agent_calls(self, run_id: str) -> list[AgentCall]:
        return [c for c in self._calls if c.run_id == run_id]

    def add_approval(self, a: Approval) -> None:
        with self._lock:
            self._approvals.append(a.model_copy(update={"created_at": _now()}))

    def approvals(self, run_id: str) -> list[Approval]:
        return [a for a in self._approvals if a.run_id == run_id]


class LakebaseRepo:
    """psycopg 3 against Lakebase with a short-lived OAuth credential, refreshed before it
    expires. Identity comes from the Databricks SDK default auth (the app's service
    principal when deployed)."""

    TOKEN_TTL_S = 30 * 60

    def __init__(self, project: str | None = None) -> None:
        from databricks.sdk import WorkspaceClient

        from edip.store import lakebase

        self.ws = WorkspaceClient()
        self.project = project or lakebase.PROJECT
        self._endpoint, self._host = lakebase.primary_endpoint(self.ws, self.project)
        self._user = self.ws.current_user.me().user_name
        self._token: str | None = None
        self._token_at = 0.0
        self._lock = threading.Lock()

    def _connect(self) -> Any:  # noqa: ANN401
        import psycopg
        from psycopg.rows import dict_row

        from edip.store.lakebase import DATABASE

        with self._lock:
            if self._token is None or time.monotonic() - self._token_at > self.TOKEN_TTL_S:
                cred = self.ws.postgres.generate_database_credential(endpoint=self._endpoint)
                self._token, self._token_at = cred.token, time.monotonic()
            token = self._token
        return psycopg.connect(
            host=self._host,
            dbname=DATABASE,
            user=self._user,
            password=token,
            sslmode="require",
            row_factory=dict_row,
            connect_timeout=30,
        )

    def _exec(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        import psycopg

        with self._connect() as conn, conn.cursor() as cur:
            try:
                cur.execute(sql, params)
            except psycopg.errors.UniqueViolation as e:
                raise DuplicateAgentCall(str(e)) from e
            return cur.fetchall() if cur.description else []

    def put_scenario(self, s: Scenario) -> None:
        self._exec(
            "INSERT INTO edip.scenarios (scenario_id, name, description, settings, settings_hash,"
            " created_by_role) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (scenario_id) DO NOTHING",
            (
                s.scenario_id,
                s.name,
                s.description,
                json.dumps(s.settings),
                s.settings_hash,
                s.created_by_role,
            ),
        )

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        rows = self._exec("SELECT * FROM edip.scenarios WHERE scenario_id = %s", (scenario_id,))
        return Scenario.model_validate(rows[0]) if rows else None

    def list_scenarios(self) -> list[Scenario]:
        rows = self._exec("SELECT * FROM edip.scenarios ORDER BY created_at")
        return [Scenario.model_validate(r) for r in rows]

    def create_run(self, r: DecisionRun) -> None:
        self._exec(
            "INSERT INTO edip.decision_runs (run_id, scenario_id, status, dataset_hash,"
            " model_version, tariff_hash, battery_hash, optimizer_settings, prompt_versions,"
            " mlflow_run_id, mlflow_trace_ids) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                r.run_id,
                r.scenario_id,
                r.status,
                r.dataset_hash,
                r.model_version,
                r.tariff_hash,
                r.battery_hash,
                json.dumps(r.optimizer_settings),
                json.dumps(r.prompt_versions),
                r.mlflow_run_id,
                json.dumps(r.mlflow_trace_ids),
            ),
        )

    def set_status(self, run_id: str, status: RunStatus, trace_ids: list[str]) -> None:
        run = self.get_run(run_id)
        ids = list(dict.fromkeys([*(run.mlflow_trace_ids if run else []), *trace_ids]))
        self._exec(
            "UPDATE edip.decision_runs SET status = %s, mlflow_trace_ids = %s,"
            " updated_at = now() WHERE run_id = %s",
            (status, json.dumps(ids), run_id),
        )

    def get_run(self, run_id: str) -> DecisionRun | None:
        rows = self._exec("SELECT * FROM edip.decision_runs WHERE run_id = %s", (run_id,))
        return DecisionRun.model_validate(rows[0]) if rows else None

    def list_runs(self, limit: int = 50) -> list[DecisionRun]:
        rows = self._exec(
            "SELECT * FROM edip.decision_runs ORDER BY created_at DESC LIMIT %s", (limit,)
        )
        return [DecisionRun.model_validate(r) for r in rows]

    def add_checkpoint(self, c: Checkpoint) -> None:
        self._exec(
            "INSERT INTO edip.checkpoints (checkpoint_id, run_id, step, payload)"
            " VALUES (%s,%s,%s,%s)",
            (c.checkpoint_id, c.run_id, c.step, json.dumps(c.payload, default=str)),
        )

    def checkpoints(self, run_id: str) -> list[Checkpoint]:
        rows = self._exec(
            "SELECT * FROM edip.checkpoints WHERE run_id = %s ORDER BY created_at", (run_id,)
        )
        return [Checkpoint.model_validate(r) for r in rows]

    def add_agent_call(self, a: AgentCall) -> None:
        self._exec(
            "INSERT INTO edip.agent_calls (call_id, run_id, agent, endpoint, prompt_version,"
            " status, latency_ms, prompt_tokens, completion_tokens, mlflow_trace_id, error_type)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                a.call_id,
                a.run_id,
                a.agent,
                a.endpoint,
                a.prompt_version,
                a.status,
                a.latency_ms,
                a.prompt_tokens,
                a.completion_tokens,
                a.mlflow_trace_id,
                a.error_type,
            ),
        )

    def agent_calls(self, run_id: str) -> list[AgentCall]:
        rows = self._exec(
            "SELECT * FROM edip.agent_calls WHERE run_id = %s ORDER BY created_at", (run_id,)
        )
        return [AgentCall.model_validate(r) for r in rows]

    def add_approval(self, a: Approval) -> None:
        self._exec(
            "INSERT INTO edip.approvals (approval_id, run_id, decision, actor_role, actor_hash,"
            " comment) VALUES (%s,%s,%s,%s,%s,%s)",
            (a.approval_id, a.run_id, a.decision, a.actor_role, a.actor_hash, a.comment),
        )

    def approvals(self, run_id: str) -> list[Approval]:
        rows = self._exec(
            "SELECT * FROM edip.approvals WHERE run_id = %s ORDER BY created_at", (run_id,)
        )
        return [Approval.model_validate(r) for r in rows]
