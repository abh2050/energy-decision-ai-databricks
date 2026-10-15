"""Base-case decision inputs from persisted replay and stress results, and both verdicts.

Economics: the frozen target checks (`replay_job.Outputs.checks`, strict reading) and net
benefit from the replay's annual table. Stress: one pass flag per test, true only when every
ML and robust row on the real tariffs passed (the frozen limits apply to each). Coverage:
P10 to P90 coverage of the pinned forecaster on the test year.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from edip.workflow.decision import STRATEGIES, DecisionInputs, StrategyEvidence, decide


def base_inputs(
    annual: pd.DataFrame,
    checks: list[dict[str, Any]],
    stress: pd.DataFrame,
    coverage_pct: float,
    tariffs: list[str],
) -> DecisionInputs:
    net = annual.set_index(["tariff_id", "strategy"])["net_benefit_usd"]
    passes = {(c["tariff_id"], c["strategy"]): bool(c["passes"]) for c in checks}
    strategies = [
        StrategyEvidence(
            tariff_id=t,
            strategy=s,
            passes_target=passes[(t, s)],
            net_vs_no_battery_usd=float(net[(t, s)]),
            net_vs_fixed_usd=float(net[(t, s)] - net[(t, "fixed_schedule")]),
        )
        for t in tariffs
        for s in STRATEGIES
    ]
    scoped = stress[stress.strategy.isin(STRATEGIES) & stress.tariff_id.isin(tariffs)]
    return DecisionInputs(
        violations=int(annual[annual.tariff_id.isin(tariffs)]["violations"].sum()),
        coverage_pct=coverage_pct,
        stress_passed={t: bool(g.passed.all()) for t, g in scoped.groupby("test")},
        strategies=strategies,
    )


def verdict_record(x: DecisionInputs) -> dict[str, Any]:
    r = decide(x)
    return {
        "case": "base",
        "label": "revised strategy, post-hoc",
        "frozen_decision": r.frozen_decision,
        "frozen_reasons": "; ".join(r.frozen_reasons),
        "a1_decision": r.decision,
        "a1_reasons": "; ".join(r.reasons),
        "a1_scope": "; ".join(f"{t}/{s}" for t, s in r.scope),
        "a1_ref": r.a1_ref,
        "display": r.display,
        "inputs_json": x.model_dump_json(),
    }
