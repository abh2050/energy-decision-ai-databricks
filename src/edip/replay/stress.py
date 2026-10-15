"""Predefined stress tests (config/stress_tests.yaml) evaluated against the frozen limits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from edip.core.charge_guard import start_peaks_from_load
from edip.core.tariff import Tariff, load_tariffs
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


NOT_APPLICABLE = "not applicable, base case already loses money"


def evaluate(
    unstressed: pd.DataFrame, stressed: pd.DataFrame, monthly: pd.DataFrame, limits: dict[str, Any]
) -> list[dict[str, Any]]:
    """Per tariff and strategy: retained net benefit, worst month vs no battery, violations.

    When the unstressed net benefit is not positive, retained percent is undefined: it is
    recorded as null with reason "base_negative", and the test is judged on the monthly
    bill limit and the absolute dollar change (stressed must be no worse than unstressed).
    """
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
        base_negative = before <= 0
        change_ok = (
            after >= before
            if base_negative
            else (after >= limits["min_net_benefit_retained_pct"] / 100 * before)
        )
        rows.append(
            {
                "tariff_id": r["tariff_id"],
                "strategy": r["strategy"],
                "net_benefit_unstressed_usd": before,
                "net_benefit_stressed_usd": after,
                "absolute_change_usd": after - before,
                "retained_pct": None if base_negative else after / before * 100,
                "retained_reason": "base_negative" if base_negative else None,
                "retained_display": NOT_APPLICABLE if base_negative else None,
                "judged_on": (
                    "monthly bill limit and absolute dollar change"
                    if base_negative
                    else "retained net benefit and monthly bill limit"
                ),
                "worst_month_vs_no_battery_pct": worst,
                "violations": int(r["violations"]),
                "passed": bool(
                    change_ok
                    and worst <= limits["max_monthly_bill_increase_vs_no_battery_pct"]
                    and r["violations"] <= limits["accepted_constraint_violations"]
                ),
            }
        )
    return rows


def _charges(row: Any) -> tuple[dict[str, float], dict[str, float]]:  # noqa: ANN401
    return json.loads(row.demand_usd_by_charge), json.loads(row.billing_demand_kw_by_charge)


def excess_months(
    case: str,
    monthly: pd.DataFrame,
    tariffs: dict[str, Tariff],
    load15: pd.Series,
    margin: float,
    limit_pct: float,
) -> list[dict[str, Any]]:
    """Every strategy month billed more than `limit_pct` above no battery, with the excess
    split into energy, each demand charge, and Facility Capacity, and whether the charge
    guard's month-start limit caused the demand excess: the guard starts each month at the
    previous month's billed demand, so charging may lift this month's demand up to that
    level even when it is above this month's no-battery demand."""
    out = []
    nb = monthly[monthly.strategy == "no_battery"].set_index(["tariff_id", "month"])
    for tid, tariff in tariffs.items():
        first = pd.Period(monthly[monthly.tariff_id == tid].month.min(), "M")
        seed = start_peaks_from_load(tariff, load15, first - 1)
        for strategy, g in monthly[
            (monthly.tariff_id == tid) & (monthly.strategy != "no_battery")
        ].groupby("strategy"):
            g = g.sort_values("month")
            prev_kw = dict(seed)
            for row in g.itertuples():
                base = nb.loc[(tid, row.month)]
                usd, kw = _charges(row)
                base_usd, base_kw = _charges(base)
                pct = (row.bill_usd / base.bill_usd - 1) * 100
                if pct > limit_pct:
                    split = {"energy_usd": row.energy_usd - base.energy_usd}
                    caused = []
                    for name in usd:
                        split[f"{name} usd"] = usd[name] - base_usd.get(name, 0.0)
                        start_cap = prev_kw.get(name, 0.0) * (1 - margin)
                        if (
                            kw[name] > base_kw.get(name, 0.0) + 0.5
                            and start_cap > base_kw.get(name, 0.0) + 0.5
                            and kw[name] <= start_cap + 0.5
                        ):
                            caused.append(name)
                    split["facility_capacity_usd"] = (
                        row.facility_capacity_usd - base.facility_capacity_usd
                    )
                    out.append(
                        {
                            "case": case,
                            "tariff_id": tid,
                            "strategy": strategy,
                            "month": row.month,
                            "bill_above_no_battery_pct": pct,
                            "excess_usd": row.bill_usd - base.bill_usd,
                            **{k: float(v) for k, v in split.items()},
                            "guard_month_start_limit_caused": bool(caused),
                            "guard_month_start_determinants": caused,
                        }
                    )
                prev_kw = {**prev_kw, **kw}
    return out


def run_all(
    cdir: Path, obs: pd.DataFrame, hourly: pd.DataFrame, load15: pd.Series, work: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stress results and the excess-month breakdown (base case and every test)."""
    cfg = yaml.safe_load((cdir / "stress_tests.yaml").read_text())
    limits = yaml.safe_load((cdir / "acceptance_targets.yaml").read_text())["stress"]
    settings = RevisedSettings(
        **yaml.safe_load((cdir / "revised_strategy.yaml").read_text())["settings"]
    )
    tariffs = cfg["tariffs"]
    tariff_objs = {
        t.id: t
        for f in ("anchored_tou.yaml", "low_spread_tou.yaml")
        for t in load_tariffs(cdir / "tariffs" / f)
        if t.id in tariffs
    }
    monthly_limit = limits["max_monthly_bill_increase_vs_no_battery_pct"]
    base = compute(cdir, obs, hourly, load15, tariffs, settings)
    excess = excess_months(
        "base", base.monthly, tariff_objs, load15, settings.guard_margin_fraction, monthly_limit
    )
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
        # Monthly bills compare with no battery under the same stress (heat week: scaled load).
        for row in evaluate(base.annual, out.annual, out.monthly, limits):
            rows.append({"test": name, **row})
        excess += excess_months(
            name, out.monthly, tariff_objs, vl, settings.guard_margin_fraction, monthly_limit
        )
    frame = pd.DataFrame(rows)
    frame.attrs["heat_week_window"] = [w.isoformat() for w in window]
    return frame, pd.DataFrame(excess)
