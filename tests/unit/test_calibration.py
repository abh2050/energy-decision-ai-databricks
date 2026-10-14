import numpy as np
import pandas as pd
import pytest

from edip.core.calibration import apply_cqr, conformal_quantile, fit_cqr


def _frame(days: int, width: float, noise_by_hour: np.ndarray, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(days):
        for h in range(24):
            mu = 500.0
            rows.append(
                {
                    "decision_date": d,
                    "horizon_h": h,
                    "actual": mu + rng.normal(0, noise_by_hour[h]),
                    "p10": mu - width,
                    "p50": mu,
                    "p90": mu + width,
                }
            )
    return pd.DataFrame(rows)


def test_conformal_quantile_finite_sample_level():
    scores = np.arange(1, 11, dtype=float)  # n = 10, ceil(11 * 0.8) / 10 = 0.9
    assert conformal_quantile(scores, 0.8) == 9.0


def test_per_hour_corrections_widen_noisy_hours_and_narrow_quiet_ones():
    noise = np.where(np.arange(24) < 12, 5.0, 60.0)  # quiet morning, noisy afternoon
    cal = _frame(92, width=20.0, noise_by_hour=noise, seed=0)
    cqr = fit_cqr(cal, 0.8, "2013-10-01", "2014-01-01")
    q = cqr.as_array()
    assert (q[:12] < 0).all()  # band too wide for quiet hours -> narrowed
    assert (q[12:] > 0).all()  # too narrow for noisy hours -> widened
    assert all(c.n == 92 for c in cqr.per_hour)

    test = _frame(365, width=20.0, noise_by_hour=noise, seed=1)
    lo, hi = apply_cqr(test.p10, test.p50, test.p90, test.horizon_h, cqr)
    covered = (test.actual >= lo) & (test.actual <= hi)
    raw = (test.actual >= test.p10) & (test.actual <= test.p90)
    assert covered.mean() == pytest.approx(0.8, abs=0.04)
    assert abs(covered.mean() - 0.8) < abs(raw.mean() - 0.8)


def test_band_stays_ordered_around_p50():
    cal = _frame(30, width=100.0, noise_by_hour=np.full(24, 1.0), seed=2)
    cqr = fit_cqr(cal, 0.8, "a", "b")  # large negative corrections
    lo, hi = apply_cqr(cal.p10, cal.p50, cal.p90, cal.horizon_h, cqr)
    assert (lo <= cal.p50).all() and (cal.p50 <= hi).all()
