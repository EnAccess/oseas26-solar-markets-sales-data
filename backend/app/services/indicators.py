"""Indicator catalogue: one description per column, shared by the map, cell API, reports and assistant.

`kind` separates the evidence types the UI must never blur:
  observed            direct measurement (satellite radiance, survey responses, mapped infrastructure)
  external_estimate   another organisation's modelled estimate (WorldPop, Meta RWI)
  derived             calculated here from the inputs above
  model_prediction    output of this project's trained model
"""
from __future__ import annotations

import math

import pandas as pd

INDICATORS: dict[str, dict] = {
    "population_density": dict(
        label="Population density", unit="people/km²", kind="external_estimate", source="population",
        decimals=0,
        description="WorldPop 2020 people-per-pixel summed over the 5 km cell and divided by the nominal "
                    "25 km² cell area. Cells partly outside Rwanda or over water are underestimated.",
    ),
    "population_total": dict(
        label="Population (5 km cell)", unit="people", kind="external_estimate", source="population",
        decimals=0, description="WorldPop 2020 estimated people within the cell.",
    ),
    "nighttime_radiance": dict(
        label="Nighttime radiance", unit="nW/cm²/sr", kind="observed", source="night_lights", decimals=2,
        description="NASA VNP46A2 radiance at the cell centre. Low radiance suggests limited grid "
                    "electricity; solar home systems and lanterns are below the sensor's detection floor.",
    ),
    "distance_to_grid_km": dict(
        label="Distance to mapped grid", unit="km", kind="derived", source="grid", decimals=1,
        description="Distance from the cell centre to the nearest OpenStreetMap power line. Mapped lines "
                    "do not guarantee that nearby households are connected.",
    ),
    "grid_presence": dict(
        label="Mapped grid line in cell", unit="yes/no", kind="observed", source="grid", decimals=0,
        description="Whether any mapped OpenStreetMap power line crosses the cell.",
    ),
    "relative_wealth": dict(
        label="Relative Wealth Index", unit="RWI (0 = national mean)", kind="external_estimate",
        source="relative_wealth", decimals=2,
        description="Mean Meta RWI of the 2.4 km tiles whose centre falls in the cell. Relative, not absolute.",
    ),
    "survey_solar_share": dict(
        label="District solar-device ownership (estimate)", unit="% of households", kind="derived",
        source="survey", decimals=1, percent=True,
        description="MTF survey-weighted solar-owning households in the district divided by WorldPop "
                    "district population / assumed household size. District-wide, small samples.",
    ),
    "survey_solar_hh_weighted": dict(
        label="Survey-weighted solar households (district)", unit="households", kind="observed",
        source="survey", decimals=0,
        description="Sum of MTF household weights for ordinary households reporting a solar device.",
    ),
    "survey_solar_hh_sampled": dict(
        label="Sampled solar households (district)", unit="households", kind="observed", source="survey",
        decimals=0, description="Number of distinct surveyed households with a solar device in the district.",
    ),
    "predicted_solar_penetration": dict(
        label="Predicted solar penetration", unit="% of households", kind="model_prediction",
        source="model", decimals=0, percent=True,
        description="This project's model estimate. Only shown when the model was trained on real labels.",
    ),
    "energy_need_score": dict(
        label="Energy need score", unit="score 0–100", kind="derived", source="method", decimals=0,
        percent=True, description="Population, distance to grid and darkness, scaled within Rwanda.",
    ),
    "market_gap_score": dict(
        label="Market opportunity score", unit="score 0–100", kind="derived", source="method", decimals=0,
        percent=True,
        description="Energy need × (1 − solar uptake evidence). A relative priority for field "
                    "investigation, not a percentage of households and not proof of viability.",
    ),
}

KIND_LABELS = {
    "observed": "Observed",
    "external_estimate": "External modelled estimate",
    "derived": "Derived in this tool",
    "model_prediction": "Model prediction",
}

REPORT_INDICATORS = [
    "population_total", "population_density", "nighttime_radiance", "distance_to_grid_km", "grid_presence",
    "relative_wealth", "survey_solar_share", "survey_solar_hh_sampled", "predicted_solar_penetration",
    "energy_need_score", "market_gap_score",
]


def clean(value):
    """NaN/inf -> None; numpy scalars -> Python."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return value
    if isinstance(value, (int, float)) or hasattr(value, "item"):
        value = float(value)
        return None if math.isinf(value) else value
    return value


def display_value(column: str, value) -> float | None:
    """Value in the unit shown to users (shares and scores as 0-100)."""
    value = clean(value)
    if value is None:
        return None
    spec = INDICATORS[column]
    shown = value * 100 if spec.get("percent") else value
    return round(shown, spec["decimals"])


def format_value(column: str, value) -> str:
    shown = display_value(column, value)
    if shown is None:
        return "Not available"
    spec = INDICATORS[column]
    if spec["unit"] == "yes/no":
        return "Yes" if shown else "No"
    text = f"{shown:,.{spec['decimals']}f}"
    return f"{text}%" if spec["unit"].startswith("%") else f"{text} {spec['unit']}"


def source_name(key: str, sources: dict) -> str:
    if key == "method":
        return "Market-gap method (services/market_gap.py)"
    if key == "model":
        return "Project model"
    source = sources.get(key, {})
    return source.get("dataset") or source.get("source") or key


def source_date(source: dict) -> str | None:
    """Best available date for a source: data year, OSM snapshot, or ingest window."""
    if source.get("year"):
        return str(source["year"])
    if source.get("osm_snapshot"):
        return f"OSM snapshot {source['osm_snapshot'][:10]}"
    if source.get("requested_end"):
        return f"Ingest {source['requested_end']}"
    return None


def indicator_record(row: pd.Series, column: str, sources: dict) -> dict:
    spec = INDICATORS[column]
    raw = clean(row.get(column)) if column in row.index else None
    source = sources.get(spec["source"], {}) if spec["source"] not in ("method", "model") else {}
    return {
        "key": column,
        "label": spec["label"],
        "value": raw,
        "display_value": display_value(column, raw),
        "formatted": format_value(column, raw),
        "unit": spec["unit"],
        "kind": spec["kind"],
        "kind_label": KIND_LABELS[spec["kind"]],
        "source": source_name(spec["source"], sources),
        "source_year": source_date(source),
        "status": "available" if raw is not None else "missing",
        "description": spec["description"],
    }
