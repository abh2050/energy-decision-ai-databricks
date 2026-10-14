"""Daily battery dispatch as a mixed integer program (FR14, FR15, FR17).

One horizon is 24 hourly UTC steps. Variables per hour t: charge c_t (kW), discharge d_t
(kW), state of charge s_t (kWh, end of hour), grid import g_t (kW), binary b_t (1 =
charge mode); plus one peak variable per demand charge and local billing month in the day.

    g_t = L_t - d_t + c_t,  g_t >= 0                  (no export)
    0 <= c_t <= P b_t,  0 <= d_t <= P (1 - b_t)       (power, no simultaneous)
    s_t = s_{t-1} + eta_c c_t - d_t / eta_d            (efficiency losses)
    soc_min <= s_t <= soc_max,  s_23 >= terminal       (bounds, terminal reserve)
    m_k >= g_t for t in window k,  m_k >= M_k          (running monthly peak)

Objective: sum_t price_t g_t + sum_k rate_k (m_k - M_k) + deg sum_t d_t, where M_k is the
peak already set this month, so only the increase above it is charged.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from edip.core.battery import BatterySpec

T = 24


class DemandTerm(BaseModel):
    """One demand charge in one local month: hours of the day in its window, $/kW rate,
    and the peak (kW) already set this month for that charge."""

    name: str
    mask: list[bool]
    rate_usd_per_kw: float
    running_peak_kw: float


class Plan(BaseModel):
    charge_kw: list[float]
    discharge_kw: list[float]
    soc_kwh: list[float]
    grid_kw: list[float]
    objective_usd: float
    status: str


def solve_day(
    load_kw: np.ndarray,
    price_usd_per_kwh: np.ndarray,
    demand_terms: list[DemandTerm],
    spec: BatterySpec,
    soc0_kwh: float,
    terminal_min_kwh: float | None,
) -> Plan:
    """Optimal 24 hour plan for a forecast (or actual) hourly load."""
    load = np.maximum(np.asarray(load_kw, dtype=float), 0.0)
    price = np.asarray(price_usd_per_kwh, dtype=float)
    if load.shape != (T,) or price.shape != (T,):
        raise ValueError("load and price need 24 hourly values")
    nk = len(demand_terms)
    # Variable layout: c[0:24] d[24:48] s[48:72] g[72:96] b[96:120] m[120:120+nk]
    ic, id_, is_, ig, ib, im = 0, T, 2 * T, 3 * T, 4 * T, 5 * T
    n = 5 * T + nk

    cost = np.zeros(n)
    cost[ig : ig + T] = price
    cost[id_ : id_ + T] = spec.degradation_usd_per_kwh
    for k, term in enumerate(demand_terms):
        cost[im + k] = term.rate_usd_per_kw

    lo = np.zeros(n)
    hi = np.full(n, np.inf)
    hi[ic : ic + T] = spec.power_kw
    hi[id_ : id_ + T] = spec.power_kw
    lo[is_ : is_ + T] = spec.soc_min_kwh
    hi[is_ : is_ + T] = spec.soc_max_kwh
    hi[ib : ib + T] = 1
    if terminal_min_kwh is not None:
        reachable = min(spec.soc_max_kwh, soc0_kwh + T * spec.power_kw * spec.eta_charge)
        lo[is_ + T - 1] = max(spec.soc_min_kwh, min(terminal_min_kwh, reachable))
    for k, term in enumerate(demand_terms):
        lo[im + k] = term.running_peak_kw

    rows = 3 * T + T + T + int(sum(sum(t.mask) for t in demand_terms))
    A = lil_matrix((rows, n))
    lb, ub = [], []
    r = 0
    for t in range(T):
        # grid balance: g_t + d_t - c_t = L_t
        A[r, ig + t], A[r, id_ + t], A[r, ic + t] = 1, 1, -1
        lb.append(load[t])
        ub.append(load[t])
        r += 1
        # charge only in charge mode: c_t - P b_t <= 0
        A[r, ic + t], A[r, ib + t] = 1, -spec.power_kw
        lb.append(-np.inf)
        ub.append(0)
        r += 1
        # discharge only otherwise: d_t + P b_t <= P
        A[r, id_ + t], A[r, ib + t] = 1, spec.power_kw
        lb.append(-np.inf)
        ub.append(spec.power_kw)
        r += 1
        # state of charge: s_t - s_{t-1} - eta_c c_t + d_t / eta_d = 0 (s_{-1} = soc0)
        A[r, is_ + t] = 1
        if t:
            A[r, is_ + t - 1] = -1
        A[r, ic + t] = -spec.eta_charge
        A[r, id_ + t] = 1 / spec.eta_discharge
        rhs = soc0_kwh if t == 0 else 0.0
        lb.append(rhs)
        ub.append(rhs)
        r += 1
        # no export is the lower bound g_t >= 0; discharge cannot exceed load plus charge
        A[r, id_ + t], A[r, ic + t] = 1, -1
        lb.append(-np.inf)
        ub.append(load[t])
        r += 1
    for k, term in enumerate(demand_terms):
        for t in np.flatnonzero(term.mask):
            # m_k - g_t >= 0
            A[r, im + k], A[r, ig + t] = 1, -1
            lb.append(0)
            ub.append(np.inf)
            r += 1

    integrality = np.zeros(n)
    integrality[ib : ib + T] = 1
    res = milp(
        cost,
        constraints=LinearConstraint(A.tocsr()[:r], lb, ub),
        integrality=integrality,
        bounds=Bounds(lo, hi),
        options={"disp": False, "mip_rel_gap": 1e-7},
    )
    if res.x is None:
        raise RuntimeError(f"no feasible plan: {res.message}")
    x = res.x
    offset = sum(t.rate_usd_per_kw * t.running_peak_kw for t in demand_terms)
    c, d = np.clip(x[ic : ic + T], 0, None), np.clip(x[id_ : id_ + T], 0, None)
    # Remove solver dust so charge and discharge are never both positive.
    c[c < 1e-7], d[d < 1e-7] = 0.0, 0.0
    return Plan(
        charge_kw=c.tolist(),
        discharge_kw=d.tolist(),
        soc_kwh=x[is_ : is_ + T].tolist(),
        grid_kw=x[ig : ig + T].tolist(),
        objective_usd=float(res.fun - offset),
        status=str(res.message),
    )
