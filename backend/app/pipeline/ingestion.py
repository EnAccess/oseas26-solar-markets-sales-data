"""Load raw layers.

Real mode (DEMO_MODE=false):
  - PRIMARY: population.tif + relative_wealth.csv are required.
  - SECONDARY: night_lights.tif, solar_resource.tif, grid.geojson, power_facilities.geojson,
    minigrids.geojson, surveys.csv, gogla.csv are used if present. A missing input stays
    missing (NaN / empty) and is recorded as such; synthetic data is never substituted.
  - Per-layer provenance (source, licence, retrieval date) is recorded in RawLayers.sources.

Demo mode (DEMO_MODE=true): everything is synthetic via demo_generator.
"""
from __future__ import annotations

import json
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
    "grid.geojson": "OSM / Gridfinder / EAE grid lines",
    "power_facilities.geojson": "OSM substations and power plants",
    "surveys.csv": "DHS / MICS / MTF clusters with GPS and solar_ownership",
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
    surveys: pd.DataFrame | None
    gogla: pd.DataFrame | None = None
    is_demo: bool = False
    sources: dict = field(default_factory=dict)
    # Per-cell flag: True where the cell had at least one real RWI observation.
    relative_wealth_observed: np.ndarray | None = None
    # Mapped substations / power plants (points), for display only.
    facilities: gpd.GeoDataFrame | None = None


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


def _source(raw_dir: Path, name: str) -> dict:
    """Provenance for one raw file: its sidecar .meta.json if present, else just the path."""
    meta_path = raw_dir / f"{name}.meta.json"
    info = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return {"status": "real", "file": f"data/raw/{raw_dir.name}/{name}", **info}


def _missing(note: str) -> dict:
    return {"status": "missing", "note": note}


def _load_real(settings: Settings, country: Country, grid: gpd.GeoDataFrame, spec: GridSpec) -> RawLayers:
    """Load real inputs. Missing secondary inputs stay missing (NaN / empty); nothing synthetic is borrowed."""
    raw_dir = settings.raw_path(country.code)

    missing = [f for f in PRIMARY_FILES if not (raw_dir / f).exists()]
    if missing:
        listing = "\n".join(f"  - {f}: {PRIMARY_FILES[f]}" for f in missing)
        raise FileNotFoundError(
            f"DEMO_MODE=false but primary files are missing in {raw_dir}:\n{listing}\n"
            "Run scripts/ingest/fetch_population_wealth.py or set DEMO_MODE=true."
        )
    logger.info("Loading real datasets from %s", raw_dir)
    sources: dict[str, dict] = {}

    # ---- population: people per pixel summed onto the grid ------------------------
    _log_raster_crs(raw_dir / "population.tif", "population.tif")
    pop_total = values_at_cells(raster_to_grid(raw_dir / "population.tif", spec, Resampling.sum), grid)
    # NaN = no raster coverage (outside the source footprint). Kept as unknown, never 0.
    population_density = pop_total / spec.res_km**2
    sources["population"] = _source(raw_dir, "population.tif")

    # ---- relative wealth: mean of RWI tiles whose centre falls in the cell --------
    rwi = pd.read_csv(raw_dir / "relative_wealth.csv")
    validate_columns(rwi, ["latitude", "longitude", "rwi"], "relative_wealth.csv")
    rwi_by_cell = assign_cells(rwi, grid, spec).groupby("cell_id")["rwi"].mean()
    wealth = grid["cell_id"].map(rwi_by_cell).to_numpy(dtype=float)
    wealth_observed = grid["cell_id"].isin(rwi_by_cell.index).to_numpy()
    sources["relative_wealth"] = _source(raw_dir, "relative_wealth.csv")

    # ---- night lights: raster if supplied, else the NASA cache is joined in build --
    nl_path = raw_dir / "night_lights.tif"
    if nl_path.exists():
        night = values_at_cells(raster_to_grid(nl_path, spec, Resampling.average), grid)
        sources["night_lights"] = _source(raw_dir, "night_lights.tif")
    else:
        night = np.full(len(grid), np.nan, dtype=float)
        sources["night_lights"] = _missing("No night_lights.tif; the processed NASA VNP46A2 cache is used if present.")

    sr_path = raw_dir / "solar_resource.tif"
    if sr_path.exists():
        solar = values_at_cells(raster_to_grid(sr_path, spec, Resampling.average), grid)
        sources["solar_resource"] = _source(raw_dir, "solar_resource.tif")
    else:
        solar = np.full(len(grid), np.nan, dtype=float)
        sources["solar_resource"] = _missing("Global Solar Atlas GHI raster not supplied.")

    grid_path = raw_dir / "grid.geojson"
    grid_lines = _read_vector(grid_path)
    sources["grid"] = (_source(raw_dir, "infrastructure") | {"file": "data/raw/RW/grid.geojson"}
                       if grid_path.exists() else _missing("Run scripts/update_grid_from_overpass.py."))
    facilities = _read_vector(raw_dir / "power_facilities.geojson")

    mg_path = raw_dir / "minigrids.geojson"
    minigrids = _read_vector(mg_path)
    sources["minigrids"] = (_source(raw_dir, "minigrids.geojson") if mg_path.exists()
                            else _missing("No verified minigrid dataset is available in the repository."))

    surveys_path = raw_dir / "surveys.csv"
    surveys = pd.read_csv(surveys_path) if surveys_path.exists() else None
    sources["surveys"] = (_source(raw_dir, "surveys.csv") if surveys_path.exists()
                          else _missing("No georeferenced (GPS) survey clusters; model labels cannot be built."))

    gogla_path = raw_dir / "gogla.csv"
    gogla = pd.read_csv(gogla_path) if gogla_path.exists() else None
    sources["gogla"] = _source(raw_dir, "gogla.csv") if gogla_path.exists() else _missing("No GOGLA table supplied.")

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
        facilities=facilities,
    )


def load_raw_layers(settings: Settings, country: Country, grid: gpd.GeoDataFrame, spec: GridSpec) -> RawLayers:
    if settings.demo_mode:
        from .demo_generator import generate_demo

        return generate_demo(settings, country, grid, spec)
    return _load_real(settings, country, grid, spec)
