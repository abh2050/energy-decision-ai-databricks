"""Trace the interval that set each excess billed demand (Gate 5 known limit).

For a month billed above no battery, find the demand interval that set each billed demand
that exceeds the no-battery value, and record what the battery did, the charge guard's
limit for that hour, and the actual load at that moment. The guard state is replayed from
the settled schedule (it depends only on settled grid draw), so the limit is the one the
settlement used. Read only: no strategy or guard behaviour changes.

Cause labels (`cause`):
- "guard limit carried forward from <month>": the guard's limit in that hour came from a
  running peak set before the previous month and carried into this month by the guard's
  month start (see the guard note in docs/business_case.md, note 8).
- "guard month-start limit (previous month)": the limit came from the previous month.
- "guard limit raised earlier this month": set by grid draw earlier in this month.
- "no charging in the interval": billed demand above no battery without charging (should
  not occur; recorded if it does).
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from edip.core.billing_demand import interval_demand, local_month, net_interval_load
from edip.core.charge_guard import ChargeGuard, start_peaks_from_load
from edip.core.tariff import Tariff

FIFTEEN = pd.Timedelta(minutes=15)


def guard_states(
    tariff: Tariff, frame: pd.DataFrame, load15: pd.Series, margin: float
) -> pd.DataFrame:
    """Per settled hour: the guard's cap, binding determinant, and the local month in which
    the binding determinant's running peak was set (its origin)."""
    hours = frame.index
    first = local_month(pd.DatetimeIndex([hours[0]]), tariff.clock)[0]
    guard = ChargeGuard(tariff, start_peaks_from_load(tariff, load15, first - 1), margin)
    guard.precompute(hours)
    origin = {d.name: first - 1 for d in guard.dets}
    l15 = load15.reindex(
        pd.DatetimeIndex(np.concatenate([hours + FIFTEEN * (i + 1) for i in range(4)]))
    ).to_numpy()
    l15 = l15.reshape(4, -1).T
    rows = []
    for i, h in enumerate(hours):
        cap = guard.cap_kw(h)
        active = guard._active(h)
        bind = min(active, key=lambda d: guard.running[d.name]).name if active else None
        rows.append(
            {
                "hour_start": h,
                "guard_cap_kw": cap,
                "guard_binding_determinant": bind,
                "guard_running_peak_kw": guard.running[bind] if bind else np.nan,
                "guard_cap_origin_month": str(origin[bind]) if bind else None,
            }
        )
        c, d = float(frame["charge_kw"].iloc[i]), float(frame["discharge_kw"].iloc[i])
        before = dict(guard.running)
        guard.update(h, np.maximum(l15[i] - d + c, 0.0))
        for name, v in guard.running.items():
            if v > before[name] + 1e-9:
                origin[name] = guard.month
    return pd.DataFrame(rows).set_index("hour_start")


def _cause(charge_kw: float, origin: str | None, month: str) -> str:
    if charge_kw <= 1e-6:
        return "no charging in the interval"
    m = pd.Period(month, "M")
    if origin is None:
        return "no guard limit in effect"
    o = pd.Period(origin, "M")
    if o == m:
        return "guard limit raised earlier this month"
    if o == m - 1:
        return "guard month-start limit (previous month)"
    return f"guard limit carried forward from {origin}"


def billed_max_moments(
    case: str,
    excess: pd.DataFrame,
    settlements: pd.DataFrame,
    schedules: pd.DataFrame,
    monthly: pd.DataFrame,
    tariffs: dict[str, Tariff],
    load15: pd.Series,
    margin: float,
) -> list[dict[str, Any]]:
    """One row per excess month and demand charge whose billed kW exceeds no battery."""
    out: list[dict[str, Any]] = []
    rows = excess[excess["case"] == case] if len(excess) else excess
    if not len(rows):
        return out
    nb = monthly[monthly.strategy == "no_battery"].set_index(["tariff_id", "month"])
    mine = monthly.set_index(["tariff_id", "strategy", "month"])
    for (tid, strategy), g in rows.groupby(["tariff_id", "strategy"]):
        tariff = tariffs[tid]
        frame = settlements[
            (settlements.tariff_id == tid) & (settlements.strategy == strategy)
        ].set_index("hour_start")
        plan = schedules[(schedules.tariff_id == tid) & (schedules.strategy == strategy)]
        plan = plan.set_index("hour_start")["planned_charge_kw"]
        states = guard_states(tariff, frame, load15, margin)
        l15 = load15[
            (load15.index > frame.index[0]) & (load15.index <= frame.index[-1] + 4 * FIFTEEN)
        ]
        net, _ = net_interval_load(l15, frame["discharge_kw"] - frame["charge_kw"])
        for row in g.itertuples():
            kw = pd.Series(
                json.loads(mine.loc[(tid, strategy, row.month), "billing_demand_kw_by_charge"])
            )
            base_kw = pd.Series(json.loads(nb.loc[(tid, row.month), "billing_demand_kw_by_charge"]))
            for charge in tariff.demand_charges:
                if kw.get(charge.name, 0.0) <= base_kw.get(charge.name, 0.0) + 0.5:
                    continue
                demand = interval_demand(net, charge.tariff_interval_minutes)
                load_d = interval_demand(l15, charge.tariff_interval_minutes)
                in_month = local_month(demand.index, tariff.clock) == pd.Period(row.month, "M")
                window = tariff.in_demand_window(charge, demand.index).to_numpy()
                d = demand[in_month & window]
                start = d.idxmax()
                h = start.floor("h")
                st = states.loc[h]
                out.append(
                    {
                        "case": case,
                        "tariff_id": tid,
                        "strategy": strategy,
                        "month": row.month,
                        "charge": charge.name,
                        "interval_start_utc": start,
                        "interval_start_local": start.tz_localize("UTC")
                        .tz_convert(tariff.clock)
                        .tz_localize(None),
                        "billed_kw": float(d.max()),
                        "no_battery_billed_kw": float(base_kw.get(charge.name, 0.0)),
                        "actual_load_kw": float(load_d.loc[start]),
                        "battery_charge_kw": float(frame.loc[h, "charge_kw"]),
                        "battery_discharge_kw": float(frame.loc[h, "discharge_kw"]),
                        "planned_charge_kw": float(plan.loc[h]),
                        "guard_clipped_kw": float(frame.loc[h, "guard_clipped_kw"]),
                        "guard_cap_kw": float(st.guard_cap_kw),
                        "guard_binding_determinant": st.guard_binding_determinant,
                        "guard_running_peak_kw": float(st.guard_running_peak_kw),
                        "guard_cap_origin_month": st.guard_cap_origin_month,
                        "guard_month_start_limit_caused": bool(row.guard_month_start_limit_caused),
                        "cause": _cause(
                            float(frame.loc[h, "charge_kw"]), st.guard_cap_origin_month, row.month
                        ),
                    }
                )
    return out
