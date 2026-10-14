"""Conformalized quantile regression for the P10 to P90 band (FR10, PRD coverage target).

For each forecast hour h, on calibration days only:
    score_i = max(p10_i - y_i, y_i - p90_i)
    Q_h = the k-th smallest score, k = ceil((n + 1)(1 - alpha)), with 1 - alpha = 0.8
Calibrated band: [p10 - Q_h, p90 + Q_h]. Q_h may be negative, which narrows the band.
P50 is unchanged, and the band is clipped so p10 <= p50 <= p90 still holds.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from pydantic import BaseModel


class HourCorrection(BaseModel):
    horizon_h: int
    n: int
    correction_kw: float


class CqrCorrections(BaseModel):
    target_coverage: float
    calibration_start: str
    calibration_end_exclusive: str
    per_hour: list[HourCorrection]

    def as_array(self) -> np.ndarray:
        out = np.zeros(24)
        for c in self.per_hour:
            out[c.horizon_h] = c.correction_kw
        return out


def conformal_quantile(scores: np.ndarray, coverage: float) -> float:
    n = len(scores)
    if n == 0:
        raise ValueError("no calibration scores")
    k = min(n, math.ceil((n + 1) * coverage))  # k-th smallest score, 1-indexed
    return float(np.sort(scores)[k - 1])


def fit_cqr(
    calibration: pd.DataFrame, coverage: float, start: str, end_exclusive: str
) -> CqrCorrections:
    """`calibration` rows: horizon_h, actual, p10, p90 for complete calibration days."""
    per_hour = []
    for h in range(24):
        g = calibration[calibration.horizon_h == h]
        scores = np.maximum(g.p10 - g.actual, g.actual - g.p90).to_numpy()
        per_hour.append(
            HourCorrection(
                horizon_h=h, n=len(scores), correction_kw=conformal_quantile(scores, coverage)
            )
        )
    return CqrCorrections(
        target_coverage=coverage,
        calibration_start=start,
        calibration_end_exclusive=end_exclusive,
        per_hour=per_hour,
    )


def apply_cqr(
    p10: np.ndarray, p50: np.ndarray, p90: np.ndarray, horizon_h: np.ndarray, cqr: CqrCorrections
) -> tuple[np.ndarray, np.ndarray]:
    q = cqr.as_array()[np.asarray(horizon_h, dtype=int)]
    lo = np.minimum(np.asarray(p10) - q, p50)
    hi = np.maximum(np.asarray(p90) + q, p50)
    return lo, hi
