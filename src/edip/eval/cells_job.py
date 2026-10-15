"""Decision evidence for every battery cell the planning agent may select (Gate 6).

For each (power fraction, duration) on the allowlist, at base costs: the full 2014 replay
of all six strategies on both real tariffs, the three stress tests, the excess-month trace,
both decision verdicts, and the evidence rows agents cite. The live app reads these
persisted results; it never runs a replay per request.

Usage (local, owner decision 2026-10-14; Delta written by the gate6_load_cells job):
  uv run python -m edip.eval.cells_job --tables DIR --out DIR
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd
import yaml

from edip.agents.fallback import build_packet
from edip.core.labels import REVISED
from edip.core.metrics import coverage
from edip.replay.stress import run_all, with_battery
from edip.workflow.verdicts import base_inputs, verdict_record

LABEL = REVISED
EVIDENCE_TABLE = "edip.eval.cell_evidence"


def cell_key(power_fraction: float, duration_hours: int) -> str:
    return f"{power_fraction:g}/{duration_hours}"


def run_cell(
    cdir: Path,
    obs: pd.DataFrame,
    hourly: pd.DataFrame,
    load15: pd.Series,
    coverage_pct: float,
    power_fraction: float,
    duration_hours: int,
) -> dict[str, pd.DataFrame]:
    key = cell_key(power_fraction, duration_hours)
    tariffs = yaml.safe_load((cdir / "stress_tests.yaml").read_text())["tariffs"]
    with tempfile.TemporaryDirectory() as tmp:
        cell_dir = with_battery(
            cdir,
            Path(tmp) / "cell",
            power_fraction_of_observed_peak=power_fraction,
            duration_hours=duration_hours,
        )
        run = run_all(cell_dir, obs, hourly, load15, Path(tmp) / "work")
    inputs = base_inputs(run.base.annual, run.base.checks, run.results, coverage_pct, tariffs)
    verdict = verdict_record(inputs) | {"case": "cell"}
    packet = build_packet(EVIDENCE_TABLE, inputs)
    evidence = pd.DataFrame(
        [
            {"cell": key, "row_key": k.split("|")[1], "column": k.split("|")[2], "value": v}
            for k, v in packet.values.items()
        ]
    )
    annual = run.base.annual.drop(columns=["months"], errors="ignore").copy()
    sched = run.base.schedules.merge(
        run.base.settlements, on=["tariff_id", "strategy", "hour_start"], how="inner"
    )
    out = {
        "cell_annual": annual,
        "cell_stress_results": run.results,
        "cell_excess_months": run.excess,
        "cell_peak_moments": run.moments,
        "cell_verdicts": pd.DataFrame([verdict]),
        "cell_evidence": evidence,
        "cell_schedules": sched,
    }
    for df in out.values():
        for i, (col, val) in enumerate(
            (
                ("cell", key),
                ("power_fraction", float(power_fraction)),
                ("duration_hours", int(duration_hours)),
            )
        ):
            if col in df:
                df.drop(columns=col, inplace=True)
            df.insert(i, col, val)
        df["label"] = LABEL
        for col in df.columns:
            if df[col].dtype == object and df[col].map(lambda v: isinstance(v, list)).any():
                df[col] = df[col].apply(json.dumps)
            if str(df[col].dtype).startswith("datetime"):
                df[col] = df[col].astype(str)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    args = parser.parse_args()
    cdir = args.config_dir
    pinned = yaml.safe_load((cdir / "model_versions.yaml").read_text())["load_forecaster"]
    obs = pd.read_parquet(args.tables / "load_observations.parquet")
    p = pd.read_parquet(args.tables / "forecast_predictions.parquet")
    p = p[(p.split == "test") & (p.model_version == pinned["version"])]
    hourly = (
        p.set_index("target_hour")[["actual", "seasonal", "point", "p50", "p90"]]
        .sort_index()
        .astype(float)
    )
    load15 = (
        pd.read_parquet(args.tables / "load_intervals_15min.parquet")
        .set_index("interval_end")["kw"]
        .sort_index()
        .astype(float)
    )
    cov = coverage(p.actual.astype(float), p.p10.astype(float), p.p90.astype(float))
    allow = yaml.safe_load((cdir / "agent_allowlist.yaml").read_text())["planning_agent"]
    fields = allow["allowed_fields"]
    parts: dict[str, list[pd.DataFrame]] = {}
    for pf in fields["power_fraction"]:
        for dur in fields["duration_hours"]:
            res = run_cell(cdir, obs, hourly, load15, cov, float(pf), int(dur))
            for k, v in res.items():
                parts.setdefault(k, []).append(v)
            v = res["cell_verdicts"].iloc[0]
            print(cell_key(pf, dur), v.frozen_decision, v.a1_decision, flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for k, frames in parts.items():
        pd.concat(frames, ignore_index=True).to_parquet(args.out / f"{k}.parquet", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
