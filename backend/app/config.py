"""Central configuration. Every value can be overridden through environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]

# Human-readable names for model features (used by the API and the UI).
FEATURE_LABELS: dict[str, str] = {
    "population_density": "Population density",
    "nighttime_radiance": "Nighttime radiance",
    "relative_wealth": "Relative wealth",
    "solar_resource": "Solar resource (GHI)",
    "distance_to_grid_km": "Distance to grid",
    "distance_to_minigrid_km": "Distance to minigrid",
    "grid_presence": "Grid presence in cell",
    "minigrid_presence": "Minigrid presence in cell",
    "settlement_density": "Settlement density (3x3 neighbourhood)",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    backend_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    demo_mode: bool = False
    default_country: str = "RW"
    grid_resolution_km: float = 5.0

    features: str = (
        "population_density,nighttime_radiance,relative_wealth,solar_resource,"
        "distance_to_grid_km,distance_to_minigrid_km,grid_presence,minigrid_presence,"
        "settlement_density"
    )
    cv_folds: int = 5
    spatial_block_km: float = 30.0
    spatial_buffer_km: float = 10.0
    random_seed: int = 42
    min_training_cells: int = 30

    # Potential Market Gap Indicator
    # Relative cut-off on the 0-1 market_gap_score (~top fifth of scored Rwandan cells in the current build).
    underserved_threshold: float = 0.55
    high_penetration_threshold: float = 0.66
    low_penetration_threshold: float = 0.33
    need_w_population: float = 0.4
    need_w_grid_distance: float = 0.4
    need_w_darkness: float = 0.2
    avg_household_size: float = 4.3

    # AI assistant (backend only; the key never reaches the browser)
    anthropic_api_key: str | None = None
    assistant_model: str = "gemini-3.8-flash"
    assistant_timeout_s: float = 60.0

    @property
    def feature_list(self) -> list[str]:
        return [f.strip() for f in self.features.split(",") if f.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ---- per-country directories -------------------------------------------------
    def raw_path(self, code: str) -> Path:
        return BASE_DIR / "data" / "raw" / code

    def processed_path(self, code: str) -> Path:
        return _ensure(BASE_DIR / "data" / "processed" / code)

    def models_path(self, code: str) -> Path:
        return _ensure(BASE_DIR / "models" / code)

    def outputs_path(self, code: str) -> Path:
        return _ensure(BASE_DIR / "outputs" / code)


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
