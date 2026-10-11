"""Validation and cleaning for cell features and survey labels."""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from .spatial_processing import GridSpec, assign_cells

logger = logging.getLogger(__name__)

CELL_COLUMNS = [
    "cell_id", "row", "col", "lon", "lat", "population_density", "population_total",
    "nighttime_radiance", "relative_wealth", "solar_resource", "distance_to_grid_km",
    "grid_presence", "distance_to_minigrid_km", "minigrid_presence", "settlement_density",
    "relative_wealth_observed",
]


def validate_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def clean_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Fill gaps with the column median and clip physically impossible values."""
    validate_columns(df, CELL_COLUMNS, "cell features")
    out = df.copy()

    # Preserve boolean flag columns untouched.
    bool_cols = {"relative_wealth_observed"}
    numeric = [c for c in CELL_COLUMNS if c not in {"cell_id"} and c not in bool_cols]

    for col in numeric:
        n_missing = int(out[col].isna().sum())
        if n_missing:
            logger.warning("Filling %d missing values in '%s' with the median", n_missing, col)
            out[col] = out[col].fillna(out[col].median() if out[col].notna().any() else 0.0)

    for col in ["population_density", "population_total", "nighttime_radiance",
                "distance_to_grid_km", "distance_to_minigrid_km", "settlement_density"]:
        out[col] = out[col].clip(lower=0)
    out["solar_resource"] = out["solar_resource"].clip(lower=0.1)
    for col in ["grid_presence", "minigrid_presence"]:
        out[col] = (out[col] > 0).astype(int)

    # Ensure the flag column is proper bool, not object/float.
    if "relative_wealth_observed" in out.columns:
        out["relative_wealth_observed"] = out["relative_wealth_observed"].astype(bool)

    return out

def clean_surveys(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise survey records. Expected columns: latitude, longitude, solar_ownership.

    Optional: electricity_access, n_households (weight; defaults to 1).
    solar_ownership may be household-level (0/1) or a cluster share (0-1 or 0-100).
    """
    validate_columns(df, ["latitude", "longitude", "solar_ownership"], "survey data")
    out = df.copy()
    for col in ["latitude", "longitude", "solar_ownership", "electricity_access", "n_households"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    before = len(out)
    out = out.dropna(subset=["latitude", "longitude", "solar_ownership"])
    out = out[out["latitude"].between(-90, 90) & out["longitude"].between(-180, 180)]
    if out["solar_ownership"].max() > 1.0:
        logger.warning("solar_ownership looks like a percentage; dividing by 100")
        out["solar_ownership"] = out["solar_ownership"] / 100.0
    out["solar_ownership"] = out["solar_ownership"].clip(0, 1)
    if "n_households" not in out.columns:
        out["n_households"] = 1.0
    out["n_households"] = out["n_households"].fillna(1.0).clip(lower=1.0)
    if len(out) < before:
        logger.info("Dropped %d invalid survey rows", before - len(out))
    return out.reset_index(drop=True)


def aggregate_labels(surveys: pd.DataFrame, grid: gpd.GeoDataFrame, spec: GridSpec) -> pd.DataFrame:
    """Household-weighted mean of solar ownership per grid cell -> `solar_penetration` (0-1)."""
    joined = assign_cells(surveys, grid, spec)
    if joined.empty:
        raise ValueError("No survey records fall inside the grid.")
    joined["w_solar"] = joined["solar_ownership"] * joined["n_households"]
    g = joined.groupby("cell_id")
    labels = pd.DataFrame(
        {
            "solar_penetration": g["w_solar"].sum() / g["n_households"].sum(),
            "n_survey_clusters": g.size(),
            "n_households_surveyed": g["n_households"].sum(),
        }
    ).reset_index()
    labels["solar_penetration"] = labels["solar_penetration"].clip(0, 1)
    return labels
