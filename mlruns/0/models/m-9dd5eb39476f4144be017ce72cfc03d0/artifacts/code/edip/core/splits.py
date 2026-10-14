"""Chronological train, validation, and test partitions (FR5)."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, model_validator

SPLIT_NAMES = ("train", "validation", "test")


class SplitBounds(BaseModel):
    """Half-open [start, end) ranges on hour_start, in order and without overlap."""

    train: tuple[pd.Timestamp, pd.Timestamp]
    validation: tuple[pd.Timestamp, pd.Timestamp]
    test: tuple[pd.Timestamp, pd.Timestamp]

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _ordered(self) -> SplitBounds:
        prev_end = None
        for name in SPLIT_NAMES:
            start, end = getattr(self, name)
            if start >= end:
                raise ValueError(f"{name}: start must be before end")
            if prev_end is not None and start < prev_end:
                raise ValueError(f"{name} overlaps the previous split")
            prev_end = end
        return self


def assign_split(hour_start: pd.DatetimeIndex, bounds: SplitBounds) -> pd.Series:
    """Label each hour with its split; hours outside every range get None."""
    labels = pd.Series(None, index=hour_start, dtype=object)
    for name in SPLIT_NAMES:
        start, end = getattr(bounds, name)
        labels[(hour_start >= start) & (hour_start < end)] = name
    return labels
