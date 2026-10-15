from pathlib import Path

import pandas as pd
import pytest

from edip.core.sensitivity import flip_boundaries
from edip.core.tariff import load_tariff, scale_demand

PGN = load_tariff(Path(__file__).parents[2] / "config" / "tariffs" / "low_spread_tou.yaml")


def _rows(strategy, net_by_spread, fixed_by_spread):
    rows = []
    for m in net_by_spread:
        for s, net in ((strategy, net_by_spread[m]), ("fixed_schedule", fixed_by_spread[m])):
            rows.append(
                {
                    "strategy": s,
                    "spread_multiplier": m,
                    "power_fraction": 0.5,
                    "duration_hours": 2,
                    "round_trip_efficiency": 0.9,
                    "degradation_usd_per_kwh": 0.03,
                    "demand_charge_multiplier": 1.0,
                    "net_benefit_usd": net,
                    "beats_no_battery": net > 0,
                    "beats_fixed": net > fixed_by_spread[m],
                }
            )
    return rows


def test_flip_boundary_smallest_spread():
    grid = pd.DataFrame(
        _rows(
            "ml_forecast",
            {1.0: -10, 1.5: -2, 2.0: 5, 3.0: 20},
            {1.0: -20, 1.5: -1, 2.0: -1, 3.0: 1},
        )
    )
    (fb,) = flip_boundaries(grid)
    assert fb.smallest_spread_beating_fixed == 1.0  # -10 > -20
    assert fb.smallest_spread_beating_no_battery == 2.0


def test_flip_boundary_never():
    grid = pd.DataFrame(_rows("robust_quantile", {1.0: -5, 3.0: -1}, {1.0: 0, 3.0: 0}))
    (fb,) = flip_boundaries(grid)
    assert fb.smallest_spread_beating_fixed is None
    assert fb.smallest_spread_beating_no_battery is None


def test_scale_demand_scales_every_demand_rate_and_facility_capacity():
    doubled = scale_demand(PGN, 2.0)
    for a, b in zip(PGN.demand_charges, doubled.demand_charges, strict=True):
        for season in a.rates_usd_per_kw:
            assert b.rates_usd_per_kw[season] == pytest.approx(2 * a.rates_usd_per_kw[season])
    assert doubled.facility_capacity.monthly_charge(800) == pytest.approx(
        2 * PGN.facility_capacity.monthly_charge(800)
    )
    assert scale_demand(PGN, 1.0).demand_charges == PGN.demand_charges
