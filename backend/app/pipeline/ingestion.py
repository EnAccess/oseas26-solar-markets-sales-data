"""Load raw layers.

Real mode (DEMO_MODE=false):
  - PRIMARY: population.tif + relative_wealth.csv are required.
  - SECONDARY: night_lights.tif, solar_resource.tif, grid.geojson, surveys.csv
    are used if present; otherwise fallback arrays are borrowed from the
    synthetic demo generator so the pipeline does not abort.
  - RawLayers.is_demo is set to False whenever the primary files load.
  - Per-layer provenance is recorded in RawLayers.sources.

Demo mode (DEMO_MODE=true): everything is synthetic via demo_generator.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from shapely.geometry import Polygon

from ..config import Settings
from ..countries import Country
from .cleaning import validate_columns
from .spatial_processing import GridSpec, assign_cells, raster_to_grid, values_at_cells

logger = logging.getLogger(__name__)

# Files required for "real primary data" mode.
PRIMARY_FILES = {
    "population.tif": "WorldPop / Meta HRSL population raster (people per pixel)",
    "relative_wealth.csv": "Meta Relative Wealth Index CSV (latitude, longitude, rwi)",
}

# Files used when present; missing ones fall back to demo_generator output.
SECONDARY_FILES = {
    "night_lights.tif": "NASA Black Marble annual radiance raster",
    "solar_resource.tif": "Global Solar Atlas GHI raster (kWh/m2/day)",
    "grid.geojson": "Gridfinder / OSM / EAE grid lines",
    "surveys.csv": "DHS / MICS / MTF clusters with solar_ownership",
}

OPTIONAL_FILES = {
    "minigrids.geojson": "Existing or planned minigrids (points or lines)",
    "boundary.geojson": "Country boundary polygon (otherwise country.bbox is used)",
    "gogla.csv": "GOGLA national sales CSV",
}


@dataclass
class RawLayers:
    population_density: np.ndarray
    nighttime_radiance: np.ndarray
    relative_wealth: np.ndarray
    solar_resource: np.ndarray
    grid_lines: gpd.GeoDataFrame
    minigrids: gpd.GeoDataFrame
    surveys: pd.DataFrame
    gogla: pd.DataFrame | None = None
    is_demo: bool = False
    sources: dict[str, str] = field(default_factory=dict)
    # NEW: per-cell boolean flag — True where the cell had at least one real RWI observation.
    relative_wealth_observed: np.ndarray | None = None


def empty_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")


def load_boundary(country: Country, raw_dir: Path, use_demo_outline: bool) -> Polygon | None:
    path = raw_dir / "boundary.geojson"
    if not use_demo_outline and path.exists():
        gdf = gpd.read_file(path).to_crs(epsg=4326)
        return gdf.geometry.union_all() if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union
    if country.boundary:
        return Polygon(country.boundary)
    return None


def _read_vector(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        return empty_gdf()
    gdf = gpd.read_file(path)
    return gdf.to_crs(epsg=4326) if gdf.crs else gdf.set_crs(epsg=4326)


def _log_raster_crs(path: Path, label: str) -> None:
    """Diagnostic: surface the CRS and NoData of a raster before we trust its sums."""
    with rasterio.open(path) as src:
        logger.info(
            "%s: crs=%s, shape=%s, nodata=%s, dtype=%s",
            label, src.crs, (src.height, src.width), src.nodata, src.dtypes[0],
        )


def _load_real(settings: Settings, country: Country, grid: gpd.GeoDataFrame, spec: GridSpec) -> RawLayers:
    raw_dir = settings.raw_path(country.code)

    missing = [f for f in PRIMARY_FILES if not (raw_dir / f).exists()]
    if missing:
        listing = "\n".join(f"  - {f}: {PRIMARY_FILES[f]}" for f in missing)
        raise FileNotFoundError(
            f"DEMO_MODE=false but primary files are missing in {raw_dir}:\n{listing}\n"
            "Add them or set DEMO_MODE=true."
        )

    # Fallback arrays for any missing secondary layers.
    from .demo_generator import generate_demo

    logger.info("Loading real primary datasets from %s", raw_dir)
    fallback = generate_demo(settings, country, grid, spec)

    sources: dict[str, str] = {}

    # ---- population (REQUIRED, real) --------------------------------------------
    _log_raster_crs(raw_dir / "population.tif", "population.tif")
    pop_raster = raster_to_grid(raw_dir / "population.tif", spec, Resampling.sum)
    pop_total = values_at_cells(pop_raster, grid)

    # Cells outside the raster footprint are EMPTY, not "unknown": fill with 0.
    # Otherwise clean_cells() would median-impute them, which is wrong for population.
    pop_total = np.nan_to_num(pop_total, nan=0.0, posinf=0.0, neginf=0.0)
    population_density = pop_total / spec.res_km**2
    sources["population"] = "real:data/raw/RW/population.tif"

    # ---- relative wealth (REQUIRED, real) ---------------------------------------
    rwi = pd.read_csv(raw_dir / "relative_wealth.csv")
    validate_columns(rwi, ["latitude", "longitude", "rwi"], "relative_wealth.csv")
    rwi_by_cell = (
        assign_cells(rwi, grid, spec)
        .groupby("cell_id")["rwi"]
        .mean()
    )
    wealth = grid["cell_id"].map(rwi_by_cell).to_numpy(dtype=float)
    # NEW: mark which cells actually had at least one RWI observation.
    # Cells not in rwi_by_cell.index have no data and will later be median-imputed
    # by clean_cells(); the flag lets downstream consumers tell the two apart.
    wealth_observed = grid["cell_id"].isin(rwi_by_cell.index).to_numpy()
    # Keep NaN here: "no RWI observation in this cell" is genuinely unknown.
    sources["relative_wealth"] = "real:data/raw/RW/relative_wealth.csv"

    # ---- secondary layers: real if present, else fallback ------------------------
    nl_path = raw_dir / "night_lights.tif"
    if nl_path.exists():
        night = values_at_cells(raster_to_grid(nl_path, spec, Resampling.average), grid)
        sources["night_lights"] = "real:data/raw/RW/night_lights.tif"
    else:
        night = np.asarray(fallback.nighttime_radiance, dtype=float)
        sources["night_lights"] = "synthetic_fallback:demo_generator"

    sr_path = raw_dir / "solar_resource.tif"
    if sr_path.exists():
        solar = values_at_cells(raster_to_grid(sr_path, spec, Resampling.average), grid)
        sources["solar_resource"] = "real:data/raw/RW/solar_resource.tif"
    else:
        solar = np.asarray(fallback.solar_resource, dtype=float)
        sources["solar_resource"] = "synthetic_fallback:demo_generator"

    grid_path = raw_dir / "grid.geojson"
    if grid_path.exists():
        grid_lines = _read_vector(grid_path)
        sources["grid"] = "real:data/raw/RW/grid.geojson"
    else:
        grid_lines = fallback.grid_lines
        sources["grid"] = "synthetic_fallback:demo_generator"

    surveys_path = raw_dir / "surveys.csv"
    if surveys_path.exists():
        surveys = pd.read_csv(surveys_path)
        sources["surveys"] = "real:data/raw/RW/surveys.csv"
    else:
        surveys = fallback.surveys
        sources["surveys"] = "synthetic_fallback:demo_generator"

    mg_path = raw_dir / "minigrids.geojson"
    minigrids = _read_vector(mg_path) if mg_path.exists() else fallback.minigrids
    sources["minigrids"] = (
        "real:data/raw/RW/minigrids.geojson" if mg_path.exists()
        else "synthetic_fallback:demo_generator"
    )

    gogla_path = raw_dir / "gogla.csv"
    gogla = pd.read_csv(gogla_path) if gogla_path.exists() else fallback.gogla
    sources["gogla"] = (
        "real:data/raw/RW/gogla.csv" if gogla_path.exists()
        else "synthetic_fallback:demo_generator"
    )

    return RawLayers(
        population_density=population_density,
        nighttime_radiance=night,
        relative_wealth=wealth,
        solar_resource=solar,
        grid_lines=grid_lines,
        minigrids=minigrids,
        surveys=surveys,
        gogla=gogla,
        is_demo=False,
        sources=sources,
        relative_wealth_observed=wealth_observed,
    )


def load_raw_layers(settings: Settings, country: Country, grid: gpd.GeoDataFrame, spec: GridSpec) -> RawLayers:
    if settings.demo_mode:
        from .demo_generator import generate_demo

        return generate_demo(settings, country, grid, spec)
    return _load_real(settings, country, grid, spec)