"""Pure scoring for the Gate 0 structured output preflight."""

from __future__ import annotations

import statistics
from enum import StrEnum

from pydantic import BaseModel, Field

REQUIRED_VALID_CALLS = 19
EXPECTED_CALLS = 20


class CallOutcome(StrEnum):
    VALID = "valid"
    INVALID_JSON = "invalid_json"
    SCHEMA_MISMATCH = "schema_mismatch"
    TIMEOUT = "timeout"
    ERROR = "error"


class PreflightCall(BaseModel):
    index: int = Field(ge=0)
    outcome: CallOutcome
    latency_s: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    error_type: str | None = None


class PreflightSummary(BaseModel):
    endpoint: str
    prompt_version: str
    config_hash: str
    calls: int
    valid_calls: int
    valid_rate: float
    median_latency_s: float | None
    p90_latency_s: float | None
    prompt_tokens: int
    completion_tokens: int
    outcomes: dict[CallOutcome, int]
    passed: bool
    required_valid_calls: int = REQUIRED_VALID_CALLS


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=10, method="inclusive")[8]


def summarize(
    calls: list[PreflightCall], *, endpoint: str, prompt_version: str, config_hash: str
) -> PreflightSummary:
    """Score preflight calls. Latency stats use completed calls only, not timeouts."""
    valid = sum(c.outcome is CallOutcome.VALID for c in calls)
    completed = [c.latency_s for c in calls if c.outcome is not CallOutcome.TIMEOUT]
    outcomes = {o: sum(c.outcome is o for c in calls) for o in CallOutcome}
    return PreflightSummary(
        endpoint=endpoint,
        prompt_version=prompt_version,
        config_hash=config_hash,
        calls=len(calls),
        valid_calls=valid,
        valid_rate=valid / len(calls) if calls else 0.0,
        median_latency_s=statistics.median(completed) if completed else None,
        p90_latency_s=_p90(completed),
        prompt_tokens=sum(c.prompt_tokens or 0 for c in calls),
        completion_tokens=sum(c.completion_tokens or 0 for c in calls),
        outcomes=outcomes,
        passed=len(calls) == EXPECTED_CALLS and valid >= REQUIRED_VALID_CALLS,
    )
