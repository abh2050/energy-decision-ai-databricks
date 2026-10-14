"""Forecast evaluation metrics (FR11, PRD section 6). Pure functions over aligned frames.

Input frame: one row per (decision_date, horizon_h) with columns `actual` and the
forecaster's columns: `point` for point forecasters; `p10`, `p50`, `p90` for quantiles.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}


def mae(actual: pd.Series, pred: pd.Series) -> float:
    return float((actual - pred).abs().mean())


def mape(actual: pd.Series, pred: pd.Series) -> float:
    """Mean absolute percentage error in percent; hours with zero actual load are skipped."""
    mask = actual != 0
    return float(((actual[mask] - pred[mask]).abs() / actual[mask].abs()).mean() * 100)


def pinball(actual: pd.Series, pred: pd.Series, q: float) -> float:
    diff = actual - pred
    return float(np.maximum(q * diff, (q - 1) * diff).mean())


def coverage(actual: pd.Series, lower: pd.Series, upper: pd.Series) -> float:
    """Share of hours (percent) where lower <= actual <= upper."""
    return float(((actual >= lower) & (actual <= upper)).mean() * 100)


def by_horizon(frame: pd.DataFrame, pred_col: str) -> pd.DataFrame:
    rows = []
    for h, g in frame.groupby("horizon_h"):
        rows.append(
            {
                "horizon_h": int(h),
                "mae_kw": mae(g.actual, g[pred_col]),
                "mape_pct": mape(g.actual, g[pred_col]),
            }
        )
    return pd.DataFrame(rows)


class PeakError(BaseModel):
    mean_abs_error_at_actual_peak_kw: float  # |forecast - actual| in the hour of the daily peak
    mean_abs_peak_magnitude_error_kw: float  # |max forecast - max actual| per day
    peak_hour_hit_rate_pct: float  # forecast peak falls in the same hour as the actual peak


def peak_error(frame: pd.DataFrame, pred_col: str) -> PeakError:
    at_peak, magnitude, hits = [], [], []
    for _, day in frame.groupby("decision_date"):
        i = day["actual"].idxmax()
        at_peak.append(abs(day.loc[i, pred_col] - day.loc[i, "actual"]))
        magnitude.append(abs(day[pred_col].max() - day["actual"].max()))
        hits.append(day[pred_col].idxmax() == i)
    return PeakError(
        mean_abs_error_at_actual_peak_kw=float(np.mean(at_peak)),
        mean_abs_peak_magnitude_error_kw=float(np.mean(magnitude)),
        peak_hour_hit_rate_pct=float(np.mean(hits) * 100),
    )


class ForecasterScore(BaseModel):
    forecaster: str
    point_column: str
    hours: int
    days: int
    mae_kw: float
    mape_pct: float
    peak: PeakError
    by_horizon: list[dict[str, float]]
    p10_p90_coverage_pct: float | None = None
    pinball_kw: dict[str, float] | None = None  # per quantile and mean


def score(frame: pd.DataFrame, forecaster: str, point_col: str) -> ForecasterScore:
    has_q = all(c in frame.columns for c in QUANTILES)
    pin = None
    cov = None
    if has_q:
        pin = {q: pinball(frame.actual, frame[q], a) for q, a in QUANTILES.items()}
        pin["mean"] = float(np.mean(list(pin.values())))
        cov = coverage(frame.actual, frame.p10, frame.p90)
    return ForecasterScore(
        forecaster=forecaster,
        point_column=point_col,
        hours=len(frame),
        days=int(frame.decision_date.nunique()),
        mae_kw=mae(frame.actual, frame[point_col]),
        mape_pct=mape(frame.actual, frame[point_col]),
        peak=peak_error(frame, point_col),
        by_horizon=by_horizon(frame, point_col).to_dict("records"),
        p10_p90_coverage_pct=cov,
        pinball_kw=pin,
    )
