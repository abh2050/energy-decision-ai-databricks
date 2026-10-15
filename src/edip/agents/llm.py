"""One bounded model call per agent per workflow (FR24 to FR27, rules 8 and 9).

`call_agent` makes at most one call through a `CallBudget`; a timeout, error, unparsable
or invalid response is never retried and the caller's deterministic fallback is used.
Every call is wrapped in an MLflow span when tracing is available.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from edip.agents.schemas import AgentOutcome
from edip.core.wire_schema import wire_schema


class ModelTimeout(Exception):
    """The request deadline passed; the outcome is uncertain, so it is never retried."""


class RawCompletion(BaseModel):
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ModelClient(Protocol):
    def complete(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> RawCompletion: ...


class CallBudget:
    """At most one model call per agent per workflow (FR24)."""

    def __init__(self) -> None:
        self.used: dict[str, int] = {}

    def take(self, agent: str) -> None:
        if self.used.get(agent, 0) >= 1:
            raise RuntimeError(f"{agent} already made its one model call in this workflow")
        self.used[agent] = self.used.get(agent, 0) + 1


class DatabricksModel:
    """Foundation Model API client with an explicit deadline and no retries."""

    def __init__(self, endpoint: str, timeout_s: float, profile: str | None = None) -> None:
        from databricks.sdk import WorkspaceClient
        from databricks_openai import DatabricksOpenAI

        ws = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        self.client = DatabricksOpenAI(workspace_client=ws, timeout=timeout_s, max_retries=0)
        self.endpoint = endpoint

    def complete(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> RawCompletion:
        import openai

        try:
            resp = self.client.chat.completions.create(
                model=self.endpoint,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "response", "schema": schema, "strict": True},
                },
            )
        except openai.APITimeoutError as exc:
            raise ModelTimeout(str(exc)) from exc
        usage = resp.usage
        return RawCompletion(
            text=resp.choices[0].message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


def _span(name: str, attributes: dict[str, Any]) -> Any:  # noqa: ANN401
    import os
    from contextlib import nullcontext

    if os.environ.get("EDIP_TRACING", "on") == "off":
        return nullcontext()
    try:
        import mlflow

        return mlflow.start_span(name=name, attributes=attributes)
    except Exception:  # tracing must never break the workflow
        from contextlib import nullcontext

        return nullcontext()


def call_agent[M: BaseModel](
    *,
    agent: str,
    prompt_version: str,
    system: str,
    user: str,
    model_cls: type[M],
    client: ModelClient,
    budget: CallBudget,
    validate: Callable[[M], list[str]],
    fallback: Callable[[], M],
    max_tokens: int = 900,
) -> tuple[M, AgentOutcome]:
    """Return the validated response, or the deterministic fallback, plus the record."""
    budget.take(agent)
    start = time.perf_counter()
    status, reasons, raw = "error", [], None
    with _span(f"agent.{agent}", {"agent": agent, "prompt_version": prompt_version}) as span:
        try:
            raw = client.complete(system, user, wire_schema(model_cls), max_tokens)
            parsed = model_cls.model_validate_json(raw.text)
            reasons = validate(parsed)
            status = "valid" if not reasons else "invalid"
        except ModelTimeout:
            status, reasons = "timeout", ["request deadline passed; not retried"]
        except (ValidationError, json.JSONDecodeError) as exc:
            status, reasons = (
                "invalid",
                [f"response does not match the schema: {type(exc).__name__}"],
            )
        except Exception as exc:  # any model failure falls back (FR26)
            status, reasons = "error", [f"{type(exc).__name__}"]
        latency = time.perf_counter() - start
        result: M = parsed if status == "valid" else fallback()
        trace_id = None
        if span is not None and hasattr(span, "set_attributes"):
            span.set_attributes(
                {
                    "status": status,
                    "used_fallback": status != "valid",
                    "latency_s": latency,
                    "prompt_tokens": raw.prompt_tokens if raw else None,
                    "completion_tokens": raw.completion_tokens if raw else None,
                    "rejection_reasons": json.dumps(reasons),
                }
            )
            trace_id = getattr(span, "trace_id", None) or getattr(span, "request_id", None)
    outcome = AgentOutcome(
        agent=agent,  # type: ignore[arg-type]
        prompt_version=prompt_version,
        status=status if status == "valid" else "fallback",  # type: ignore[arg-type]
        used_fallback=status != "valid",
        calls_made=1,
        latency_s=latency,
        prompt_tokens=raw.prompt_tokens if raw else None,
        completion_tokens=raw.completion_tokens if raw else None,
        rejection_reasons=[f"{status}: {r}" for r in reasons],
        trace_id=trace_id,
    )
    return result, outcome
