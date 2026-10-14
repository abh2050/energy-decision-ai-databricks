"""MLflow pyfunc wrapper: one registered model returns point, p10, p50, and p90 (FR12)."""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd

from edip.core.features import FEATURES

ARTIFACTS = ("point", "p10", "p50", "p90")


class LoadForecaster(mlflow.pyfunc.PythonModel):
    def load_context(self, context: Any) -> None:  # noqa: ANN401
        self.boosters = {k: lgb.Booster(model_file=context.artifacts[k]) for k in ARTIFACTS}

    def predict(self, context: Any, model_input: pd.DataFrame, params: Any = None) -> pd.DataFrame:  # noqa: ANN401
        X = model_input[list(FEATURES)].astype("float32").astype("float64")
        out = pd.DataFrame({"point": self.boosters["point"].predict(X)}, index=X.index)
        q = np.sort(np.column_stack([self.boosters[k].predict(X) for k in ARTIFACTS[1:]]), axis=1)
        for i, k in enumerate(ARTIFACTS[1:]):
            out[k] = q[:, i]
        return out
