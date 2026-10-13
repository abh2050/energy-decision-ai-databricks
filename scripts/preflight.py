"""Gate 0 structured output preflight against a Foundation Model API endpoint.

Makes exactly 20 calls with a sample Pydantic schema and writes the summary to
docs/gates/gate0_preflight.json. Calls are never retried (rule 8): a timeout is
recorded as a failure. Auth comes from the Databricks CLI profile or environment.

Usage: uv run python scripts/preflight.py [--profile edip] [--no-mlflow]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import openai
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI
from pydantic import BaseModel, Field, ValidationError

from edip.core.preflight_stats import (
    EXPECTED_CALLS,
    CallOutcome,
    PreflightCall,
    PreflightSummary,
    summarize,
)

ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
PROMPT_VERSION = "preflight-v1"
TIMEOUT_S = 30.0
MAX_TOKENS = 300
OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "gates" / "gate0_preflight.json"


class SampleScheduleNote(BaseModel):
    """Sample schema shaped like a small agent response with an evidence reference."""

    action: str = Field(pattern="^(charge|discharge|hold)$")
    hour: int = Field(ge=0, le=23)
    reason: str = Field(max_length=200)
    evidence_table: str
    evidence_row_key: str
    evidence_column: str


SYSTEM = (
    "You return only JSON matching the given schema. Cite the evidence fields exactly as "
    "given in the user message."
)
# Fixed sample inputs; values are illustrative test fixtures for the schema check only.
USER_TEMPLATES = [
    "Evidence row: table=dispatch_schedules, row_key=day-{i:02d}-h{h:02d}, column=action. "
    "The planned action in hour {h} is {a}. Describe it."
]
ACTIONS = ["charge", "discharge", "hold"]


def config_hash() -> str:
    payload = json.dumps(
        {
            "endpoint": ENDPOINT,
            "prompt_version": PROMPT_VERSION,
            "timeout_s": TIMEOUT_S,
            "max_tokens": MAX_TOKENS,
            "schema": SampleScheduleNote.model_json_schema(),
            "system": SYSTEM,
            "user": USER_TEMPLATES,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def one_call(client: openai.OpenAI, index: int) -> PreflightCall:
    hour = (index * 5) % 24
    user = USER_TEMPLATES[0].format(i=index, h=hour, a=ACTIONS[index % 3])
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=ENDPOINT,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            max_tokens=MAX_TOKENS,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "SampleScheduleNote",
                    "schema": SampleScheduleNote.model_json_schema(),
                    "strict": True,
                },
            },
        )
    except openai.APITimeoutError:
        # Outcome uncertain: log it and do not retry.
        return PreflightCall(
            index=index,
            outcome=CallOutcome.TIMEOUT,
            latency_s=time.perf_counter() - start,
            error_type="APITimeoutError",
        )
    except openai.OpenAIError as exc:
        return PreflightCall(
            index=index,
            outcome=CallOutcome.ERROR,
            latency_s=time.perf_counter() - start,
            error_type=type(exc).__name__,
        )
    latency = time.perf_counter() - start
    usage = resp.usage
    text = resp.choices[0].message.content or ""
    try:
        json.loads(text)
    except json.JSONDecodeError:
        outcome = CallOutcome.INVALID_JSON
    else:
        try:
            SampleScheduleNote.model_validate_json(text)
            outcome = CallOutcome.VALID
        except ValidationError:
            outcome = CallOutcome.SCHEMA_MISMATCH
    return PreflightCall(
        index=index,
        outcome=outcome,
        latency_s=latency,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
    )


def log_to_mlflow(summary: PreflightSummary) -> None:
    import mlflow

    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment("/Shared/edip/gate0_preflight")
    with mlflow.start_run(run_name="gate0-preflight"):
        mlflow.set_tags(
            {
                "gate": "0",
                "config_hash": summary.config_hash,
                "prompt_version": summary.prompt_version,
                "dataset_hash": "none",
            }
        )
        mlflow.log_param("endpoint", summary.endpoint)
        mlflow.log_metrics(
            {
                "valid_calls": summary.valid_calls,
                "valid_rate": summary.valid_rate,
                "prompt_tokens": summary.prompt_tokens,
                "completion_tokens": summary.completion_tokens,
                **(
                    {"median_latency_s": summary.median_latency_s}
                    if summary.median_latency_s is not None
                    else {}
                ),
            }
        )
        mlflow.log_dict(summary.model_dump(mode="json"), "gate0_preflight.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=None)
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()

    ws = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    client = DatabricksOpenAI(workspace_client=ws, timeout=TIMEOUT_S, max_retries=0)
    calls = [one_call(client, i) for i in range(EXPECTED_CALLS)]
    summary = summarize(
        calls, endpoint=ENDPOINT, prompt_version=PROMPT_VERSION, config_hash=config_hash()
    )
    record = {
        "summary": summary.model_dump(mode="json"),
        "calls": [c.model_dump(mode="json") for c in calls],
    }
    OUTPUT.write_text(json.dumps(record, indent=2) + "\n")
    if not args.no_mlflow:
        log_to_mlflow(summary)
    print(
        f"valid {summary.valid_calls}/{summary.calls}, median latency "
        f"{summary.median_latency_s}, tokens {summary.prompt_tokens}+"
        f"{summary.completion_tokens}, passed={summary.passed}"
    )
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
