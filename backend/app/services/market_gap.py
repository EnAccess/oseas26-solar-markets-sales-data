"""Energy need and the Potential Market Gap (market opportunity score). Single source of truth.

    energy_need_score  = weighted mean of three 0-1 components (weights NEED_W_*):
                           population    scaled log(1 + population density)        higher = more people
                           remoteness    scaled distance to mapped grid             higher = farther
                           darkness      1 - scaled log(1 + nighttime radiance)     higher = darker
                         Scaling is the 2nd-98th percentile of the country's non-missing values.
                         Darkness carries the smallest weight because it is correlated with
                         remoteness; darkness is a proxy for no grid, never for "no solar".
    solar_uptake       = best available evidence of existing solar adoption (0-1):
                           1. predicted penetration, only from a model trained on real survey labels
                           2. district survey estimate (MTF survey-weighted households / households)
                           otherwise unknown. Unknown is never treated as zero.
    market_gap_score   = energy_need_score * (1 - solar_uptake), 0-1, shown as a 0-100 score.

The result is a relative screening score for prioritising field investigation. It is not the
percentage of households without solar and it says nothing about commercial viability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Settings

NEED_INPUTS = {
    "population_density": "Population density",
    "distance_to_grid_km": "Distance to mapped grid",
    "nighttime_radiance": "Nighttime radiance",
}
UPTAKE_MODEL = "model_prediction"
UPTAKE_SURVEY = "district_survey"
UPTAKE_UNKNOWN = "unknown"
SMALL_SAMPLE = 10  # sampled solar households per district below which survey evidence is "limited"

METHOD = {
    "name": "Potential Market Gap (market opportunity score)",
    "version": "2.0",
    "formula": "market_gap_score = energy_need_score x (1 - solar_uptake)",
    "energy_need": "weighted mean of scaled log population density, scaled distance to mapped grid, "
                   "and 1 - scaled log nighttime radiance (2nd-98th percentile scaling)",
    "solar_uptake": "model prediction trained on real survey labels if available; otherwise the "
                    "district MTF survey estimate; otherwise unknown (no score)",
    "interpretation": "Relative 0-100 priority for field investigation. Not a measured percentage "
                      "and not evidence of commercial viability.",
}


def scale(values: pd.Series, lo_q: float = 0.02, hi_q: float = 0.98) -> pd.Series:
    """Percentile-clip and rescale to 0-1. Missing values stay missing."""
    finite = values[np.isfinite(values)]
    if finite.empty:
        return pd.Series(np.nan, index=values.index)
    lo, hi = finite.quantile(lo_q), finite.quantile(hi_q)
    if hi <= lo:
        return values.where(values.isna(), 0.0)
    return ((values - lo) / (hi - lo)).clip(0, 1)


def _column(cells: pd.DataFrame, name: str) -> pd.Series:
    """Numeric column, or all-missing when the dataset does not have it."""
    if name not in cells:
        return pd.Series(np.nan, index=cells.index)
    return pd.to_numeric(cells[name], errors="coerce")


def need_components(cells: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "need_population": scale(np.log1p(_column(cells, "population_density"))),
        "need_remoteness": scale(_column(cells, "distance_to_grid_km")),
        "need_darkness": 1 - scale(np.log1p(_column(cells, "nighttime_radiance"))),
    }, index=cells.index)


def need_weights(settings: Settings) -> np.ndarray:
    return np.array([settings.need_w_population, settings.need_w_grid_distance, settings.need_w_darkness])


def energy_need(cells: pd.DataFrame, settings: Settings) -> pd.Series:
    """Weighted need score; missing when any of its inputs is missing."""
    w = need_weights(settings)
    parts = need_components(cells)
    return pd.Series(parts.to_numpy() @ (w / w.sum()), index=cells.index)


def solar_uptake(cells: pd.DataFrame, model_trusted: bool) -> tuple[pd.Series, pd.Series]:
    """Return (uptake 0-1, source label) per cell using the evidence hierarchy above."""
    uptake = pd.Series(np.nan, index=cells.index)
    source = pd.Series(UPTAKE_UNKNOWN, index=cells.index, dtype=object)
    if "survey_solar_share" in cells:
        has = cells["survey_solar_share"].notna()
        uptake[has] = cells.loc[has, "survey_solar_share"]
        source[has] = UPTAKE_SURVEY
    if model_trusted and "predicted_solar_penetration" in cells:
        has = cells["predicted_solar_penetration"].notna()
        uptake[has] = cells.loc[has, "predicted_solar_penetration"]
        source[has] = UPTAKE_MODEL
    return uptake.clip(0, 1), source


def evidence_level(source: pd.Series, need: pd.Series, sampled: pd.Series | None) -> pd.Series:
    level = pd.Series("indicative", index=source.index, dtype=object)
    if sampled is not None:
        level[(source == UPTAKE_SURVEY) & (sampled.fillna(0) < SMALL_SAMPLE)] = "limited"
    level[need.isna() | (source == UPTAKE_UNKNOWN)] = "insufficient"
    return level


def missing_inputs(cells: pd.DataFrame, uptake_source: pd.Series) -> pd.Series:
    labels = []
    for idx in cells.index:
        missing = [label for col, label in NEED_INPUTS.items()
                   if col not in cells or pd.isna(cells.at[idx, col])]
        if uptake_source[idx] == UPTAKE_UNKNOWN:
            missing.append("Solar uptake evidence")
        labels.append("; ".join(missing))
    return pd.Series(labels, index=cells.index, dtype=object)


def add_market_scores(cells: pd.DataFrame, settings: Settings, model_trusted: bool = False) -> pd.DataFrame:
    """Add energy_need_score, solar_uptake, uptake_source, market_gap_score, evidence_level, missing_inputs."""
    out = cells.copy()
    need = energy_need(out, settings)
    uptake, source = solar_uptake(out, model_trusted)
    out["energy_need_score"] = need.round(4)
    out["solar_uptake"] = uptake.round(4)
    out["uptake_source"] = source
    out["market_gap_score"] = (need * (1 - uptake)).round(4)  # NaN when need or uptake is unknown
    out["evidence_level"] = evidence_level(source, need, out.get("survey_solar_hh_sampled"))
    out["missing_inputs"] = missing_inputs(out, source)
    return out


def opportunity_score_100(market_gap_score: float | None) -> int | None:
    """0-1 score -> integer 0-100 for display (no false precision)."""
    if market_gap_score is None or pd.isna(market_gap_score):
        return None
    return int(round(float(market_gap_score) * 100))
