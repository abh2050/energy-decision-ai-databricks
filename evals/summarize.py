"""Gate 5 evaluation report numbers from evals/results/agent_evaluations.parquet.

Usage: uv run python evals/summarize.py --usd-per-million-tokens RATE --rate-source TEXT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usd-per-million-tokens", type=float, required=True)
    parser.add_argument("--rate-source", required=True)
    args = parser.parse_args()
    df = pd.read_parquet(ROOT / "evals" / "results" / "agent_evaluations.parquet")
    summary = {
        "usd_per_million_tokens": args.usd_per_million_tokens,
        "rate_source": args.rate_source,
        "paths": summarize(df, args.usd_per_million_tokens),
        "per_scenario": df.drop(
            columns=[
                c for c in ("required_tests", "selected_tests", "unrequested_changes") if c in df
            ]
        ).to_dict("records"),
    }
    (ROOT / "docs" / "gates" / "gate5_evaluation.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n"
    )
    print(json.dumps(summary["paths"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
