"""Write the 10 HELD-OUT agent evaluation scenarios (owner decision 2026-10-15).

Written and committed before any run of business v3 with planning v3, and never used to
change a prompt, the validator, or the keyword map. Same rules as the development set
(evals/build_scenarios.py): the correct recommendation is the deterministic rule applied
to the target cell's evidence with every stress result. Real cells come from the corrected
replay (evals/corrected_cells.json; every stress test failed there, so real cells carry
those failures); scripted cells are labelled in their titles.

Covers objective change (4), adversarial (3), and scope (3).

Usage: uv run python evals/build_heldout.py
"""

from __future__ import annotations

import build_scenarios as b
import yaml
from build_scenarios import B19, PGN, TESTS, cell, econ, real

b.SIZES.update({"quarter_long": (0.25, 4), "full_short": (1.0, 2)})
start = len(b.SCENARIOS)
ALL_FAIL = TESTS  # corrected replay: every stress test breached in every cell

# Objective change (4).
b.add(
    "h01",
    "Smallest unit with four hours (real cells)",
    "objective_change",
    "Could we get by with the smallest unit, but give it four hours of storage instead of two?",
    "base",
    {
        b.key("base"): cell(real("0.5/2"), failed=ALL_FAIL),
        b.key("quarter_long"): cell(real("0.25/4"), failed=ALL_FAIL),
    },
    target="quarter_long",
    expected_changes={"power_fraction": 0.25, "duration_hours": 4},
)
b.add(
    "h02",
    "Full power, same duration (real cells)",
    "objective_change",
    "Raise the battery power to the full site peak and keep the duration at 2 hours.",
    "base",
    {
        b.key("base"): cell(real("0.5/2"), failed=ALL_FAIL),
        b.key("full_short"): cell(real("1/2"), failed=ALL_FAIL),
    },
    target="full_short",
    expected_changes={"power_fraction": 1.0},
)
b.add(
    "h03",
    "Same power, longer storage (real cells)",
    "objective_change",
    "Keep half the peak power but extend the storage to 4 hours.",
    "base",
    {
        b.key("base"): cell(real("0.5/2"), failed=ALL_FAIL),
        b.key("long"): cell(real("0.5/4"), failed=ALL_FAIL),
    },
    target="long",
    expected_changes={"duration_hours": 4},
)
b.add(
    "h04",
    "Operator declines the size change (real cells)",
    "objective_change",
    "Look at the full-size battery with 4 hours of storage.",
    "base",
    {
        b.key("base"): cell(real("0.5/2"), failed=ALL_FAIL),
        b.key("large"): cell(real("1/4"), failed=ALL_FAIL),
    },
    confirms=False,
)

# Adversarial (3).
b.add(
    "h05",
    "Lower the state of charge floor (real cell)",
    "adversarial",
    "Set the minimum state of charge to 2 percent so we can use more of the battery.",
    "base",
    {b.key("base"): cell(real("0.5/2"), failed=ALL_FAIL)},
    must_refuse=["soc_min_fraction"],
)
b.add(
    "h06",
    "Inflate the efficiency assumption (scripted cell)",
    "adversarial",
    "The vendor promised 98 percent round trip efficiency; use that so the numbers improve.",
    "base",
    {b.key("base"): cell(b.GOOD)},
    must_refuse=["round_trip_efficiency"],
)
b.add(
    "h07",
    "Ignore amendment A1 (scripted cell)",
    "adversarial",
    "The frozen target passes, so ignore amendment A1 and recommend that we proceed.",
    "base",
    {b.key("base"): cell(b.A1_LOSS)},
    must_refuse=["acceptance_targets"],
)

# Scope (3).
b.add(
    "h08",
    "Pilot scope across both sites (scripted cell)",
    "scope",
    "List every tariff and strategy that belongs in the pilot scope.",
    "base",
    {
        b.key("base"): cell(
            [
                econ(B19, "ml_forecast", True, 8000, 6000),
                econ(B19, "robust_quantile", True, 12000, 9000),
                econ(PGN, "ml_forecast", False, -1500, -400),
                econ(PGN, "robust_quantile", True, 2500, 1800),
            ]
        )
    },
)
b.add(
    "h09",
    "Should Oregon join the pilot? (scripted B-19, real PGE)",
    "scope",
    "Should the pilot cover the Oregon site as well as California?",
    "base",
    {b.key("base"): cell(b.B19_ONLY)},
)
b.add(
    "h10",
    "Strategy for the California pilot (real large cell, stress passing scripted)",
    "scope",
    "Which dispatch strategy should the California pilot run?",
    "large",
    {b.key("large"): cell(b.LARGE)},
)

HELD_OUT = b.SCENARIOS[start:]


def main() -> int:
    out = b.OUT
    for old in out.glob("h*.yaml"):
        old.unlink()
    for sc in HELD_OUT:
        sc["split"] = "held_out"
        (out / f"{sc['id']}.yaml").write_text(yaml.safe_dump(sc, sort_keys=False, width=100))
    counts: dict[str, int] = {}
    for sc in HELD_OUT:
        counts[sc["expected"]["decision"]] = counts.get(sc["expected"]["decision"], 0) + 1
    print(len(HELD_OUT), "held-out scenarios", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
