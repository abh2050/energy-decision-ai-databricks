"""Gate 5 evaluation report numbers from evals/results/agent_evaluations.parquet.

Usage: uv run python evals/summarize.py --usd-per-million-tokens RATE --rate-source TEXT
       [--prompts business_v1 business_v2 business_v3]

Reports every business prompt's run side by side and checks each against the frozen agent
targets (config/acceptance_targets.yaml#agents).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def pct(series: pd.Series) -> float | None:
    s = series.dropna().astype(bool)
    return float(s.mean() * 100) if len(s) else None


def summarize(df: pd.DataFrame, usd_per_m: float) -> dict:
    out = {}
    for path, g in df.groupby("path"):
        tokens = g.prompt_tokens + g.completion_tokens
        out[path] = {
            "scenarios": len(g),
            "recommendation_accuracy_pct": pct(g.decision_correct),
            "scope_accuracy_pct": pct(g.scope_correct),
            "claims": int(g.claims.sum()),
            "supported_claim_rate_pct": float(g.claims_supported.sum() / g.claims.sum() * 100)
            if g.claims.sum()
            else None,
            "citation_accuracy_pct": float(g.claims_cited.sum() / g.claims.sum() * 100)
            if g.claims.sum()
            else None,
            "risks_found_pct": pct(g.risks_found),
            "fallback_rate_pct": float(g.fallbacks.sum() / g.model_calls.sum() * 100),
            "model_calls": int(g.model_calls.sum()),
            "tokens_per_run": float(tokens.mean()),
            "cost_usd_per_run": float(tokens.mean() / 1e6 * usd_per_m),
            "latency_s_per_run": float(g.latency_s.mean()),
            "accuracy_by_kind_pct": {k: pct(v.decision_correct) for k, v in g.groupby("kind")},
        }
        if path == "agent_assisted":
            out[path] |= {
                "stress_test_selection_accuracy_pct": pct(g.stress_selection_correct),
                "prohibited_action_refusals_by_agent_pct": pct(g.prohibited_refused_by_agent),
                "prohibited_actions_blocked_by_system_pct": pct(g.prohibited_blocked_by_system),
                "planning_change_accuracy_pct": pct(g.planning_changes_correct),
                "scenarios_with_unrequested_changes": int(
                    (g.unrequested_changes.str.len() > 0).sum()
                ),
            }
    return out


def agent_target_checks(paths: dict, targets: dict) -> list[dict]:
    """Frozen agent targets (config/acceptance_targets.yaml#agents) on one run."""
    a, n = paths["agent_assisted"], paths["numbers_only"]
    rows = [
        (
            "supported_claim_rate_pct",
            a["supported_claim_rate_pct"],
            ">=",
            targets["supported_claim_rate_pct_min"],
        ),
        (
            "citation_accuracy_pct",
            a["citation_accuracy_pct"],
            ">=",
            targets["citation_accuracy_pct_min"],
        ),
        (
            "prohibited_action_refusal_pct",
            a["prohibited_action_refusals_by_agent_pct"],
            ">=",
            targets["prohibited_action_refusal_pct_min"],
        ),
        (
            "stress_test_selection_accuracy_pct",
            a["stress_test_selection_accuracy_pct"],
            ">=",
            targets["stress_test_selection_accuracy_pct_min"],
        ),
        (
            "recommendation_accuracy_pct (agent > numbers only)",
            a["recommendation_accuracy_pct"],
            ">",
            n["recommendation_accuracy_pct"],
        ),
        (
            "inference_cost_usd_per_run",
            a["cost_usd_per_run"],
            "<=",
            targets["inference_cost_usd_per_run_max"],
        ),
    ]
    ops = {">=": lambda x, y: x >= y, ">": lambda x, y: x > y, "<=": lambda x, y: x <= y}
    return [
        {"target": k, "value": v, "op": op, "threshold": t, "met": bool(ops[op](v, t))}
        for k, v, op, t in rows
    ]


def business_prompt(df: pd.DataFrame) -> str:
    versions = {v for s in df.prompt_versions for v in s.split(",") if v.startswith("business")}
    return ",".join(sorted(versions))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usd-per-million-tokens", type=float, required=True)
    parser.add_argument("--rate-source", required=True)
    parser.add_argument(
        "--prompts", nargs="+", default=["business_v1", "business_v2", "business_v3"]
    )
    parser.add_argument("--out", default="docs/gates/gate6_evaluation.json")
    args = parser.parse_args()
    targets = yaml.safe_load((ROOT / "config" / "acceptance_targets.yaml").read_text())["agents"]
    runs = {}
    frames = []
    for bp in args.prompts:
        df = pd.read_parquet(ROOT / "evals" / "results" / f"agent_evaluations_{bp}.parquet")
        frames.append(df)
        paths = summarize(df, args.usd_per_million_tokens)
        checks = agent_target_checks(paths, targets)
        runs[bp] = {
            "business_prompt": business_prompt(df),
            "result_set": str(df["result_set"].iloc[0]) if "result_set" in df else None,
            "paths": paths,
            "agent_targets": checks,
            "meets_every_agent_target": all(c["met"] for c in checks),
        }
    summary = {
        "usd_per_million_tokens": args.usd_per_million_tokens,
        "rate_source": args.rate_source,
        "runs": runs,
        "per_scenario": pd.concat(frames)
        .drop(
            columns=[
                c
                for c in ("required_tests", "selected_tests", "unrequested_changes")
                if c in frames[0]
            ]
        )
        .to_dict("records"),
    }
    (ROOT / args.out).write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {k: {"targets_met": v["meets_every_agent_target"]} for k, v in runs.items()}, indent=1
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
