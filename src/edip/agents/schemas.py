"""Agent request and response contracts (FR24, FR25). Every claim cites evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StressTest = Literal["forecast_error_injection", "heat_week_replay", "reserve_floor_raise"]
Decision = Literal["proceed", "revise", "withhold"]


class EvidenceRef(BaseModel):
    """A persisted value: Delta table, row key, and column."""

    table: str
    row_key: str
    column: str


class Claim(BaseModel):
    text: str = Field(max_length=400)
    value: float | None = None  # any number stated must equal the cited value
    evidence_ref: EvidenceRef


Operator = Literal[">", ">=", "<", "<=", "==", "!="]


class Comparison(BaseModel):
    """A typed comparison: left value, operator, and right value (a second evidence row,
    or a constant such as 0). The validator evaluates it against the evidence and
    rejects a false comparison. Plain claims may not compare values."""

    text: str = Field(max_length=300)
    left: EvidenceRef
    operator: Operator
    right: EvidenceRef | None = None
    right_value: float | None = None  # used when `right` is not given


class ScenarioChange(BaseModel):
    """One proposed change to an allowlisted scenario field."""

    field: str
    new_value: str | float | int
    reason: str = Field(max_length=300)
    # Planning v3: the operator's words that ask for this change, quoted exactly.
    quote: str = Field(default="", max_length=300)


class PlanningResponse(BaseModel):
    interpretation: str = Field(max_length=600)
    changes: list[ScenarioChange] = Field(default_factory=list, max_length=4)
    refused: list[str] = Field(default_factory=list)  # requests the agent declined
    claims: list[Claim] = Field(default_factory=list, max_length=6)
    comparisons: list[Comparison] = Field(default_factory=list, max_length=4)


class RiskTestSelection(BaseModel):
    tests: list[StressTest] = Field(max_length=3)
    reason: str = Field(max_length=400)


class RiskResponse(BaseModel):
    selection: RiskTestSelection
    findings: list[Claim] = Field(default_factory=list, max_length=8)
    unresolved_risks: list[str] = Field(default_factory=list, max_length=6)
    comparisons: list[Comparison] = Field(default_factory=list, max_length=4)


class BusinessResponse(BaseModel):
    decision: Decision
    scope_tariffs: list[str] = Field(default_factory=list)
    scope_strategies: list[str] = Field(default_factory=list)
    rationale: str = Field(max_length=800)
    claims: list[Claim] = Field(min_length=1, max_length=8)
    comparisons: list[Comparison] = Field(default_factory=list, max_length=4)


class AgentOutcome(BaseModel):
    """What the workflow records for one agent call (FR26, FR27)."""

    agent: Literal["planning", "risk", "business"]
    prompt_version: str
    status: Literal["valid", "invalid", "timeout", "error", "fallback"]
    used_fallback: bool
    calls_made: int
    latency_s: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    rejection_reasons: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    raw_text: str | None = None  # the model's raw response, kept for evaluation
