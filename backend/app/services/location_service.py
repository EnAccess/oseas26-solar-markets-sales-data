"""Resolve user-supplied locations against the project's own geography (no external geocoder).

Supported: grid cell IDs (e.g. RW_0412), "lat, lon" coordinates, and district / province names from
the GADM boundaries attached to every cell. Villages, sectors and administrative cells are not in the
backend dataset, so they are reported as unmatched with an explanation instead of being guessed.
"""
from __future__ import annotations

import difflib
import math
import re

import pandas as pd

from ..pipeline.spatial_processing import GridSpec

CELL_ID = re.compile(r"\b([A-Z]{2})_(\d{4})\b", re.IGNORECASE)
COORDS = re.compile(r"(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)")
UNMATCHED_NOTE = (
    "Districts, provinces, sectors, administrative cells and coordinates can be matched. Villages are not in "
    "the backend dataset; choose the Village boundary level on the map instead."
)
PROVINCE_ALIASES = {
    "kigali": "Kigali City", "umujyi wa kigali": "Kigali City", "umujyiwakigali": "Kigali City",
    "east": "Eastern Province", "eastern": "Eastern Province", "iburasirazuba": "Eastern Province",
    "west": "Western Province", "western": "Western Province", "iburengerazuba": "Western Province",
    "north": "Northern Province", "northern": "Northern Province", "amajyaruguru": "Northern Province",
    "south": "Southern Province", "southern": "Southern Province", "amajyepfo": "Southern Province",
}


def _normalise(text: str) -> str:
    text = text.lower().replace("province", "").replace("district", "").replace("city", "")
    return re.sub(r"[^a-z ]", " ", text).strip()


def _names(cells: pd.DataFrame, ids: list[str]) -> str:
    if "place_name" not in cells:
        return ", ".join(ids)
    lookup = cells.set_index("cell_id")["place_name"]
    return "; ".join(str(lookup.get(i, i)) for i in ids)


def cell_at(lat: float, lon: float, cells: pd.DataFrame, spec: GridSpec) -> str | None:
    """ID of the grid cell containing a point, or None when the point is outside the grid."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    row = math.floor((spec.max_lat - lat) / spec.deg)
    col = math.floor((lon - spec.min_lon) / spec.deg)
    match = cells.loc[(cells["row"] == row) & (cells["col"] == col), "cell_id"]
    return None if match.empty else str(match.iloc[0])


def _area_match(name: str, cells: pd.DataFrame, column: str) -> str | None:
    names = sorted(cells[column].dropna().unique())
    lookup = {_normalise(n): n for n in names}
    key = _normalise(name)
    if not key:
        return None
    if column == "province" and key in PROVINCE_ALIASES:
        key = _normalise(PROVINCE_ALIASES[key])
    if key in lookup:
        return lookup[key]
    close = difflib.get_close_matches(key, list(lookup), n=1, cutoff=0.85)
    return lookup[close[0]] if close else None


def resolve(query: str, cells: pd.DataFrame, spec: GridSpec) -> dict:
    """Resolve one location string. Returns {matched, type, name, cell_ids, note}."""
    text = (query or "").strip()
    if not text:
        return {"matched": False, "query": query, "note": "Empty location."}

    ids = [f"{c.upper()}_{n}" for c, n in CELL_ID.findall(text)]
    if ids:
        known = [i for i in dict.fromkeys(ids) if (cells["cell_id"] == i).any()]
        if known:
            return {"matched": True, "query": query, "type": "grid", "name": _names(cells, known), "cell_ids": known}
        return {"matched": False, "query": query, "note": f"No grid cell with ID {', '.join(ids)}."}

    coords = COORDS.search(text)
    if coords:
        lat, lon = float(coords.group(1)), float(coords.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return {"matched": False, "query": query, "note": "Coordinates are out of range."}
        cell = cell_at(lat, lon, cells, spec)
        if cell is None:
            return {"matched": False, "query": query,
                    "note": f"({lat}, {lon}) is outside the Rwanda analysis grid."}
        return {"matched": True, "query": query, "type": "grid", "name": _names(cells, [cell]),
                "cell_ids": [cell]}

    for column, kind in (("district", "district"), ("province", "province"), ("admin_sector", "sector"),
                         ("admin_cell", "cell")):
        if column in cells:
            name = _area_match(text, cells, column)
            if name:
                ids = cells.loc[cells[column] == name, "cell_id"].tolist()
                return {"matched": True, "query": query, "type": kind, "name": name, "cell_ids": ids,
                        "note": f"{len(ids)} analysis cell(s) whose centre lies in {name}."}
    return {"matched": False, "query": query, "note": f"Could not match '{text}'. {UNMATCHED_NOTE}"}


def list_areas(cells: pd.DataFrame) -> dict:
    return {
        "districts": sorted(cells["district"].dropna().unique().tolist()) if "district" in cells else [],
        "provinces": sorted(cells["province"].dropna().unique().tolist()) if "province" in cells else [],
    }
