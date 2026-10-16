"""Map-ready layer definitions and GeoJSON builders.

Every layer is built from the same cached cell table as the cell API and reports, so a value on
the map is the value in the panel and the report. Cells without a value are kept (value = null)
so coverage gaps stay visible instead of disappearing.
"""
from __future__ import annotations

import pandas as pd

from ..pipeline.export import cells_to_geojson
from .indicators import INDICATORS, KIND_LABELS, display_value, source_date, source_name


class LayerUnavailableError(RuntimeError):
    """Raised when a layer's source column is not present in the dataset."""


# `selector=False` layers stay available through the API (e.g. for EAE) but are not offered in the UI.
LAYERS: dict[str, dict] = {
    "market_gap": dict(
        name="Potential Market Gap", column="market_gap_score", selector=True,
        legend=("Lower priority", "Medium", "Higher priority"),
        direction="Higher = more people, farther from the mapped grid, darker, and less evidence of existing solar.",
    ),
    "population": dict(
        name="Population Density", column="population_density", selector=True, log=True,
        legend=("Sparse", "Medium", "Dense"), direction="Higher = more people per km².",
    ),
    "night_lights": dict(
        name="Nighttime Lights", column="nighttime_radiance", selector=True, log=True,
        legend=("Dark", "Medium", "Bright"),
        direction="Higher = brighter. Dark does not mean no solar: small systems are invisible to satellites.",
    ),
    "grid": dict(
        name="Distance to Mapped Grid", column="distance_to_grid_km", selector=True,
        legend=("Near grid", "Medium", "Far from grid"), direction="Higher = farther from a mapped power line.",
    ),
    "survey_solar": dict(
        name="Solar Ownership (district survey)", column="survey_solar_share", selector=True,
        legend=("Lower", "Medium", "Higher"),
        direction="Higher = larger estimated share of households owning a solar device (district-wide value).",
    ),
    "relative_wealth": dict(
        name="Relative Wealth", column="relative_wealth", selector=True,
        legend=("Poorer", "National mean", "Wealthier"), direction="Higher = wealthier than the national mean.",
    ),
    "population_total": dict(
        name="Total Population", column="population_total", selector=False,
        legend=("Few", "Medium", "Many"), direction="Higher = more people in the cell.",
    ),
    "solar_penetration": dict(
        name="Predicted Solar Penetration", column="predicted_solar_penetration", selector=False,
        legend=("Very low", "Medium", "Very high"), direction="Higher = larger predicted share of households.",
    ),
}


def available_layers(cells: pd.DataFrame) -> dict[str, dict]:
    """Layers whose source column exists and has at least one value."""
    return {k: v for k, v in LAYERS.items()
            if v["column"] in cells.columns and cells[v["column"]].notna().any()}


def layer_catalog(cells: pd.DataFrame, sources: dict) -> list[dict]:
    out = []
    for layer_id, layer in available_layers(cells).items():
        spec = INDICATORS[layer["column"]]
        out.append({
            "id": layer_id, "name": layer["name"], "description": spec["description"], "unit": spec["unit"],
            "selector": layer["selector"], "kind": KIND_LABELS[spec["kind"]],
            "source": source_name(spec["source"], sources),
        })
    return out


def cached_layer(svc, code: str, layer_id: str) -> dict:
    """GeoJSON for a layer, built once per dataset version (the cache resets when source files change)."""
    cache = svc.layer_cache(code)
    if layer_id not in cache:
        cache[layer_id] = build_layer(svc.cells(code), svc.spec(code).deg, layer_id,
                                      svc.meta(code).get("sources", {}))
    return cache[layer_id]


def warm(svc, code: str) -> None:
    """Pre-build every available layer so the first map request is fast."""
    for layer_id in available_layers(svc.cells(code)):
        cached_layer(svc, code, layer_id)


def build_layer(cells: pd.DataFrame, deg: float, layer_id: str, sources: dict) -> dict:
    layer = LAYERS[layer_id]
    column = layer["column"]
    if column not in cells.columns:
        raise LayerUnavailableError(f"Layer '{layer_id}' requires column '{column}', which is not in the dataset.")
    spec = INDICATORS[column]

    frame = cells[["cell_id", "lon", "lat"]].copy()
    frame["name"] = cells["place_name"] if "place_name" in cells else cells["cell_id"]
    frame["value"] = [display_value(column, v) for v in cells[column]]
    values = frame["value"].dropna()
    lo, hi = (float(values.quantile(0.02)), float(values.quantile(0.98))) if len(values) else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1e-6

    fc = cells_to_geojson(frame, deg, {"cell_id": "cell_id", "name": "name", "value": "value"})
    source = sources.get(spec["source"], {})
    fc["metadata"] = {
        "layer": layer_id,
        "name": layer["name"],
        "unit": spec["unit"],
        "description": spec["description"],
        "direction": layer["direction"],
        "kind": KIND_LABELS[spec["kind"]],
        "source": source_name(spec["source"], sources),
        "source_date": source_date(source),
        "licence": source.get("licence"),
        "scale": "log" if layer.get("log") else "linear",
        "min": round(lo, 4),
        "max": round(hi, 4),
        "range_note": "Colour range: 2nd to 98th percentile of cells in Rwanda.",
        "legend": dict(zip(("low", "mid", "high"), layer["legend"])),
        "n_cells": len(frame),
        "n_missing": int(frame["value"].isna().sum()),
    }
    return fc
