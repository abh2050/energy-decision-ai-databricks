"""Flip boundaries from the sensitivity grid (FR23). Pure functions."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

CELL_KEYS = [
    "power_fraction",
    "duration_hours",
    "round_trip_efficiency",
    "degradation_usd_per_kwh",
    "demand_charge_multiplier",
]


class FlipBoundary(BaseModel):
    strategy: str
    power_fraction: float
    duration_hours: float
    round_trip_efficiency: float
    degradation_usd_per_kwh: float
    demand_charge_multiplier: float
    spreads_tested: list[float]
    smallest_spread_beating_fixed: float | None  # FR23 definition
    smallest_spread_beating_no_battery: float | None


def flip_boundaries(grid: pd.DataFrame) -> list[FlipBoundary]:
    """For each strategy and battery cell, the smallest spread multiplier (B-19 family)
    at which the strategy beats the fixed schedule, and at which it beats no battery.
    None means it never does within the spreads tested."""
    family = grid[grid.spread_multiplier.notna()]
    out = []
    for (strategy, *cell), g in family.groupby(["strategy", *CELL_KEYS]):
        if strategy in ("no_battery", "fixed_schedule"):
            continue
        g = g.sort_values("spread_multiplier")
        spreads = g.spread_multiplier.tolist()
        beat_fixed = g[g.beats_fixed].spread_multiplier
        beat_none = g[g.beats_no_battery].spread_multiplier
        out.append(
            FlipBoundary(
                strategy=strategy,
                **dict(zip(CELL_KEYS, cell, strict=True)),
                spreads_tested=spreads,
                smallest_spread_beating_fixed=float(beat_fixed.min()) if len(beat_fixed) else None,
                smallest_spread_beating_no_battery=float(beat_none.min())
                if len(beat_none)
                else None,
            )
        )
    return out
