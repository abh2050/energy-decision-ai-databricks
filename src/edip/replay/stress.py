"""Predefined stress tests (config/stress_tests.yaml) evaluated against the frozen limits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from edip.replay.replay import RevisedSettings
from edip.replay.replay_job import compute

FORECAST_COLS = ["seasonal", "point", "p50", "p90"]


def inject_forecast_error(hourly: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    out = hourly.copy()
    for col in FORECAST_COLS:
        out[col] = (out["actual"] + multiplier * (out[col] - out["actual"])).clip(lower=0.0)
    return out


def heat_week(
    hourly: pd.DataFrame, load15: pd.Series, multiplier: float, days: int
) -> tuple[pd.DataFrame, pd.Series, tuple[pd.Timestamp, pd.Timestamp]]:
    """Scale actual load around the annual peak; forecasts are left unchanged."""
    peak = hourly["actual"].idxmax().normalize()
    start = peak - pd.Timedelta(days=days // 2)
    end = start + pd.Timedelta(days=days)
    h = hourly.copy()
    in_week = (h.index >= start) & (h.index < end)
    h.loc[in_week, "actual"] = h.loc[in_week, "actual"] * multiplier
    l15 = load15.copy()
    in15 = (l15.index > start) & (l15.index <= end)
    l15[in15] = l15[in15] * multiplier
    return h, l15, (start, end)


def raise_floor(cdir: Path, soc_min_fraction: float, work: Path) -> Path:
    """A config directory copy with a higher battery floor (hard constraints unchanged)."""
    work.mkdir(parents=True, exist_ok=True)
    for p in cdir.rglob("*"):
        target = work / p.relative_to(cdir)
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.write_bytes(p.read_bytes())
    battery = yaml.safe_load((work / "battery.yaml").read_text())
    battery["base_case"]["soc_min_fraction"] = soc_min_fraction
    (work / "battery.yaml").write_text(yaml.safe_dump(battery, sort_keys=False))
    return work


def evaluate(
    unstressed: pd.DataFrame, stressed: pd.DataFrame, monthly: pd.DataFrame, limits: dict[str, Any]
) -> list[dict[str, Any]]:
    """Per tariff and strategy: retained net benefit, worst month vs no battery, violations."""
    rows = []
    base = unstressed.set_index(["tariff_id", "strategy"])
    nb_month = monthly[monthly.strategy == "no_battery"].set_index(["tariff_id", "month"])[
        "bill_usd"
    ]
    for r in stressed.to_dict("records"):
        key = (r["tariff_id"], r["strategy"])
        before = float(base.loc[key, "net_benefit_usd"])
        after = float(r["net_benefit_usd"])
        mine = monthly[(monthly.tariff_id == r["tariff_id"]) & (monthly.strategy == r["strategy"])]
        worst = max(
            (m.bill_usd / nb_month[(m.tariff_id, m.month)] - 1) * 100 for m in mine.itertuples()
        )
        retained_ok = (
            after >= limits["min_net_benefit_retained_pct"] / 100 * before
            if before > 0
            else after >= before
        )
        rows.append(
            {
                "tariff_id": r["tariff_id"],
                "strategy": r["strategy"],
                "net_benefit_unstressed_usd": before,
                "net_benefit_stressed_usd": after,
                "retained_pct": after / before * 100 if before > 0 else None,
                "worst_month_vs_no_battery_pct": worst,
                "violations": int(r["violations"]),
                "passed": bool(
                    retained_ok
                    and worst <= limits["max_monthly_bill_increase_vs_no_battery_pct"]
                    and r["violations"] <= limits["accepted_constraint_violations"]
                ),
            }
        )
    return rows


def run_all(
    cdir: Path, obs: pd.DataFrame, hourly: pd.DataFrame, load15: pd.Series, work: Path
) -> pd.DataFrame:
    cfg = yaml.safe_load((cdir / "stress_tests.yaml").read_text())
    limits = yaml.safe_load((cdir / "acceptance_targets.yaml").read_text())["stress"]
    settings = RevisedSettings(
        **yaml.safe_load((cdir / "revised_strategy.yaml").read_text())["settings"]
    )
    tariffs = cfg["tariffs"]
    base = compute(cdir, obs, hourly, load15, tariffs, settings)
    rows = []
    t = cfg["tests"]
    variants = {
        "forecast_error_injection": (
            cdir,
            inject_forecast_error(hourly, t["forecast_error_injection"]["error_multiplier"]),
            load15,
        ),
        "reserve_floor_raise": (
            raise_floor(cdir, t["reserve_floor_raise"]["soc_min_fraction"], work / "floor"),
            hourly,
            load15,
        ),
    }
    hw_hourly, hw_l15, window = heat_week(
        hourly,
        load15,
        t["heat_week_replay"]["load_multiplier"],
        t["heat_week_replay"]["window_days"],
    )
    variants["heat_week_replay"] = (cdir, hw_hourly, hw_l15)
    for name, (vdir, vh, vl) in variants.items():
        out = compute(vdir, obs, vh, vl, tariffs, settings)
        # Heat week compares with an unstressed run on the same (scaled) load for no battery.
        for row in evaluate(base.annual, out.annual, out.monthly, limits):
            rows.append({"test": name, **row})
    frame = pd.DataFrame(rows)
    frame.attrs["heat_week_window"] = [w.isoformat() for w in window]
    return frame
