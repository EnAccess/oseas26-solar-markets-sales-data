"""Business logic on top of the scored cell table: cell evidence, interpretation, statistics, GOGLA check."""
from __future__ import annotations

import pandas as pd

from ..config import Settings
from ..schemas.schemas import CellDetails, GoglaComparison, GoglaRow, Statistics
from .indicators import REPORT_INDICATORS, clean, indicator_record
from .market_gap import UPTAKE_MODEL, UPTAKE_SURVEY, need_components, opportunity_score_100

GOGLA_CAVEAT = (
    "GOGLA reports aggregated national sales, not pixel-level penetration or households currently "
    "using a product. Treat this as a coarse sanity check only."
)
UPTAKE_LABELS = {
    UPTAKE_MODEL: "model prediction (trained on real survey labels)",
    UPTAKE_SURVEY: "district survey estimate (MTF)",
    "unknown": "no solar uptake evidence",
}


def drivers(cells: pd.DataFrame, row: pd.Series) -> list[dict]:
    """Normalised contribution of each input for one cell (0-1, higher = raises the score)."""
    parts = need_components(cells).loc[row.name]
    uptake = clean(row.get("solar_uptake"))
    items = [
        ("Population density", parts["need_population"], "Scaled log population density within Rwanda."),
        ("Distance to mapped grid", parts["need_remoteness"], "Scaled distance to the nearest mapped line."),
        ("Darkness at night", parts["need_darkness"], "1 - scaled log radiance. A grid proxy, not a solar measure."),
        ("Lack of solar uptake evidence", None if uptake is None else 1 - uptake,
         "1 - solar uptake (survey or model). Missing when no uptake evidence exists."),
    ]
    return [{"factor": f, "value": None if clean(v) is None else round(float(v), 3), "note": n}
            for f, v, n in items]


def interpret(row: pd.Series, factors: list[dict], threshold: float) -> str:
    gap = clean(row.get("market_gap_score"))
    if gap is None:
        missing = row.get("missing_inputs") or "required inputs"
        return (f"No opportunity score: missing {missing}. Treat this location as needing field "
                "investigation; missing evidence is not evidence of an underserved market.")
    ranked = sorted((f for f in factors if f["value"] is not None), key=lambda f: f["value"], reverse=True)
    strong = [f["factor"].lower() for f in ranked if f["value"] >= 0.6][:3]
    weak = [f["factor"].lower() for f in ranked if f["value"] <= 0.3][:2]
    text = ("Higher relative priority for field investigation" if gap >= threshold
            else "Lower relative priority compared with other cells in Rwanda")
    if strong:
        text += f", mainly because of {', '.join(strong)}"
    if weak:
        text += f"; held back by low {', '.join(weak)}"
    text += "."
    darkness = next(f["value"] for f in factors if f["factor"] == "Darkness at night")
    share = clean(row.get("survey_solar_share"))
    if darkness is not None and darkness >= 0.7 and share is not None and share >= 0.15:
        text += (" The cell is dark at night, yet the district survey reports solar ownership: darkness "
                 "here should not be read as an absence of solar.")
    if row.get("evidence_level") == "limited":
        text += " Survey evidence for this district rests on fewer than 10 sampled solar households."
    return text + " This is a screening result, not proof of commercial viability."


def cell_details(row: pd.Series, cells: pd.DataFrame, code: str, meta: dict, model_info: dict,
                 threshold: float) -> CellDetails:
    sources = meta.get("sources", {})
    factors = drivers(cells, row)
    gap = clean(row.get("market_gap_score"))
    return CellDetails(
        cell_id=row["cell_id"], country=code,
        place_name=clean(row.get("place_name")), admin_cell=clean(row.get("admin_cell")),
        admin_sector=clean(row.get("admin_sector")),
        latitude=float(row["lat"]), longitude=float(row["lon"]),
        district=clean(row.get("district")), province=clean(row.get("province")),
        population=clean(row.get("population_total")),
        population_density=clean(row.get("population_density")),
        relative_wealth=clean(row.get("relative_wealth")),
        relative_wealth_observed=bool(row.get("relative_wealth_observed")) if "relative_wealth_observed" in row else None,
        nighttime_radiance=clean(row.get("nighttime_radiance")),
        distance_to_grid_km=clean(row.get("distance_to_grid_km")),
        grid_presence=None if clean(row.get("grid_presence")) is None else int(row["grid_presence"]),
        survey_solar_share=clean(row.get("survey_solar_share")),
        survey_solar_hh_sampled=clean(row.get("survey_solar_hh_sampled")),
        predicted_solar_penetration=clean(row.get("predicted_solar_penetration")),
        observed_solar_penetration=clean(row.get("observed_solar_penetration")),
        energy_need_score=clean(row.get("energy_need_score")),
        solar_uptake=clean(row.get("solar_uptake")),
        uptake_source=row.get("uptake_source"),
        uptake_source_label=UPTAKE_LABELS.get(row.get("uptake_source"), "unknown"),
        market_gap_score=gap,
        opportunity_score=opportunity_score_100(gap),
        evidence_level=row.get("evidence_level"),
        missing_inputs=[m for m in str(row.get("missing_inputs") or "").split("; ") if m],
        potentially_underserved=None if gap is None else bool(gap >= threshold),
        drivers=factors,
        indicators=[indicator_record(row, c, sources) for c in REPORT_INDICATORS],
        model_status=model_info,
        interpretation=interpret(row, factors, threshold),
        is_demo=bool(meta.get("is_demo")),
    )


def statistics(cells: pd.DataFrame, metrics: dict | None, model_info: dict, settings: Settings, code: str,
               is_demo: bool, threshold: float) -> Statistics:
    pop = cells["population_total"]
    gap = cells["market_gap_score"]
    flagged = gap >= threshold
    model_ok = model_info.get("usable") and "predicted_solar_penetration" in cells
    pred = cells["predicted_solar_penetration"] if model_ok else None
    return Statistics(
        country=code, is_demo=is_demo, threshold=threshold,
        total_area_km2=float(len(cells) * settings.grid_resolution_km**2),
        total_population=float(pop.sum()),
        n_cells=len(cells),
        n_scored_cells=int(gap.notna().sum()),
        potentially_underserved_cells=int(flagged.sum()),
        population_in_gap_areas=float(pop[flagged].sum()),
        avg_predicted_penetration=None if pred is None else float(pred.mean()),
        population_weighted_penetration=(None if pred is None or pop.sum() <= 0
                                         else float((pred * pop).sum() / pop[pred.notna()].sum())),
        high_penetration_cells=None if pred is None else int((pred >= settings.high_penetration_threshold).sum()),
        low_penetration_cells=None if pred is None else int((pred <= settings.low_penetration_threshold).sum()),
        model_r2_random=metrics["random_cv"]["r2"] if metrics and model_ok else None,
        model_r2_spatial=metrics["spatial_cv"]["r2"] if metrics and model_ok else None,
    )


def gogla_comparison(cells: pd.DataFrame, gogla: pd.DataFrame | None, model_info: dict, settings: Settings,
                     is_demo: bool) -> GoglaComparison:
    if gogla is None or gogla.empty:
        return GoglaComparison(available=False, is_demo=is_demo,
                               caveat=GOGLA_CAVEAT + " No GOGLA table is available for this country.")
    if not model_info.get("usable") or "predicted_solar_penetration" not in cells:
        return GoglaComparison(available=False, is_demo=is_demo,
                               caveat=GOGLA_CAVEAT + " " + model_info.get("reason", ""))
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
