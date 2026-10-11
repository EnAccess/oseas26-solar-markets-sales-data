"""Map-ready layer definitions and GeoJSON builders."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..pipeline.export import cells_to_geojson


class LayerUnavailableError(RuntimeError):
    """Raised when a layer's source column is not present in the dataset."""
    pass


LAYERS: dict[str, dict] = {
    "population": dict(
        name="Population Density", column="population_density", unit="people/km2", fixed=None,
        description="Modelled population per square kilometre.",
        legend=("Low", "Medium", "High"),
    ),
    "population_total": dict(
        name="Total Population", column="population_total", unit="people", fixed=None,
        description="Estimated people within each source grid cell.",
        legend=("Few", "Medium", "Many"),
    ),
    "night_lights": dict(
        name="Nighttime Lights", column="nighttime_radiance", unit="nW/cm2/sr", fixed=None,
        description="Satellite night-time radiance. Dark does not mean no solar: small systems are invisible to satellites.",
        legend=("Dark", "Medium", "Bright"),
    ),
    "grid": dict(
        name="Distance to Grid", column="distance_to_grid_km", unit="km", fixed=None,
        description="Distance from the cell centre to the nearest mapped grid line.",
        legend=("Near grid", "Medium", "Far from grid"),
    ),
    "solar_resource": dict(
        name="Solar Households (survey)", column="solar_households", unit="households", fixed=None,
        description="MTF survey households with a solar device. District totals mapped onto each 5 km grid cell.",
        legend=("Few", "Medium", "Many"),
    ),
    "relative_wealth": dict(
        name="Relative Wealth", column="relative_wealth", unit="RWI", fixed=None,
        description="Meta Relative Wealth Index. Positive = wealthier than national median.",
        legend=("Poorer", "Median", "Wealthier"),
    ),
    "solar_penetration": dict(
        name="Predicted Solar Penetration", column="predicted_solar_penetration", unit="0-1", fixed=(0.0, 1.0),
        description="Model estimate of the share of households using off-grid solar (0 = very low, 1 = very high).",
        legend=("Very low", "Medium", "Very high"),
    ),
    "market_gap": dict(
        name="Potential Market Gap", column="market_gap_score", unit="0-1", fixed=None,
        description="Energy need x (1 - predicted penetration). A screening indicator, not proof of commercial viability.",
        legend=("Low opportunity", "Medium", "Potentially underserved"),
    ),
}



_BASE = Path(__file__).resolve().parents[2] / "data" / "processed" / "RW"
_CELLS_SURVEY = _BASE / "cells_with_survey.csv"


def available_layers(cells: pd.DataFrame) -> dict[str, dict]:
    """Return only layers whose source column is present in cells."""
    return {k: v for k, v in LAYERS.items() if v["column"] in cells.columns}


def layer_catalog(cells: pd.DataFrame | None = None) -> list[dict]:
    src = available_layers(cells) if cells is not None else LAYERS
    return [
        {"id": k, "name": v["name"], "description": v["description"], "unit": v["unit"]}
        for k, v in src.items()

    ]


def build_layer(cells: pd.DataFrame, deg: float, layer_id: str, is_demo: bool) -> dict:
    if layer_id == "solar_resource":
        return _build_solar_households_cells_layer(deg, is_demo)

    spec = LAYERS[layer_id]
    col = spec["column"]
    if col not in cells.columns:
        raise LayerUnavailableError(
            f"Layer '{layer_id}' requires column '{col}', which is not present in the "
            f"current dataset. Retrain the model to enable this layer."
        )
    if spec["fixed"]:
        lo, hi = spec["fixed"]
    else:
        lo, hi = float(cells[col].quantile(0.02)), float(cells[col].quantile(0.98))
        if hi <= lo:
            hi = lo + 1e-6

    fc = cells_to_geojson(cells, deg, {"value": col})
    for f, cid in zip(fc["features"], cells["cell_id"]):
        f["properties"]["cell_id"] = cid

    fc["metadata"] = {

        "layer": layer_id,
        "name": spec["name"],
        "unit": spec["unit"],
        "description": spec["description"],
        "min": round(lo, 4),
        "max": round(hi, 4),

        "layer": layer_id, "name": spec["name"], "unit": spec["unit"],
        "description": spec["description"],
        "min": round(lo, 4), "max": round(hi, 4),

        "legend": {"low": spec["legend"][0], "mid": spec["legend"][1], "high": spec["legend"][2]},
        "is_demo": is_demo,
    }
    return fc


def _build_solar_households_cells_layer(deg: float, is_demo: bool) -> dict:
    df = pd.read_csv(_CELLS_SURVEY).dropna(subset=["solar_households"]).reset_index(drop=True)

    spec = LAYERS["solar_resource"]
    lo = float(df["solar_households"].quantile(0.02))
    hi = float(df["solar_households"].quantile(0.98))
    if hi <= lo:
        hi = lo + 1e-6

    fc = cells_to_geojson(df, deg, {"value": "solar_households"})
    for f, cid in zip(fc["features"], df["cell_id"]):
        f["properties"]["cell_id"] = cid

    fc["metadata"] = {
        "layer": "solar_resource",
        "name": spec["name"],
        "unit": spec["unit"],
        "description": spec["description"],
        "min": round(lo, 4),
        "max": round(hi, 4),
        "legend": {"low": "Few", "mid": "Medium", "high": "Many"},
        "is_demo": is_demo,
    }
    return fc