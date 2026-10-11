"""Spatial feature engineering on the common grid."""
from __future__ import annotations

from typing import TYPE_CHECKING

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from ..countries import Country
from .spatial_processing import WGS84, project_points

if TYPE_CHECKING:  # pragma: no cover
    from .ingestion import RawLayers

DISTANCE_CAP_KM = 150.0


def _union(gdf: gpd.GeoDataFrame):
    geom = gdf.geometry
    return geom.union_all() if hasattr(geom, "union_all") else geom.unary_union


def distance_to_geoms_km(grid: gpd.GeoDataFrame, geoms: gpd.GeoDataFrame | None, epsg: int) -> np.ndarray:
    """Distance (km) from every cell centroid to the nearest geometry, capped at DISTANCE_CAP_KM."""
    if geoms is None or geoms.empty:
        return np.full(len(grid), DISTANCE_CAP_KM)
    pts = gpd.GeoSeries(gpd.points_from_xy(grid["lon"], grid["lat"]), crs=WGS84).to_crs(epsg=epsg)
    union = _union(geoms.to_crs(epsg=epsg))
    return np.minimum(pts.distance(union).to_numpy() / 1000.0, DISTANCE_CAP_KM)


def presence_in_cell(grid: gpd.GeoDataFrame, geoms: gpd.GeoDataFrame | None) -> np.ndarray:
    """1 if any geometry intersects the cell polygon, else 0."""
    if geoms is None or geoms.empty:
        return np.zeros(len(grid), dtype=int)
    union = _union(geoms.to_crs(WGS84))
    return grid.geometry.intersects(union).to_numpy().astype(int)


def settlement_density(grid: gpd.GeoDataFrame, pop_density: np.ndarray, epsg: int, res_km: float) -> np.ndarray:
    """Mean population density over the cell and its neighbours (approx. 3x3 window)."""
    xy = project_points(grid["lon"], grid["lat"], epsg)
    tree = cKDTree(xy)
    neighbours = tree.query_ball_point(xy, r=res_km * 1000 * 1.5)
    return np.array([pop_density[idx].mean() for idx in neighbours])


def build_feature_frame(grid: gpd.GeoDataFrame, raw: "RawLayers", country: Country, res_km: float) -> pd.DataFrame:
    df = pd.DataFrame(grid[["cell_id", "row", "col", "lon", "lat"]])
    df["population_density"] = np.asarray(raw.population_density, dtype=float)
    df["population_total"] = df["population_density"] * res_km**2
    df["nighttime_radiance"] = np.asarray(raw.nighttime_radiance, dtype=float)
    df["relative_wealth"] = np.asarray(raw.relative_wealth, dtype=float)
    if raw.relative_wealth_observed is not None:
        df["relative_wealth_observed"] = raw.relative_wealth_observed.astype(bool)
    else:
        df["relative_wealth_observed"] = True  # demo mode: all cells treated as observed
    df["solar_resource"] = np.asarray(raw.solar_resource, dtype=float)
    df["distance_to_grid_km"] = distance_to_geoms_km(grid, raw.grid_lines, country.utm_epsg)
    df["grid_presence"] = presence_in_cell(grid, raw.grid_lines)
    df["distance_to_minigrid_km"] = distance_to_geoms_km(grid, raw.minigrids, country.utm_epsg)
    df["minigrid_presence"] = presence_in_cell(grid, raw.minigrids)
    pop = df["population_density"].fillna(0).to_numpy()
    df["settlement_density"] = settlement_density(grid, pop, country.utm_epsg, res_km)
    return df
