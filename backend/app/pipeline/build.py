"""End-to-end data pipeline: load -> validate -> clean -> grid -> features -> processed CSV.

Run:  python -m app.pipeline.build [--country RW]
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from ..config import Settings, get_settings
from ..countries import get_country
from .cleaning import aggregate_labels, clean_cells, clean_surveys
from .feature_engineering import build_feature_frame
from .ingestion import load_boundary, load_raw_layers
from .spatial_processing import build_grid
from .survey import attach_place_names, attach_survey

logger = logging.getLogger(__name__)
NIGHTLIGHTS_CACHE = "cells_with_nightlights.csv"


def _truthy(name: str) -> bool:
    return os.getenv(name, "false").lower() in {"1", "true", "yes"}


def join_nightlights_cache(cells: pd.DataFrame, processed_dir: Path) -> tuple[pd.DataFrame, dict | None]:
    """Fill nighttime_radiance from the processed NASA VNP46A2 cache when no raster was supplied.

    The cache is keyed by cell_id; coordinates are checked too, so a re-gridded dataset can never
    silently receive another cell's radiance.
    """
    path = processed_dir / NIGHTLIGHTS_CACHE
    if cells["nighttime_radiance"].notna().any() or not path.exists():
        return cells, None
    cache = pd.read_csv(path, usecols=["cell_id", "lon", "lat", "nighttime_radiance"])
    merged = cells[["cell_id", "lon", "lat"]].merge(
        cache, on="cell_id", how="left", suffixes=("", "_cache"), validate="one_to_one"
    )
    offset = np.hypot(merged["lon"] - merged["lon_cache"], merged["lat"] - merged["lat_cache"])
    if merged["lon_cache"].isna().any() or (offset > 1e-6).any():
        logger.warning("%s does not match the current grid; radiance left missing. "
                       "Re-run the night-lights ingest.", path.name)
        return cells, None
    out = cells.copy()
    out["nighttime_radiance"] = merged["nighttime_radiance"].to_numpy()
    snapshots = sorted((processed_dir.parents[1] / "raw").glob("nightlights_RW_*.meta.json"))
    snapshot = json.loads(snapshots[-1].read_text(encoding="utf-8")) if snapshots else {}
    note = "Single-day sample per cell (latest granule within 30 days before the ingest date)."
    if not snapshot:
        note += (" The raw snapshot metadata is not present in this checkout, so the acquisition"
                 " date cannot be verified here.")
    source = {
        "status": "real",
        "file": f"data/processed/{processed_dir.name}/{NIGHTLIGHTS_CACHE}",
        "dataset": "NASA Black Marble VNP46A2 (VIIRS day/night band), sampled at cell centres via LAADS",
        "unit": "nW/cm2/sr",
        "requested_start": snapshot.get("requested_start"),
        "requested_end": snapshot.get("requested_end"),
        "note": note,
    }
    return out, source


def infrastructure_geojson(raw) -> str:
    """Classified mapped infrastructure for display. Nothing is invented when inputs are missing."""
    parts = []
    if not raw.grid_lines.empty:
        lines = raw.grid_lines.copy()
        lines["kind"] = "grid_line"
        lines["line_class"] = lines["power"] if "power" in lines else "line"
        parts.append(lines)
    facilities = raw.facilities
    if facilities is not None and not facilities.empty:
        parts.append(facilities.assign(kind=facilities["power"]))
    if not raw.minigrids.empty:
        parts.append(raw.minigrids.assign(kind="minigrid"))
    if not parts:
        return json.dumps({"type": "FeatureCollection", "features": []})
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    keep = [c for c in ("kind", "line_class", "voltage", "name", "operator", "plant:source", "osm_id")
            if c in gdf.columns]
    return gdf[[*keep, "geometry"]].to_json(na="drop")


def build_dataset(settings: Settings, country_code: str) -> dict:
    country = get_country(country_code)
    out_dir = settings.processed_path(country.code)
    res = settings.grid_resolution_km

    boundary = load_boundary(country, settings.raw_path(country.code), settings.demo_mode)
    grid, spec = build_grid(country, res, boundary)
    raw = load_raw_layers(settings, country, grid, spec)

    cells = clean_cells(build_feature_frame(grid, raw, country, res))
    sources = dict(raw.sources)
    if not raw.is_demo:
        cells, nl_source = join_nightlights_cache(cells, out_dir)
        if nl_source:
            sources["night_lights"] = nl_source
    cells = attach_survey(cells, out_dir, settings.avg_household_size)
    cells = attach_place_names(cells, out_dir)
    sources["survey"] = {
        "status": "real",
        "file": "data/processed/RW/Household_Solar_Device_Use_and_Ownership.csv",
        "dataset": "Multi-Tier Framework (MTF) household survey, solar device module (Rwanda)",
        "resolution": "District (no household GPS)",
        "note": "Survey year is not recorded in the file. The file lists solar-device owners only.",
    }
    sources["districts"] = {"status": "real", "file": "data/processed/RW/rwanda_districts.geojson",
                            "dataset": "GADM level-2 administrative boundaries"}
    sources["place_names"] = {"status": "real", "file": "data/processed/RW/cell_admin_names.csv",
                              "dataset": "Administrative cell names (rwanda-location-lookup boundaries)",
                              "note": "Name of the administrative cell containing each 5 km analysis cell's centre."}

    # ---- training labels: only from georeferenced surveys; synthetic only by explicit override ----
    training, n_labelled, labels = None, 0, "not_written"
    if raw.surveys is not None and not _truthy("SKIP_TRAINING"):
        if raw.is_demo and not _truthy("ALLOW_SYNTHETIC_LABELS"):
            logger.warning("Surveys are synthetic; training.csv not written (set ALLOW_SYNTHETIC_LABELS=true).")
        else:
            survey_labels = aggregate_labels(clean_surveys(raw.surveys), grid, spec)
            training = cells.merge(survey_labels, on="cell_id", how="inner")
            n_labelled = len(training)
            labels = "synthetic" if raw.is_demo else "real"
            if n_labelled < settings.min_training_cells:
                raise ValueError(f"Only {n_labelled} labelled cells; need at least {settings.min_training_cells}.")

    cells.to_csv(out_dir / "cells_features.csv", index=False)
    training_path = out_dir / "training.csv"
    if training is not None:
        training.to_csv(training_path, index=False)
    elif training_path.exists():
        training_path.unlink()  # never leave labels from an earlier (e.g. synthetic) build behind
    if raw.gogla is not None:
        raw.gogla.to_csv(out_dir / "gogla.csv", index=False)
    (out_dir / "infrastructure.geojson").write_text(infrastructure_geojson(raw), encoding="utf-8")

    meta = {
        "country": country.code,
        "country_name": country.name,
        "is_demo": raw.is_demo,
        "training_labels": labels,
        "grid_spec": spec.to_dict(),
        "n_cells": len(cells),
        "n_labelled_cells": n_labelled,
        "bounds": [
            float(cells["lon"].min() - spec.deg / 2), float(cells["lat"].min() - spec.deg / 2),
            float(cells["lon"].max() + spec.deg / 2), float(cells["lat"].max() + spec.deg / 2),
        ],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "assumptions": {"avg_household_size": settings.avg_household_size},
        "sources": sources,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Dataset built: %d cells, %d labelled", len(cells), n_labelled)
    return meta


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Build the processed cell dataset (no model training).")
    parser.add_argument("--country", default=None)
    args = parser.parse_args()
    settings = get_settings()
    print(json.dumps(build_dataset(settings, args.country or settings.default_country), indent=2))
