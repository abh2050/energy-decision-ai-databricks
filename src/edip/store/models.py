"""Pydantic row models for the Lakebase tables in lakebase_schema.sql."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["operator", "viewer", "system"]
RunStatus = Literal[
    "requested",
    "planning_proposed",
    "operator_confirmed",
    "forecasted",
    "optimized",
    "settled",
    "risk_reviewed",
    "recommended",
    "decided",
    "failed",
]
AgentName = Literal["planning", "risk", "business"]
AgentCallStatus = Literal["valid", "invalid", "timeout", "error", "fallback"]


class Scenario(BaseModel):
    scenario_id: str
    name: str
    description: str | None = None
    settings: dict[str, Any]
    settings_hash: str
    created_by_role: Role
    created_at: datetime | None = None


class DecisionRun(BaseModel):
    run_id: str
    scenario_id: str
    status: RunStatus
    dataset_hash: str
    model_version: str
    tariff_hash: str
    battery_hash: str
    optimizer_settings: dict[str, Any]
    prompt_versions: dict[AgentName, str]
    mlflow_run_id: str | None = None
    mlflow_trace_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Checkpoint(BaseModel):
    checkpoint_id: str
    run_id: str
    step: str
    payload: dict[str, Any]
    created_at: datetime | None = None


class Approval(BaseModel):
    approval_id: str
    run_id: str
    decision: Literal["approve", "revise", "reject"]
    actor_role: Literal["operator"]
    # Hash of the operator identity; raw emails are never stored (rule 7).
    actor_hash: str
    comment: str | None = None
    created_at: datetime | None = None


class AgentCall(BaseModel):
    call_id: str
    run_id: str
    agent: AgentName
    endpoint: str
    prompt_version: str
    status: AgentCallStatus
    latency_ms: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    mlflow_trace_id: str | None = None
    error_type: str | None = None
    created_at: datetime | None = None


TABLE_MODELS: dict[str, type[BaseModel]] = {
    "scenarios": Scenario,
    "decision_runs": DecisionRun,
    "checkpoints": Checkpoint,
    "approvals": Approval,
    "agent_calls": AgentCall,
}
