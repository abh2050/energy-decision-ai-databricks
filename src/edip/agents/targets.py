"""Frozen acceptance targets as citable evidence rows (owner decision 2026-10-15).

Every numeric value in config/acceptance_targets.yaml becomes a read-only row in the table
`config.acceptance_targets`: row key = the YAML path of its parent, column = its key. The
coverage band's bounds (target minus and plus tolerance, 75 and 85) are added as
`derived_lower_bound` and `derived_upper_bound`. The file itself is never changed.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

TABLE = "config.acceptance_targets"
DEFAULT = Path(__file__).resolve().parents[3] / "config" / "acceptance_targets.yaml"


def _walk(node: Any, path: list[str], out: dict[str, float]) -> None:  # noqa: ANN401
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, bool):
                continue
            if isinstance(v, int | float):
                row = "/".join(path) or "root"
                out[f"{TABLE}|{row}|{k}"] = float(v)
            else:
                _walk(v, [*path, str(k)], out)


def target_values(targets: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    _walk(targets, [], out)
    cov = targets.get("forecasting", {}).get("p10_p90_coverage_pct", {})
    if "target" in cov and "tolerance" in cov:
        row = f"{TABLE}|forecasting/p10_p90_coverage_pct"
        out[f"{row}|derived_lower_bound"] = float(cov["target"] - cov["tolerance"])
        out[f"{row}|derived_upper_bound"] = float(cov["target"] + cov["tolerance"])
    return out


@cache
def default_target_values() -> dict[str, float]:
    return target_values(yaml.safe_load(DEFAULT.read_text()))
