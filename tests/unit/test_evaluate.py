from edip.replay.evaluate import StrategyEconomics, check_targets

TARGETS = {
    "dispatch_economics": {
        "strategies": ["ml_forecast", "robust_quantile"],
        "baseline": "fixed_schedule",
        "min_incremental_pct_of_fixed_net_benefit": 10,
    }
}


def _e(name, gross, op):
    return StrategyEconomics(
        tariff_id="t",
        strategy=name,
        bill_usd=0,
        degradation_usd=0,
        net_benefit_gross_usd=gross,
        operating_cost_usd=op,
        net_benefit_usd=gross - op,
        regret_vs_hindsight_usd=0,
    )


def test_strict_and_single_count_readings():
    op = 5000.0
    econ = [
        _e("fixed_schedule", 50000, 0),
        _e("ml_forecast", 62000, op),
        _e("robust_quantile", 58000, op),
    ]
    checks = {c.strategy: c for c in check_targets(econ, TARGETS, op)}
    ml, robust = checks["ml_forecast"], checks["robust_quantile"]
    # single count: +12,000 >= 5,000 (10%) and > 5,000 op cost -> pass
    assert ml.incremental_single_count_usd == 12000 and ml.passes_single_count
    # strict: (62,000 - 5,000) - 50,000 = 7,000 >= 5,000 and > 5,000 -> pass
    assert ml.incremental_usd == 7000 and ml.passes
    # robust: single +8,000 passes; strict +3,000 fails both conditions
    assert robust.passes_single_count and not robust.passes


def test_negative_fixed_benefit_is_handled():
    econ = [
        _e("fixed_schedule", -10000, 0),
        _e("ml_forecast", -12000, 1000),
        _e("robust_quantile", 4000, 1000),
    ]
    checks = {c.strategy: c for c in check_targets(econ, TARGETS, 1000.0)}
    assert not checks["ml_forecast"].passes
    assert checks["robust_quantile"].passes  # +13,000 strict, above both thresholds
