"""Selected-location reports. One JSON report model feeds the in-app preview, CSV and PDF, so the
numbers in every format come from the same cached cell rows as the map and cell API."""
from __future__ import annotations

import io
from collections import OrderedDict
from datetime import datetime, timezone

import pandas as pd

from ..data_sources import LIMITATIONS
from .indicators import INDICATORS, REPORT_INDICATORS, clean, display_value, indicator_record, source_date
from .market_gap import METHOD, opportunity_score_100
from .prediction_service import UPTAKE_LABELS, drivers, interpret

MAX_REPORT_CELLS = 500
REPORT_SOURCES = ("population", "night_lights", "grid", "survey", "relative_wealth", "districts")
_CACHE: OrderedDict = OrderedDict()
_CACHE_SIZE = 32


class ReportError(ValueError):
    """Invalid report request (empty, too large, unknown cells)."""


def validate_selection(svc, code: str, cell_ids: list[str]) -> list[str]:
    ids = list(dict.fromkeys(cid.strip() for cid in cell_ids if cid and cid.strip()))
    if not ids:
        raise ReportError("Select at least one grid cell to generate a report.")
    if len(ids) > MAX_REPORT_CELLS:
        raise ReportError(f"Reports are limited to {MAX_REPORT_CELLS} cells; {len(ids)} were selected.")
    unknown = svc.unknown_ids(code, ids)
    if unknown:
        raise ReportError(f"Unknown cell IDs: {', '.join(unknown[:10])}" + (" ..." if len(unknown) > 10 else ""))
    return ids


def _cell_entry(row: pd.Series, cells: pd.DataFrame, sources: dict, threshold: float) -> dict:
    factors = drivers(cells, row)
    gap = clean(row.get("market_gap_score"))
    return {
        "cell_id": row["cell_id"],
        "name": clean(row.get("place_name")) or row["cell_id"],
        "admin_cell": clean(row.get("admin_cell")),
        "admin_sector": clean(row.get("admin_sector")),
        "district": clean(row.get("district")),
        "province": clean(row.get("province")),
        "latitude": round(float(row["lat"]), 5),
        "longitude": round(float(row["lon"]), 5),
        "indicators": {c: indicator_record(row, c, sources) for c in REPORT_INDICATORS},
        "opportunity_score": opportunity_score_100(gap),
        "energy_need": opportunity_score_100(clean(row.get("energy_need_score"))),
        "flagged": None if gap is None else bool(gap >= threshold),
        "evidence_level": row.get("evidence_level"),
        "uptake_source": UPTAKE_LABELS.get(row.get("uptake_source"), "unknown"),
        "missing_inputs": [m for m in str(row.get("missing_inputs") or "").split("; ") if m],
        "drivers": factors,
        "interpretation": interpret(row, factors, threshold),
    }


def _summary(rows: pd.DataFrame, res_km: float) -> dict:
    pop = rows["population_total"]
    with_pop = pop.notna()
    scores = rows["market_gap_score"].dropna() * 100
    districts = (rows.dropna(subset=["district"]).groupby("district")
                 .agg(cells=("cell_id", "size"), solar_share=("survey_solar_share", "first"),
                      sampled=("survey_solar_hh_sampled", "first"))
                 .reset_index())
    return {
        "n_cells": len(rows),
        "area_km2": round(len(rows) * res_km**2, 1),
        "population_total": None if not with_pop.any() else round(float(pop.sum())),
        "population_missing_cells": int((~with_pop).sum()),
        "population_density": (None if not with_pop.any()
                               else round(float(pop.sum() / (with_pop.sum() * res_km**2)))),
        "median_radiance": clean(rows["nighttime_radiance"].median()),
        "mean_distance_to_grid_km": clean(round(rows["distance_to_grid_km"].mean(), 1)),
        "cells_with_mapped_grid": int((rows["grid_presence"] == 1).sum()),
        "n_scored": int(len(scores)),
        "score_mean": None if scores.empty else round(float(scores.mean())),
        "score_min": None if scores.empty else round(float(scores.min())),
        "score_max": None if scores.empty else round(float(scores.max())),
        "districts": [
            {"district": r.district, "cells": int(r.cells),
             "solar_share_pct": display_value("survey_solar_share", r.solar_share),
             "sampled_solar_households": clean(r.sampled)}
            for r in districts.itertuples()
        ],
    }


