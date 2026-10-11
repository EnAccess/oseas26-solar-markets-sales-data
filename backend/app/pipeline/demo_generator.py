"""Generate synthetic demo features alongside NASA-sourced nightlight radiance."""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from ..config import Settings
from ..countries import Country
from .feature_engineering import distance_to_geoms_km
from .ingestion import RawLayers
from .spatial_processing import KM_PER_DEG, GridSpec
from nightlights.core.sampling import sample_radiance

logger = logging.getLogger(__name__)


def _km_dist(lon, lat, lon0, lat0):
    dx = (lon - lon0) * KM_PER_DEG * np.cos(np.radians(lat0))
    dy = (lat - lat0) * KM_PER_DEG
    return np.hypot(dx, dy)


def generate_demo(settings: Settings, country: Country, grid: gpd.GeoDataFrame, spec: GridSpec) -> RawLayers:
    logger.warning("DEMO MODE: generating SYNTHETIC data for %s", country.name)
    rng = np.random.default_rng(settings.random_seed)
    lon, lat = grid["lon"].to_numpy(), grid["lat"].to_numpy()
    n = len(grid)

    # --- population: urban peaks over a noisy rural base -----------------------------
    pop = 300 * rng.lognormal(0, 0.35, n)
    for _, cx, cy, w in country.cities:
        sigma = 8 + 14 * w
        pop += 2200 * w * np.exp(-(_km_dist(lon, lat, cx, cy) ** 2) / (2 * sigma**2))

    # --- grid and minigrids ------------------------------------------------------------
    capital = country.cities[0]
    lines = []
    for _, cx, cy, _w in country.cities[1:]:
        mid = ((capital[1] + cx) / 2 + rng.normal(0, 0.05), (capital[2] + cy) / 2 + rng.normal(0, 0.05))
        lines.append(LineString([(capital[1], capital[2]), mid, (cx, cy)]))
    for _, cx, cy, _w in country.cities:  # short rural feeders
        for _ in range(2):
            ang, length = rng.uniform(0, 2 * np.pi), rng.uniform(10, 28) / KM_PER_DEG
            lines.append(LineString([(cx, cy), (cx + length * np.cos(ang), cy + length * np.sin(ang))]))
    grid_lines = gpd.GeoDataFrame({"geometry": lines}, crs="EPSG:4326")
    dist_grid = distance_to_geoms_km(grid, grid_lines, country.utm_epsg)

    remote = np.where(dist_grid > 8)[0]
    pool = remote if len(remote) >= 12 else np.arange(n)
    chosen = rng.choice(pool, size=min(12, len(pool)), replace=False)
    minigrids = gpd.GeoDataFrame({"geometry": [Point(lon[i], lat[i]) for i in chosen]}, crs="EPSG:4326")
    minigrid_flag = np.zeros(n)
    minigrid_flag[chosen] = 1

    # --- nighttime lights, wealth, solar resource -------------------------------------
    near_grid = np.exp(-dist_grid / 10)
    night = sample_radiance(list(zip(lat, lon)))
    wealth = -0.7 + 0.9 * np.tanh(pop / 900) + 0.5 * near_grid + rng.normal(0, 0.2, n)
    solar = 5.0 + 0.3 * (lon - lon.min()) / (lon.max() - lon.min()) + rng.normal(0, 0.08, n)

    # --- hidden "truth" used only to create fake survey labels --------------------------
    sig = 1 / (1 + np.exp(-2 * wealth))
    pop_term = np.clip(np.log1p(pop) / np.log1p(1500), 0, 1)
    truth = 0.02 + 0.85 * sig * (1 - 0.85 * near_grid) + 0.25 * (1 - near_grid) * pop_term + 0.25 * (solar - 5.0)
    for _ in range(6):  # unobserved regional effects -> makes spatial CV harder than random CV
        cx, cy = rng.uniform(lon.min(), lon.max()), rng.uniform(lat.min(), lat.max())
        truth += rng.normal(0, 0.10) * np.exp(-(_km_dist(lon, lat, cx, cy) ** 2) / (2 * 22**2))
    truth = np.clip(truth + rng.normal(0, 0.04, n), 0.0, 1.0)

    # --- synthetic survey clusters (GPS-displaced like real DHS points) -----------------
    idx = rng.choice(n, size=int(n * 0.35), replace=False)
    hh = rng.integers(25, 41, len(idx))
    solar_share = rng.binomial(hh, truth[idx]) / hh
    grid_share = np.clip(near_grid[idx] * 0.9 + rng.normal(0, 0.05, len(idx)), 0, 1)
    jitter = rng.normal(0, 0.012, (len(idx), 2))
    surveys = pd.DataFrame(
        {
            "cluster_id": [f"DEMO_{i:04d}" for i in range(len(idx))],
            "latitude": lat[idx] + rng.uniform(-0.4, 0.4, len(idx)) * spec.deg + jitter[:, 0],
            "longitude": lon[idx] + rng.uniform(-0.4, 0.4, len(idx)) * spec.deg + jitter[:, 1],
            "solar_ownership": solar_share,
            "electricity_access": grid_share,
            "n_households": hh,
        }
    )

    # --- synthetic GOGLA-style national control total ----------------------------------
    households = pop * spec.res_km**2 / settings.avg_household_size
    national = float((truth * households).sum())
    factor = rng.uniform(0.8, 1.1)
    gogla = pd.DataFrame(
        {
            "country": [country.name] * 2,
            "reported_sales": [round(national * factor * 0.35), round(national * factor * 0.65)],
            "product_category": ["solar_home_system", "pico_solar"],
            "year": [2023, 2023],
        }
    )
    return RawLayers(
        population_density=pop,
        nighttime_radiance=night,
        relative_wealth=wealth,
        solar_resource=solar,
        grid_lines=grid_lines,
        minigrids=minigrids,
        surveys=surveys,
        gogla=gogla,
        is_demo=True,
        sources={
            "all": "Synthetic demo features generated by pipeline/demo_generator.py; nighttime_radiance is sourced from NASA LAADS.",
            "nighttime_radiance": "NASA Black Marble VNP46A2, sampled from LAADS",
        },
    )
