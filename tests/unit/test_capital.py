from pathlib import Path

import pandas as pd
import pytest

from edip.core.capital import installed_cost, npv, simple_payback_years, unit_costs

ROOT = Path(__file__).parents[2]
CAPEX = pd.read_csv(ROOT / "data" / "reference" / "atb2025_commercial_battery_capex_2026.csv")
CASES = {"low": "Advanced", "mid": "Moderate", "high": "Conservative"}


def test_unit_costs_reproduce_every_atb_duration():
    for uc in unit_costs(CAPEX, CASES):
        rows = CAPEX[CAPEX.scenario == uc.atb_scenario].set_index("techdetail")["value"]
        for hours in (1, 2, 4, 6, 8):
            per_kw = uc.usd_per_kwh * hours + uc.usd_per_kw
            assert per_kw == pytest.approx(rows[f"{hours}Hr Battery Storage"], rel=1e-3)


def test_low_mid_high_order():
    costs = {u.case: u for u in unit_costs(CAPEX, CASES)}
    assert costs["low"].usd_per_kwh < costs["mid"].usd_per_kwh < costs["high"].usd_per_kwh


def test_payback_and_npv():
    assert simple_payback_years(100_000, 10_000) == 10
    assert simple_payback_years(100_000, -5) is None
    assert npv(100_000, 0, 15, 0.08) == -100_000
    assert npv(0, 1000, 1, 0.08) == pytest.approx(1000 / 1.08)
    uc = unit_costs(CAPEX, CASES)[0]
    assert installed_cost(uc, 10, 20) == pytest.approx(20 * uc.usd_per_kwh + 10 * uc.usd_per_kw)
