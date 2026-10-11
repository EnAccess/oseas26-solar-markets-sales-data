from __future__ import annotations

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


class LayerInfo(BaseModel):
    id: str
    name: str
    description: str
    unit: str


class CellDetails(BaseModel):
    cell_id: str
    country: str
    latitude: float
    longitude: float
    # Real (this migration)
    population: float
    population_density: float
    relative_wealth: float
    relative_wealth_observed: bool | None = None
    # Teammates' inputs (currently fallback)
    nighttime_radiance: float
    distance_to_grid_km: float
    distance_to_minigrid_km: float
    grid_presence: int
    solar_resource: float
    # Model-derived (None until a model is trained on real data)
    observed_solar_penetration: float | None = None
    predicted_solar_penetration: float | None = None
    energy_need_score: float | None = None
    market_gap_score: float | None = None
    potentially_underserved: bool | None = None
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
    year: str
    resolution: str
    role: str
    limitations: str
    demo_substitute: str


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
