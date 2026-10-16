from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class CountryInfo(BaseModel):
    code: str
    name: str
    center: tuple[float, float]
    zoom: int
    bbox: tuple[float, float, float, float]
    ready: bool = Field(description="True once a dataset exists for this country")


class AppMeta(BaseModel):
    country: str
    country_name: str
    is_demo: bool
    grid_resolution_km: float
    n_cells: int
    n_labelled_cells: int
    bounds: list[float]
    selected_model: str
    features: list[str]
    underserved_threshold: float
    disclaimer: str
    training_labels: str | None = None
    built_at: str | None = None
    sources: dict[str, dict[str, Any]] = {}
    assumptions: dict[str, Any] = {}
    model_status: dict[str, Any] = {}
    method: dict[str, str] = {}


class LayerInfo(BaseModel):
    id: str
    name: str
    description: str
    unit: str
    selector: bool = True
    kind: str | None = None
    source: str | None = None


class Indicator(BaseModel):
    key: str
    label: str
    value: float | None = None
    display_value: float | None = None
    formatted: str
    unit: str
    kind: str
    kind_label: str
    source: str
    source_year: str | None = None
    status: str
    description: str


class Driver(BaseModel):
    factor: str
    value: float | None = None
    note: str


class CellDetails(BaseModel):
    cell_id: str
    place_name: str | None = None
    admin_cell: str | None = None
    admin_sector: str | None = None
    country: str
    latitude: float
    longitude: float
    district: str | None = None
    province: str | None = None
    population: float | None = None
    population_density: float | None = None
    relative_wealth: float | None = None
    relative_wealth_observed: bool | None = None
    nighttime_radiance: float | None = None
    distance_to_grid_km: float | None = None
    grid_presence: int | None = None
    survey_solar_share: float | None = None
    survey_solar_hh_sampled: float | None = None
    # Model-derived: None unless the model was trained on real labels for this dataset.
    predicted_solar_penetration: float | None = None
    observed_solar_penetration: float | None = None
    energy_need_score: float | None = None
    solar_uptake: float | None = None
    uptake_source: str | None = None
    uptake_source_label: str | None = None
    market_gap_score: float | None = Field(None, description="0-1 relative opportunity score")
    opportunity_score: int | None = Field(None, description="market_gap_score as an integer 0-100")
    evidence_level: str | None = None
    missing_inputs: list[str] = []
    potentially_underserved: bool | None = None
    drivers: list[Driver] = []
    indicators: list[Indicator] = []
    model_status: dict[str, Any] = {}
    interpretation: str
    is_demo: bool


class MetricSet(BaseModel):
    mae: float | None = None
    rmse: float | None = None
    r2: float | None = None
    n_folds: int | None = None
    n_evaluated: int | None = None
    n_blocks: int | None = None
    block_km: float | None = None
    buffer_km: float | None = None


class ModelResult(BaseModel):
    random_cv: MetricSet
    spatial_cv: MetricSet


class ModelPerformance(BaseModel):
    country: str
    is_demo: bool
    selected_model: str
    selection_criterion: str
    n_samples: int
    features: list[str]
    trained_at: str
    random_cv: MetricSet
    spatial_cv: MetricSet
    models: dict[str, ModelResult]
    note: str
    usable: bool = False


class FeatureImportanceItem(BaseModel):
    feature: str
    label: str
    importance: float


class FeatureImportanceResponse(BaseModel):
    title: str = "Model feature importance"
    selected_model: str
    is_demo: bool
    importance: list[FeatureImportanceItem]
    by_model: dict[str, list[FeatureImportanceItem]]
    warning: str


class Statistics(BaseModel):
    country: str
    is_demo: bool
    threshold: float
    total_area_km2: float
    total_population: float
    n_cells: int
    n_scored_cells: int | None = None
    avg_predicted_penetration: float | None = None
    population_weighted_penetration: float | None = None
    potentially_underserved_cells: int | None = None
    population_in_gap_areas: float | None = None
    high_penetration_cells: int | None = None
    low_penetration_cells: int | None = None
    model_r2_random: float | None = None
    model_r2_spatial: float | None = None


class DataSource(BaseModel):
    id: str
    name: str
    description: str
    resolution: str
    role: str
    limitations: str
    status: str = Field(description="real | missing | synthetic")
    date: str | None = None
    licence: str | None = None
    file: str | None = None
    retrieved_at: str | None = None
    note: str | None = None


class GoglaRow(BaseModel):
    product_category: str
    year: int
    reported_sales: float


class GoglaComparison(BaseModel):
    available: bool
    is_demo: bool
    rows: list[GoglaRow] = []
    total_reported_sales: float | None = None
    model_estimated_solar_households: float | None = None
    ratio_model_to_reported: float | None = None
    caveat: str
