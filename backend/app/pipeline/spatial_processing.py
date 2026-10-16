"""Common spatial grid, CRS handling and raster -> grid resampling."""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject
from shapely.geometry import Polygon

from ..countries import Country

logger = logging.getLogger(__name__)
KM_PER_DEG = 111.32
WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class GridSpec:
    """Regular lat/lon grid anchored at the top-left of the country bounding box."""

    min_lon: float
    max_lat: float
    deg: float
    n_rows: int
    n_cols: int
    res_km: float

    @property
    def transform(self):
        return from_origin(self.min_lon, self.max_lat, self.deg, self.deg)

    def to_dict(self) -> dict:
        return asdict(self)


def make_grid_spec(country: Country, res_km: float) -> GridSpec:
    min_lon, min_lat, max_lon, max_lat = country.bbox
    deg = res_km / KM_PER_DEG
    return GridSpec(
        min_lon=min_lon,
        max_lat=max_lat,
        deg=deg,
        n_rows=math.ceil((max_lat - min_lat) / deg),
        n_cols=math.ceil((max_lon - min_lon) / deg),
        res_km=res_km,
    )


def build_grid(
    country: Country, res_km: float, boundary: Polygon | None = None
) -> tuple[gpd.GeoDataFrame, GridSpec]:
    """Create the common grid. Cells whose centroid falls outside `boundary` are dropped."""
    spec = make_grid_spec(country, res_km)
    idx = np.arange(spec.n_rows * spec.n_cols)
    rows, cols = np.divmod(idx, spec.n_cols)
    lon = spec.min_lon + (cols + 0.5) * spec.deg
    lat = spec.max_lat - (rows + 0.5) * spec.deg
    if boundary is not None:
        keep = shapely.contains_xy(boundary, lon, lat)
        rows, cols, lon, lat = rows[keep], cols[keep], lon[keep], lat[keep]
    if len(rows) == 0:
        raise ValueError("No grid cells fall inside the country boundary.")
    h = spec.deg / 2
    gdf = gpd.GeoDataFrame(
        {
            "cell_id": [f"{country.code}_{i + 1:04d}" for i in range(len(rows))],
            "row": rows.astype(int),
            "col": cols.astype(int),
            "lon": lon,
            "lat": lat,
        },
        geometry=shapely.box(lon - h, lat - h, lon + h, lat + h),
        crs=WGS84,
    )
    logger.info("Built %d grid cells at %.1f km resolution", len(gdf), res_km)
    return gdf, spec


def project_points(lon, lat, epsg: int) -> np.ndarray:
    """Return an (n, 2) array of metric x/y coordinates."""
    pts = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=WGS84).to_crs(epsg=epsg)
    return np.column_stack([pts.x.to_numpy(), pts.y.to_numpy()])


def assign_cells(df: pd.DataFrame, grid: gpd.GeoDataFrame, spec: GridSpec,
                 lat_col: str = "latitude", lon_col: str = "longitude") -> pd.DataFrame:
    """Attach `cell_id` to point records. Points outside the grid are dropped."""
    out = df.copy()
    out["row"] = np.floor((spec.max_lat - out[lat_col]) / spec.deg).astype(int)
    out["col"] = np.floor((out[lon_col] - spec.min_lon) / spec.deg).astype(int)
    merged = out.merge(grid[["cell_id", "row", "col"]], on=["row", "col"], how="inner")
    dropped = len(out) - len(merged)
    if dropped:
        logger.info("%d point records fell outside the grid and were dropped", dropped)
    return merged


def raster_to_grid(path, spec: GridSpec, resampling: Resampling) -> np.ndarray:
    """Reproject + resample any raster onto the common grid. Returns (n_rows, n_cols) float array.

    Use Resampling.sum for count-like rasters (population) and Resampling.average for
    continuous ones (radiance, GHI).
    """
    dst = np.full((spec.n_rows, spec.n_cols), np.nan, dtype="float32")
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            dst_transform=spec.transform,
            dst_crs=WGS84,
            resampling=resampling,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    return dst


def values_at_cells(arr2d: np.ndarray, grid: gpd.GeoDataFrame) -> np.ndarray:
    return arr2d[grid["row"].to_numpy(), grid["col"].to_numpy()].astype(float)