def _narrative(entries: list[dict], summary: dict, national: dict, threshold: float) -> list[str]:
    scored = [e for e in entries if e["opportunity_score"] is not None]
    flagged = sorted((e for e in scored if e["flagged"]), key=lambda e: -e["opportunity_score"])
    missing = [e for e in entries if e["opportunity_score"] is None]
    lines = []
    if flagged:
        top = ", ".join(f"{e['name']} ({e['district'] or 'no district'}, {e['opportunity_score']})"
                        for e in flagged[:5])
        lines.append(f"{len(flagged)} of {len(entries)} selected cells score at or above the priority "
                     f"cut-off ({round(threshold * 100)}/100) and warrant field investigation first: {top}.")
    elif scored:
        lines.append(f"None of the {len(scored)} scored cells reaches the priority cut-off "
                     f"({round(threshold * 100)}/100); they rank below the most underserved parts of Rwanda.")
    if scored:
        lines.append(f"Selection average score {summary['score_mean']}/100 versus a Rwanda median of "
                     f"{national['median']}/100 (range of selection {summary['score_min']}-{summary['score_max']}).")
    if missing:
        lines.append(f"{len(missing)} cell{'s have' if len(missing) != 1 else ' has'} no score because inputs are missing "
                     f"(e.g. {missing[0]['name']}: {', '.join(missing[0]['missing_inputs'])}). "
                     "Missing evidence is not evidence of an underserved market.")
    lines.append("Observed or externally estimated inputs: population (WorldPop 2020), nighttime radiance "
                 "(NASA VNP46A2), mapped grid (OpenStreetMap), district survey ownership (MTF). Derived: "
                 "energy need and the opportunity score. No model prediction is used unless the model was "
                 "trained on real survey labels.")
    lines.append("Before any investment decision: confirm household electrification status and existing "
                 "solar product use in the field, check distributor presence and sales records, and compare "
                 "with national electrification programme (RBF) connection data.")
    return lines


def build_report(svc, code: str, cell_ids: list[str], threshold: float, title: str | None = None) -> dict:
    ids = validate_selection(svc, code, cell_ids)
    key = (code, svc.version(code), tuple(sorted(ids)), round(threshold, 4), title)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    cells = svc.cells(code)
    meta = svc.meta(code)
    sources = meta.get("sources", {})
    # Keep the original row labels: drivers() looks rows up in the national component table.
    position = pd.Series(cells.index, index=cells["cell_id"])
    rows = cells.loc[position.loc[ids].to_numpy()]
    entries = [_cell_entry(row, cells, sources, threshold) for _, row in rows.iterrows()]
    summary = _summary(rows, svc.spec(code).res_km)
    national_scores = cells["market_gap_score"].dropna() * 100
    national = {"median": round(float(national_scores.median())) if len(national_scores) else None,
                "p80": round(float(national_scores.quantile(0.8))) if len(national_scores) else None,
                "n_scored": int(len(national_scores))}
    report = {
        "title": title or f"Solar market reality: {len(ids)} selected location{'s' if len(ids) != 1 else ''}",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "country": meta.get("country_name", code),
        "dataset_built_at": meta.get("built_at"),
        "threshold_score": round(threshold * 100),
        "cells": entries,
        "summary": summary,
        "national": national,
        "method": METHOD,
        "model_status": svc.model_info(code),
        "sources": [
            {"key": k, "name": sources.get(k, {}).get("dataset") or sources.get(k, {}).get("source") or k,
             "status": sources.get(k, {}).get("status", "missing"), "date": source_date(sources.get(k, {})),
             "licence": sources.get(k, {}).get("licence"), "note": sources.get(k, {}).get("note")}
            for k in REPORT_SOURCES
        ],
        "interpretation": [],
        "limitations": LIMITATIONS,
    }
    report["interpretation"] = _narrative(entries, summary, national, threshold)
    _CACHE[key] = report
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return report


CSV_COLUMNS = ["population_total", "population_density", "nighttime_radiance", "distance_to_grid_km",
               "grid_presence", "relative_wealth", "survey_solar_share", "survey_solar_hh_sampled",
               "energy_need_score", "market_gap_score"]


def report_csv(report: dict) -> str:
    records = []
    for e in report["cells"]:
        rec = {"place": e["name"], "cell": e["admin_cell"], "sector": e["admin_sector"],
               "district": e["district"], "province": e["province"],
               "latitude": e["latitude"], "longitude": e["longitude"]}
        for col in CSV_COLUMNS:
            spec = INDICATORS[col]
            rec[f"{spec['label']} ({spec['unit']})"] = e["indicators"][col]["display_value"]
        rec["Solar uptake evidence"] = e["uptake_source"]
        rec["Evidence level"] = e["evidence_level"]
        rec["Missing inputs"] = "; ".join(e["missing_inputs"])
        rec["analysis_cell_id"] = e["cell_id"]  # last column: stable key for joining with the dataset
        records.append(rec)
    return pd.DataFrame(records).to_csv(index=False)
