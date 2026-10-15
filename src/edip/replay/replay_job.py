"""Gate 3 Databricks job: rolling replay of six strategies on every tariff (FR14 to FR21).

Reads load_observations, load_intervals_15min, and forecast_predictions (pinned model
version). Writes dispatch_schedules, settlement_outcomes, replay_outcomes, and
gate3_results.json in the edip.ml.artifacts volume, and logs an MLflow run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel

from edip.core.battery import BatterySpec
from edip.core.billing_demand import interval_demand, monthly_demand_all_hours
from edip.core.labels import PRE_REGISTERED, REVISED
from edip.core.strategies import STRATEGIES, fixed_rule
from edip.core.tariff import Tariff, load_tariffs
from edip.replay.evaluate import check_targets, economics
from edip.replay.replay import RevisedSettings, StrategyResult, run

TARIFF_FILES = ("anchored_tou.yaml", "low_spread_tou.yaml", "synthetic_high_spread.yaml")


def file_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for p in sorted(paths):
        digest.update(p.read_bytes())
    return digest.hexdigest()[:16]


def window_key(tariff: Tariff, fixed_cfg: dict[str, Any]) -> str:
    return tariff.id if tariff.id in fixed_cfg["demand_window"] else "synthetic_high_spread"


def replay_table(annual: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    """Annual and monthly rows in one table with Arrow-safe column types."""
    table = pd.concat(
        [annual.assign(level="annual", month=""), monthly.assign(level="month")],
        ignore_index=True,
    )
    for col in table.columns:
        if table[col].dtype == object:
            numeric = pd.to_numeric(table[col], errors="coerce")
            if numeric.notna().sum() == table[col].notna().sum():
                table[col] = numeric.astype(float)
            else:
                table[col] = table[col].astype("string")
    return table


class Outputs(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    schedules: pd.DataFrame
    settlements: pd.DataFrame
    annual: pd.DataFrame
    monthly: pd.DataFrame
    checks: list[dict[str, Any]]
    rules: dict[str, Any]
    spec: BatterySpec
    observed_peak_kw: float
    operating_cost_usd: float


def compute(
    cdir: Path,
    obs: pd.DataFrame,
    hourly: pd.DataFrame,
    load15: pd.Series,
    tariff_ids: list[str] | None = None,
    revised: RevisedSettings | None = None,
) -> Outputs:
    """Run every strategy on every tariff over the period in `hourly`. Pure pandas; used
    by the job, the validation tuning, and local checks. Facility Capacity is seeded
    with the 11 months of no-battery Demand before the first replayed month."""
    battery_cfg = yaml.safe_load((cdir / "battery.yaml").read_text())
    targets = yaml.safe_load((cdir / "acceptance_targets.yaml").read_text())
    fc_cfg = yaml.safe_load((cdir / "forecasting.yaml").read_text())
    train = obs[obs.split == "train"].set_index("hour_start")["kw_mean"].sort_index()
    observed_peak = float(train.max())
    spec = BatterySpec.from_config(battery_cfg, observed_peak)
    operating = float(battery_cfg["operating_cost"]["annual_usd"])
    first = hourly.index[0].normalize().replace(day=1)
    seed_start = first - pd.DateOffset(months=11)
    seed15 = load15[(load15.index > seed_start) & (load15.index <= first)]
    tariffs = [t for f in TARIFF_FILES for t in load_tariffs(cdir / "tariffs" / f)]
    if tariff_ids is not None:
        tariffs = [t for t in tariffs if t.id in tariff_ids]
    fixed_cfg = battery_cfg["fixed_schedule"]
    prot = fc_cfg["robust_protected_periods"]
    summary: list[dict[str, Any]] = []
    monthly: list[dict[str, Any]] = []
    schedules, settlements = [], []
    econ_all: list[dict[str, Any]] = []
    checks_all: list[dict[str, Any]] = []
    rules: dict[str, Any] = {}
    for tariff in tariffs:
        key = window_key(tariff, fixed_cfg)
        rule = fixed_rule(tariff, fixed_cfg["demand_window"][key], train, spec)
        rules[tariff.id] = rule.model_dump()
        prot_key = key if key in prot else "pge_b19_secondary"
        seed = (
            monthly_demand_all_hours(
                interval_demand(seed15, tariff.demand_charges[0].tariff_interval_minutes),
                tariff.clock,
            )
            if tariff.facility_capacity is not None
            else None
        )
        results: dict[str, StrategyResult] = {}
        for strategy in STRATEGIES:
            res, frame = run(
                tariff,
                strategy,
                hourly,
                load15,
                spec,
                protected_periods=prot[prot_key],
                fixed=rule,
                seed_monthly_demand_kw=seed,
                revised=revised,
            )
            results[strategy] = res
            frame = frame.reset_index()
            frame.insert(0, "strategy", strategy)
            frame.insert(0, "tariff_id", tariff.id)
            plan_cols = ["forecast_kw", "planned_charge_kw", "planned_discharge_kw"]
            schedules.append(frame[["tariff_id", "strategy", "hour_start", *plan_cols]])
            settlements.append(frame.drop(columns=plan_cols))
            for m in res.months:
                monthly.append(
                    {
                        "tariff_id": tariff.id,
                        "strategy": strategy,
                        "month": m.month,
                        "bill_usd": m.total_usd,
                        "energy_kwh": m.energy_kwh,
                        "energy_usd": m.energy_usd,
                        "demand_usd": sum(m.demand_usd.values()),
                        "facility_capacity_usd": m.facility_capacity_usd,
                        "facility_capacity_kw": m.facility_capacity_kw,
                        "demand_usd_by_charge": json.dumps(m.demand_usd),
                        "billing_demand_kw_by_charge": json.dumps(m.billing_demand_kw),
                    }
                )
            summary.append(res.model_dump(exclude={"months"}))
        econ = economics(results, operating)
        econ_all += [e.model_dump() for e in econ]
        checks_all += [c.model_dump() for c in check_targets(econ, targets, operating)]
    annual = pd.DataFrame(summary).merge(
        pd.DataFrame(econ_all).drop(columns=["bill_usd", "degradation_usd"]),
        on=["tariff_id", "strategy"],
    )
    return Outputs(
        schedules=pd.concat(schedules, ignore_index=True),
        settlements=pd.concat(settlements, ignore_index=True),
        annual=annual,
        monthly=pd.DataFrame(monthly),
        checks=checks_all,
        rules=rules,
        spec=spec,
        observed_peak_kw=observed_peak,
        operating_cost_usd=operating,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--catalog", default="edip")
    parser.add_argument("--out", default="/Volumes/edip/ml/artifacts/gate3")
    parser.add_argument(
        "--revised",
        action="store_true",
        help="apply config/revised_strategy.yaml; write *_revised tables (never the originals)",
    )
    args = parser.parse_args()
    cdir = Path(args.config_dir)
    targets = yaml.safe_load((cdir / "acceptance_targets.yaml").read_text())
    pinned = yaml.safe_load((cdir / "model_versions.yaml").read_text())["load_forecaster"]
    if targets["status"] != "frozen":
        raise RuntimeError("acceptance targets must be frozen before the replay")
    cfg_hash = file_hash(
        [cdir / "battery.yaml", cdir / "acceptance_targets.yaml", cdir / "settlement.yaml"]
        + [cdir / "tariffs" / f for f in TARIFF_FILES]
    )

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    obs = spark.table(f"{args.catalog}.curated.load_observations").toPandas()
    dataset_sha = obs["dataset_sha256"].iloc[0]
    preds = spark.table(f"{args.catalog}.curated.forecast_predictions").toPandas()
    preds = preds[(preds.model_version == pinned["version"]) & (preds.split == "test")]
    hourly = (
        preds.set_index("target_hour")[["actual", "seasonal", "point", "p50", "p90"]]
        .sort_index()
        .astype(float)
    )
    iv = spark.table(f"{args.catalog}.curated.load_intervals_15min").toPandas()
    load15 = iv.set_index("interval_end")["kw"].sort_index().astype(float)
    revised = None
    suffix, label = "", PRE_REGISTERED
    if args.revised:
        settings = yaml.safe_load((cdir / "revised_strategy.yaml").read_text())
        if settings["status"] != "frozen":
            raise RuntimeError("revised strategy settings must be frozen before the rerun")
        revised = RevisedSettings(**settings["settings"])
        suffix, label = "_revised", REVISED
    o = compute(cdir, obs, hourly, load15, revised=revised)

    def write(pdf: pd.DataFrame, name: str) -> None:
        spark.createDataFrame(pdf).write.mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(f"{args.catalog}.curated.{name}{suffix}")

    meta = {
        "model_version": pinned["version"],
        "config_hash": cfg_hash,
        "dataset_sha256": dataset_sha,
        "result_label": label,
    }
    write(o.schedules.assign(**meta), "dispatch_schedules")
    write(o.settlements.assign(**meta), "settlement_outcomes")
    replay = replay_table(o.annual, o.monthly).assign(**meta)
    write(replay, "replay_outcomes")

    results_json = {
        **meta,
        "observed_peak_kw": o.observed_peak_kw,
        "battery": o.spec.model_dump(),
        "operating_cost_usd": o.operating_cost_usd,
        "fixed_rules": o.rules,
        "annual": o.annual.to_dict("records"),
        "economics_checks": o.checks,
        "monthly": o.monthly.to_dict("records"),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if revised is not None:
        results_json["revised_settings"] = revised.model_dump()
        out = out / "revised"
        out.mkdir(parents=True, exist_ok=True)
    (out / "gate3_results.json").write_text(json.dumps(results_json, indent=2, default=str) + "\n")

    import mlflow

    mlflow.set_experiment("/Shared/edip/gate3_replay")
    with mlflow.start_run(run_name="gate3-replay" + ("-revised" if revised else "")):
        mlflow.set_tags({"gate": "3", **meta, "mlflow_version": mlflow.__version__})
        for row in o.annual.to_dict("records"):
            prefix = f"{row['tariff_id']}.{row['strategy']}"
            mlflow.log_metric(f"{prefix}.bill_usd", row["bill_usd"])
            mlflow.log_metric(f"{prefix}.net_benefit_usd", row["net_benefit_usd"])
            mlflow.log_metric(f"{prefix}.violations", row["violations"])
        mlflow.log_dict(results_json, "gate3_results.json")
    violations = int(o.annual["violations"].sum())
    print(json.dumps({"rows": len(o.annual), "violations": violations}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
