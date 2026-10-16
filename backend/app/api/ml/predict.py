"""Prediction helpers. The market-gap calculation lives in services/market_gap.py."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ...config import Settings
from ...services.market_gap import add_market_scores


def predict_cells(model, cells: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Predict penetration for every cell, clamped to [0, 1]."""
    return np.clip(model.predict(cells[features].to_numpy()), 0.0, 1.0)


def add_scores(cells: pd.DataFrame, settings: Settings, model_trusted: bool) -> pd.DataFrame:
    """Round predictions and add the shared energy-need / market-gap columns."""
    out = cells.copy()
    out["predicted_solar_penetration"] = out["predicted_solar_penetration"].round(4)
    return add_market_scores(out, settings, model_trusted)
