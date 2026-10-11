"""Business logic on top of predictions: statistics, cell details, GOGLA sanity check."""
from __future__ import annotations

import pandas as pd

from ..config import Settings
from ..schemas.schemas import CellDetails, GoglaComparison, GoglaRow, Statistics

GOGLA_CAVEAT = (
    "GOGLA reports aggregated national sales, not pixel-level penetration or households currently "
    "using a product. Treat this as a coarse sanity check only."
)

MODEL_UNAVAILABLE_MSG = (
    "Model predictions are not available for this dataset. "
    "The cells_features.csv does not contain model output columns; "
    "retrain the model on real data to enable this layer."
)


def _opt(row: pd.Series, key: str):
    """Read a numeric field from a row, returning None if missing or NaN."""
    if key not in row.index:
        return None
    v = row[key]
    return None if pd.isna(v) else float(v)


def _opt_bool(row: pd.Series, key: str) -> bool | None:
    if key not in row.index:
        return None
    v = row[key]
    if pd.isna(v):
        return None
    return bool(v)


def interpret(pred: float | None, gap: float | None, threshold: float) -> str:
    if pred is None or gap is None:
        return MODEL_UNAVAILABLE_MSG
    if gap >= threshold:
        return "Potentially underserved area. Further field validation is recommended."
    if pred >= 0.66:
        return "High predicted solar penetration. Market may already be well served; verify locally."
    if pred <= 0.33:
        return ("Low predicted solar penetration, but energy need is limited relative to other areas. "
                "Area requiring further investigation.")
    return "Moderate predicted solar penetration. Area requiring further investigation."


def cell_details(row: pd.Series, code: str, is_demo: bool, threshold: float) -> CellDetails:
    obs = _opt(row, "observed_solar_penetration")
    pred = _opt(row, "predicted_solar_penetration")
    need = _opt(row, "energy_need_score")
    gap = _opt(row, "market_gap_score")
    return CellDetails(
        cell_id=row["cell_id"], country=code,
        latitude=row["lat"], longitude=row["lon"],
        population=row["population_total"],
        population_density=row["population_density"],
        relative_wealth=row["relative_wealth"],
        relative_wealth_observed=_opt_bool(row, "relative_wealth_observed"),
        nighttime_radiance=row["nighttime_radiance"],
        distance_to_grid_km=row["distance_to_grid_km"],
        distance_to_minigrid_km=row["distance_to_minigrid_km"],
        grid_presence=int(row["grid_presence"]),
        solar_resource=row["solar_resource"],
        observed_solar_penetration=obs,
        predicted_solar_penetration=pred,
        energy_need_score=need,
        market_gap_score=gap,
        potentially_underserved=(None if gap is None else bool(gap >= threshold)),
        interpretation=interpret(pred, gap, threshold),
        is_demo=is_demo,
    )


def _has_model_cols(cells: pd.DataFrame) -> bool:
    return "predicted_solar_penetration" in cells.columns and "market_gap_score" in cells.columns


def statistics(cells: pd.DataFrame, metrics: dict | None, settings: Settings, code: str,
               is_demo: bool, threshold: float) -> Statistics:
    pop = cells["population_total"]
    common = dict(
        country=code, is_demo=is_demo, threshold=threshold,
        total_area_km2=float(len(cells) * settings.grid_resolution_km**2),
        total_population=float(pop.sum()),
        n_cells=len(cells),
    )
    if not _has_model_cols(cells):
        return Statistics(**common)
    gap = cells["market_gap_score"] >= threshold
    pred = cells["predicted_solar_penetration"]
    return Statistics(
        **common,
        avg_predicted_penetration=float(pred.mean()),
        population_weighted_penetration=float((pred * pop).sum() / pop.sum()) if pop.sum() > 0 else 0.0,
        potentially_underserved_cells=int(gap.sum()),
        population_in_gap_areas=float(pop[gap].sum()),
        high_penetration_cells=int((pred >= settings.high_penetration_threshold).sum()),
        low_penetration_cells=int((pred <= settings.low_penetration_threshold).sum()),
        model_r2_random=(metrics["random_cv"]["r2"] if metrics else None),
        model_r2_spatial=(metrics["spatial_cv"]["r2"] if metrics else None),
    )


def gogla_comparison(cells: pd.DataFrame, gogla: pd.DataFrame | None, settings: Settings,
                     is_demo: bool) -> GoglaComparison:
    if gogla is None or gogla.empty:
        return GoglaComparison(
            available=False, is_demo=is_demo,
            caveat=GOGLA_CAVEAT + " No gogla.csv found for this country.",
        )
    if not _has_model_cols(cells):
        return GoglaComparison(
            available=False, is_demo=is_demo,
            caveat=GOGLA_CAVEAT + " " + MODEL_UNAVAILABLE_MSG,
        )
    est = float((cells["predicted_solar_penetration"] * cells["population_total"]).sum()
                / settings.avg_household_size)
    total = float(gogla["reported_sales"].sum())
    return GoglaComparison(
        available=True, is_demo=is_demo,
        rows=[GoglaRow(product_category=r.product_category, year=int(r.year),
                       reported_sales=float(r.reported_sales)) for r in gogla.itertuples()],
        total_reported_sales=total,
        model_estimated_solar_households=est,
        ratio_model_to_reported=est / total if total else None,
        caveat=GOGLA_CAVEAT,
    )
