"""ONNX export of LightGBM forecasters for the browser sandbox (FR13)."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import onnxruntime as ort
import pandas as pd
from onnxmltools import convert_lightgbm
from onnxmltools.convert.common.data_types import FloatTensorType

INPUT_NAME = "features"


def to_onnx(model: lgb.LGBMRegressor, n_features: int, opset: int) -> bytes:
    onx = convert_lightgbm(
        model,
        initial_types=[(INPUT_NAME, FloatTensorType([None, n_features]))],
        target_opset=opset,
        zipmap=False,
    )
    return onx.SerializeToString()


def onnx_predict(onnx_bytes: bytes, X: pd.DataFrame) -> np.ndarray:
    session = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    out = session.run(None, {INPUT_NAME: X.to_numpy(dtype=np.float32)})[0]
    return np.asarray(out).reshape(-1)


def parity_max_abs_diff(model: lgb.LGBMRegressor, onnx_bytes: bytes, X: pd.DataFrame) -> float:
    """Largest absolute difference (kW) between the Python model and its ONNX export."""
    return float(np.max(np.abs(model.predict(X) - onnx_predict(onnx_bytes, X))))
