from collections import defaultdict
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import UNIT
from ..core import catalog
from ..core.sampling import LAYER, sample_area, sample_points

app = FastAPI(title="Nightlights API", version="0.4.0",
              description="VIIRS nighttime-light features streamed directly from NASA LAADS.")

CAVEAT = ("Nightlights cannot detect solar home systems or pico-lanterns: dark does not "
          "mean unserved. Use as a model feature, not as a measure of penetration.")
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
NO_FILE = "NASA has no file for this tile/date yet"


class Point(BaseModel):
    id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class BatchRequest(BaseModel):
    points: List[Point] = Field(min_length=1, max_length=5000)
    radius_km: float = Field(1.0, ge=0, le=25)
    threshold: float = Field(1.0, ge=0)
    date: Optional[str] = Field(None, pattern=DATE_RE, description="YYYY-MM-DD; default = newest available")


# CHANGE: new Pydantic models for /features and /features/batch.
# These are separate from Point/BatchRequest so the ML contract can evolve
# without breaking anyone already using /sample/batch.
class FeaturePoint(BaseModel):
    id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class FeatureBatchRequest(BaseModel):
    locations: List[FeaturePoint] = Field(min_length=1, max_length=5000)
    search_radius_km: float = Field(1.0, ge=0, le=25)
    brightness_threshold: float = Field(1.0, ge=0)
    date: Optional[str] = Field(None, pattern=DATE_RE,
                                description="YYYY-MM-DD; default = newest available")


def _source(item):
    return {"file": item["file"], "date": item["date"], "tile": item["tile"],
            "product": item["product"], "layer": LAYER, "unit": UNIT,
            "access": "streamed from NASA LAADS (no local copy)"}


# CHANGE: helpers used by /nightlights and /features only. Existing endpoints
# do not call these and are unaffected.
def _warnings() -> list:
    return [
        "Satellite nightlight data cannot see small solar home systems or solar lanterns. "
        "A dark place is not necessarily an unelectrified place.",
        "Use this as one input to a model, not as a direct measure of how many people "
        "have electricity.",
        "Daily data has gaps from clouds. Prefer monthly or annual composites for modelling.",
    ]


def _english_summary(mean_value: Optional[float], valid_share: float) -> str:
    if mean_value is None or valid_share == 0:
        return ("No usable pixels in this area on this date — likely cloud cover "
                "or a fill region. Try a nearby date.")
    if mean_value < 1:
        return "This area is essentially dark on this date."
    if mean_value < 10:
        return "This area has faint nighttime lighting — small settlements or rural roads."
    if mean_value < 100:
        return "This area is moderately lit — towns or suburban areas."
    return "This area is brightly lit — typical of a well-lit urban area."


