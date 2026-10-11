"""Prediction and the Potential Market Gap Indicator."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ...config import Settings


def predict_cells(model, cells: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Predict penetration for every cell, clamped to [0, 1]."""
    return np.clip(model.predict(cells[features].to_numpy()), 0.0, 1.0)


def _scale(s: pd.Series, lo_q: float = 0.02, hi_q: float = 0.98) -> pd.Series:
    lo, hi = s.quantile(lo_q), s.quantile(hi_q)
    if hi <= lo:
        return pd.Series(0.0, index=s.index)
    return ((s - lo) / (hi - lo)).clip(0, 1)


def add_scores(cells: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """energy_need_score (0-1): dense population, far from grid, dark at night.
    market_gap_score = energy_need_score * (1 - predicted_solar_penetration).

    This is a screening indicator, NOT an investment or viability model.
    """
    out = cells.copy()
    w = np.array([settings.need_w_population, settings.need_w_grid_distance, settings.need_w_darkness])
    parts = np.column_stack(
        [
            _scale(np.log1p(out["population_density"])),
            _scale(out["distance_to_grid_km"]),
            1 - _scale(np.log1p(out["nighttime_radiance"])),
        ]
    )
    out["energy_need_score"] = (parts @ w / w.sum()).round(4)
    out["market_gap_score"] = (out["energy_need_score"] * (1 - out["predicted_solar_penetration"])).round(4)
    out["predicted_solar_penetration"] = out["predicted_solar_penetration"].round(4)
    return out
