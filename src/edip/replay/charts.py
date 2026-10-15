"""Flip boundary chart (FR23) as PNG plus the JSON the public pages read."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

STRATEGIES = ["seasonal_forecast", "ml_forecast", "robust_quantile", "hindsight"]


def flip_chart(
    boundaries: pd.DataFrame,
    path: Path,
    *,
    efficiency: float,
    degradation: float,
    demand_multiplier: float,
    spreads: list[float],
) -> None:
    """Two panels (beats fixed schedule, beats no battery): rows are strategies, columns
    battery size and duration at one efficiency, degradation cost, and demand rate."""
    base = boundaries[
        (boundaries.round_trip_efficiency == efficiency)
        & (boundaries.degradation_usd_per_kwh == degradation)
        & (boundaries.demand_charge_multiplier == demand_multiplier)
    ]
    configs = sorted({(r.power_fraction, r.duration_hours) for r in base.itertuples()})
    labels = [f"{int(p * 100)}% / {int(d)}h" for p, d in configs]
    never = max(spreads) * 1.25
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), sharey=True)
    for ax, col, title in zip(
        axes,
        ["smallest_spread_beating_fixed", "smallest_spread_beating_no_battery"],
        ["Beats fixed schedule", "Beats no battery"],
        strict=True,
    ):
        grid = np.full((len(STRATEGIES), len(configs)), np.nan)
        for i, s in enumerate(STRATEGIES):
            for j, (p, d) in enumerate(configs):
                row = base[
                    (base.strategy == s) & (base.power_fraction == p) & (base.duration_hours == d)
                ]
                if len(row):
                    v = row.iloc[0][col]
                    grid[i, j] = never if pd.isna(v) else v
        im = ax.imshow(grid, cmap="viridis_r", vmin=min(spreads), vmax=never, aspect="auto")
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                v = grid[i, j]
                text = "" if np.isnan(v) else ("never" if v == never else f"x{v:g}")
                ax.text(j, i, text, ha="center", va="center", color="white", fontsize=9)
        ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
        ax.set_yticks(range(len(STRATEGIES)), STRATEGIES)
        ax.set_title(title)
        ax.set_xlabel("battery power (% of training peak) / duration")
    fig.colorbar(im, ax=axes, label="smallest peak-gap multiplier")
    fig.suptitle(
        f"Flip boundary on the B-19 spread family (efficiency {efficiency:g}, "
        f"degradation {degradation:g} USD/kWh, demand rate x{demand_multiplier:g}; "
        "revised strategy, post-hoc)",
        fontsize=10,
    )
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