def _features_row(item: dict, latitude: float, longitude: float,
                  stats: dict, radius_km: float) -> dict:
    """Flat, short-keyed row for the ML pipeline. Prefix is `nightlight_` so
    merges with WorldPop / RWI / Gridfinder do not collide."""
    return {
        "latitude": latitude,
        "longitude": longitude,
        "nightlight_mean": stats.get("mean"),
        "nightlight_median": stats.get("median"),
        "nightlight_max": stats.get("max"),
        "nightlight_lit_fraction": stats.get("lit_frac"),
        "nightlight_valid_fraction": stats.get("valid_frac"),
        "nightlight_pixel_count": stats.get("n_pixels"),
        "nightlight_radius_km": radius_km,
        "nightlight_source_file": item["file"],
        "nightlight_date_used": item["date"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/resolve")
def resolve(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
            date: Optional[str] = Query(None, pattern=DATE_RE, description="YYYY-MM-DD")):
    """Which NASA file would answer this point?"""
    try:
        item = catalog.resolve(lat, lon, date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid date: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")
    if item is None:
        return {"found": False, "reason": NO_FILE}
    return {"found": True, "source": _source(item), "size_mb": item["size_mb"]}


@app.get("/sample")
def sample(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
           radius_km: float = Query(1.0, ge=0, le=25), threshold: float = Query(1.0, ge=0),
           date: Optional[str] = Query(None, pattern=DATE_RE, description="YYYY-MM-DD")):
    """Light statistics in a circle around one point."""
    out = {"lat": lat, "lon": lon, "radius_km": radius_km, "caveat": CAVEAT}
    try:
        item = catalog.resolve(lat, lon, date)
        if item is None:
            return {**out, "found": False, "reason": NO_FILE}
        stats = sample_points(item, [(lat, lon)], radius_km, threshold)[0]
        return {**out, "found": True, "source": _source(item), "stats": stats}
    except Exception as e:
        return {**out, "found": False, "reason": f"{type(e).__name__}: {e}"}


@app.post("/sample/batch")
def sample_batch(req: BatchRequest):
    """Light statistics for many points; one remote open per tile."""
    results, groups = {}, defaultdict(list)
    for i, p in enumerate(req.points):
        try:
            item = catalog.resolve(p.lat, p.lon, req.date)
        except Exception as e:
            results[i] = {"found": False, "reason": f"{type(e).__name__}: {e}"}
            continue
        if item is None:
            results[i] = {"found": False, "reason": NO_FILE}
        else:
            groups[item["file"]].append((i, item))

    for entries in groups.values():
        item = entries[0][1]
        try:
            pts = [(req.points[i].lat, req.points[i].lon) for i, _ in entries]
            for (i, _), stats in zip(entries, sample_points(item, pts, req.radius_km, req.threshold)):
                results[i] = {"found": True, "source": _source(item), "stats": stats}
        except Exception as e:
            for i, _ in entries:
                results[i] = {"found": False, "reason": f"{type(e).__name__}: {e}"}

    return {"radius_km": req.radius_km, "caveat": CAVEAT,
            "results": [{"id": p.id, "lat": p.lat, "lon": p.lon, **results[i]}
                        for i, p in enumerate(req.points)]}


@app.get("/area")
def area(west: float = Query(..., ge=-180, le=180), south: float = Query(..., ge=-90, le=90),
         east: float = Query(..., ge=-180, le=180), north: float = Query(..., ge=-90, le=90),
         max_pixels: int = Query(2500, ge=100, le=20000),
         date: Optional[str] = Query(None, pattern=DATE_RE, description="YYYY-MM-DD")):
    """Pixel grid of nighttime light for a bounding box (must stay inside one 10° tile)."""
    if east <= west or north <= south:
        raise HTTPException(status_code=422, detail="Need east > west and north > south")
    out = {"caveat": CAVEAT}
    try:
        item = catalog.resolve((south + north) / 2, (west + east) / 2, date)
        if item is None:
            return {**out, "found": False, "reason": NO_FILE}
        b = item["bounds"]
        if west < b["west"] or east > b["east"] or south < b["south"] or north > b["north"]:
            raise HTTPException(
                status_code=422,
                detail=f"Area must stay inside tile {item['tile']}: "
                       f"lon {b['west']}..{b['east']}, lat {b['south']}..{b['north']}")
        return {**out, "found": True, "source": _source(item),
                "grid": sample_area(item, west, south, east, north, max_pixels)}
    except HTTPException:
        raise
    except Exception as e:
        return {**out, "found": False, "reason": f"{type(e).__name__}: {e}"}


# ============================================================================
# CHANGE: /nightlights and /features, appended below. The five endpoints above
# are untouched and continue to work exactly as before.
# ============================================================================


@app.get("/nightlights")
def nightlights(
    latitude: float = Query(..., ge=-90, le=90, description="Latitude in decimal degrees"),
    longitude: float = Query(..., ge=-180, le=180, description="Longitude in decimal degrees"),
    search_radius_km: float = Query(1.0, ge=0, le=25,
                                    description="Radius of the circle to average over"),
    date: Optional[str] = Query(None, pattern=DATE_RE,
                                description="YYYY-MM-DD; default = newest available"),
):
    """Human-readable nighttime light summary for one location."""
    out = {
        "location": {"latitude": latitude, "longitude": longitude,
                     "search_radius_km": search_radius_km},
        "warnings": _warnings(),
    }
    try:
        item = catalog.resolve(latitude, longitude, date)
        if item is None:
            return {**out, "found": False, "reason": NO_FILE}
        stats = sample_points(item, [(latitude, longitude)], search_radius_km, 1.0)[0]
        out["location"]["tile_id"] = item["tile"]
        out["date"] = {"requested": date, "actually_used": item["date"]}
        out["source"] = {
            "satellite": "Suomi-NPP",
            "instrument": "VIIRS",
            "nasa_product": item["product"],
            "nasa_filename": item["file"],
            "data_layer": "Gap-Filled, BRDF-Corrected Nighttime Lights",
            "unit_of_measurement": "nanowatts per square centimeter per steradian",
            "how_it_was_retrieved": "Streamed live from NASA LAADS, not stored locally",
        }
        out["nighttime_light"] = {
            "average_brightness": stats.get("mean"),
            "median_brightness": stats.get("median"),
            "brightest_pixel": stats.get("max"),
            "total_pixels_checked": stats.get("n_pixels"),
            "usable_pixel_count": None if stats.get("valid_frac") is None
                                  else round(stats["valid_frac"] * stats["n_pixels"]),
            "share_of_pixels_that_were_usable": stats.get("valid_frac"),
            "share_of_pixels_brighter_than_one_unit": stats.get("lit_frac"),
            "circle_reached_a_tile_boundary": stats.get("clipped"),
            "plain_english_summary": _english_summary(stats.get("mean"),
                                                      stats.get("valid_frac") or 0),
        }
        return {**out, "found": True}
    except Exception as e:
        return {**out, "found": False, "reason": f"{type(e).__name__}: {e}"}


@app.get("/features")
def features(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    search_radius_km: float = Query(1.0, ge=0, le=25),
    brightness_threshold: float = Query(1.0, ge=0),
    date: Optional[str] = Query(None, pattern=DATE_RE, description="YYYY-MM-DD"),
):
    """One flat row of model-ready features for a single location.
    Keys are short and prefixed `nightlight_` so they merge cleanly with
    WorldPop, Meta RWI, and Gridfinder features in a pandas/GeoPandas frame.
    """
    try:
        item = catalog.resolve(latitude, longitude, date)
        if item is None:
            return {"found": False, "reason": NO_FILE,
                    "latitude": latitude, "longitude": longitude}
        stats = sample_points(item, [(latitude, longitude)],
                              search_radius_km, brightness_threshold)[0]
        row = _features_row(item, latitude, longitude, stats, search_radius_km)
        return {"found": True, **row}
    except Exception as e:
        return {"found": False, "reason": f"{type(e).__name__}: {e}",
                "latitude": latitude, "longitude": longitude}


@app.post("/features/batch")
def features_batch(req: FeatureBatchRequest):
    """Model-ready features for many locations. Groups by tile so each NASA
    file is opened once. Returns rows in the same order as the request."""
    results, groups = {}, defaultdict(list)
    for i, p in enumerate(req.locations):
        try:
            item = catalog.resolve(p.latitude, p.longitude, req.date)
        except Exception as e:
            results[i] = {"found": False, "reason": f"{type(e).__name__}: {e}"}
            continue
        if item is None:
            results[i] = {"found": False, "reason": NO_FILE}
        else:
            groups[item["file"]].append((i, item))

    for entries in groups.values():
        item = entries[0][1]
        try:
            pts = [(req.locations[i].latitude, req.locations[i].longitude) for i, _ in entries]
            for (i, _), stats in zip(entries, sample_points(item, pts, req.search_radius_km,
                                                            req.brightness_threshold)):
                results[i] = _features_row(item, req.locations[i].latitude,
                                           req.locations[i].longitude,
                                           stats, req.search_radius_km)
        except Exception as e:
            for i, _ in entries:
                results[i] = {"found": False, "reason": f"{type(e).__name__}: {e}"}

    return {
        "rows": [{"id": p.id, **results[i]} for i, p in enumerate(req.locations)],
        "caveat": CAVEAT,
    }