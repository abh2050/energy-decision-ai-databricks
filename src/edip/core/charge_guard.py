"""Settlement charge guard (revised strategy, post-hoc; owner decision 2026-10-14).

Applied at settlement to every strategy. Before each hour it limits charging so grid draw
stays under the running peak of every demand determinant in effect for that hour:
each tariff demand charge's window (B-19: maximum demand, peak period demand, and summer
part-peak demand; PGE: Peak Demand window) and, for PGE, the all-hours monthly Demand
behind Facility Capacity.

    allowed charge = max(0, min over the hour's 15 minute intervals and active
                     determinants of (running peak x (1 - margin) - actual 15 min load))

A determinant's running peak starts each local month at its billed demand for the
previous month and rises with the settled billed interval demand. The guard reduces
charging only; it never adds discharge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from edip.core.billing_demand import local_month
from edip.core.tariff import Tariff


class Determinant(BaseModel):
    name: str
    interval_minutes: int
    charge_name: str | None  # None = all hours (Facility Capacity Demand)


def determinants(tariff: Tariff) -> list[Determinant]:
    out = [
        Determinant(name=c.name, interval_minutes=c.tariff_interval_minutes, charge_name=c.name)
        for c in tariff.demand_charges
    ]
    if tariff.facility_capacity is not None:
        minutes = tariff.demand_charges[0].tariff_interval_minutes
        out.append(
            Determinant(name="Facility Capacity Demand", interval_minutes=minutes, charge_name=None)
        )
    return out


class ChargeGuard:
    """Tracks running billed demand per determinant and month; caps charging per hour."""

    def __init__(
        self,
        tariff: Tariff,
        start_peaks_kw: dict[str, float],
        margin_fraction: float = 0.0,
    ) -> None:
        """`start_peaks_kw`: billed demand per determinant in the month before the first
        settled hour (from actual load without a battery)."""
        self.tariff = tariff
        self.dets = determinants(tariff)
        self.margin = margin_fraction
        self.charges = {c.name: c for c in tariff.demand_charges}
        self.previous = dict(start_peaks_kw)
        self.running: dict[str, float] = {}
        self.month: pd.Period | None = None
        self.clipped_kwh = 0.0
        self._lookup: dict[pd.Timestamp, tuple[pd.Period, list[Determinant]]] = {}

    def precompute(self, hours_utc: pd.DatetimeIndex) -> None:
        """Cache each hour's local month and active determinants (speed only; the same
        answers as computing them hour by hour)."""
        months = local_month(hours_utc, self.tariff.clock)
        masks = {}
        for det in self.dets:
            if det.charge_name is None:
                masks[det.name] = np.ones(len(hours_utc), dtype=bool)
            else:
                charge = self.charges[det.charge_name]
                masks[det.name] = self.tariff.in_demand_window(charge, hours_utc).to_numpy()
        for i, h in enumerate(hours_utc):
            self._lookup[h] = (months[i], [d for d in self.dets if masks[d.name][i]])

    def _active(self, hour_start_utc: pd.Timestamp) -> list[Determinant]:
        if hour_start_utc in self._lookup:
            return self._lookup[hour_start_utc][1]
        idx = pd.DatetimeIndex([hour_start_utc])
        active = []
        for det in self.dets:
            all_hours = det.charge_name is None
            if (
                all_hours
                or self.tariff.in_demand_window(self.charges[det.charge_name], idx).iloc[0]
            ):
                active.append(det)
        return active

    def _roll_month(self, hour_start_utc: pd.Timestamp) -> None:
        if hour_start_utc in self._lookup:
            month = self._lookup[hour_start_utc][0]
        else:
            month = local_month(pd.DatetimeIndex([hour_start_utc]), self.tariff.clock)[0]
        if month != self.month:
            if self.month is not None:
                # Each determinant's billed demand last month seeds this month.
                self.previous = {d.name: self.running.get(d.name, 0.0) for d in self.dets}
            self.running = {d.name: self.previous.get(d.name, 0.0) for d in self.dets}
            self.month = month

    def cap_kw(self, hour_start_utc: pd.Timestamp) -> float:
        """Lowest running peak (after margin) among determinants in effect; inf if none."""
        self._roll_month(hour_start_utc)
        caps = [self.running[d.name] * (1 - self.margin) for d in self._active(hour_start_utc)]
        return min(caps) if caps else float("inf")

    def allowed_charge_kw(self, hour_start_utc: pd.Timestamp, load15_kw: np.ndarray) -> float:
        cap = self.cap_kw(hour_start_utc)
        if not np.isfinite(cap):
            return float("inf")
        return max(0.0, float(np.min(cap - np.asarray(load15_kw, dtype=float))))

    def limit(
        self, hour_start_utc: pd.Timestamp, planned_charge_kw: float, load15_kw: np.ndarray
    ) -> float:
        allowed = self.allowed_charge_kw(hour_start_utc, load15_kw)
        charge = min(planned_charge_kw, allowed)
        self.clipped_kwh += max(planned_charge_kw - charge, 0.0)
        return charge

    def update(self, hour_start_utc: pd.Timestamp, net15_kw: np.ndarray) -> None:
        """Raise running peaks with the hour's settled billed interval demand."""
        self._roll_month(hour_start_utc)
        net = np.asarray(net15_kw, dtype=float)
        for det in self._active(hour_start_utc):
            per = det.interval_minutes // 15
            demand = net.reshape(-1, per).mean(axis=1).max()
            self.running[det.name] = max(self.running[det.name], float(demand))


def start_peaks_from_load(
    tariff: Tariff, load15_kw: pd.Series, month: pd.Period
) -> dict[str, float]:
    """Billed demand per determinant in `month` (local), from actual 15 minute load with
    no battery: seeds the guard for the first settled month."""
    from edip.core.billing_demand import interval_demand

    out = {}
    for det in determinants(tariff):
        demand = interval_demand(load15_kw, det.interval_minutes)
        demand = demand[local_month(demand.index, tariff.clock) == month]
        if det.charge_name is not None:
            charge = next(c for c in tariff.demand_charges if c.name == det.charge_name)
            demand = demand[tariff.in_demand_window(charge, demand.index).to_numpy()]
        out[det.name] = float(demand.max()) if len(demand) else 0.0
    return out
