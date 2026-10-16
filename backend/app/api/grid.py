"""Grid checks from the processed infrastructure snapshot."""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from shapely.geometry import Point, shape
import shapely

from ..services.data_service import DataService
from .deps import country_code, service_dep

router = APIRouter()


@router.get("/grid/check", tags=["map"], summary="Check processed mapped grid infrastructure")
async def grid_check(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10, ge=1, le=50),
    code: str = Depends(country_code),
    svc: DataService = Depends(service_dep),
) -> dict:
    local = svc.infrastructure(code) or {"type": "FeatureCollection", "features": []}
    km_per_degree = 111.32
    longitude_scale = km_per_degree * max(abs(math.cos(math.radians(lat))), 1e-6)

    def project(coords):  # lon/lat -> local km offsets from the clicked point
        return (coords - [lon, lat]) * [longitude_scale, km_per_degree]

    nearby = []
    for feature in local.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        projected = shapely.transform(shape(geometry), project)
        if projected.distance(Point(0, 0)) <= radius_km:
            nearby.append(feature)
    features = nearby
    tags = [feature.get("properties", {}) for feature in features]
    voltages = sorted({int(value) / 1000 for tag in tags for value in str(tag.get("voltage", "")).split(";")
                       if value.strip().isdigit()}, reverse=True)
    counts = {
        "lines": sum(tag.get("kind") == "grid_line" and tag.get("line_class") != "minor_line" for tag in tags),
        "minor": sum(tag.get("line_class") == "minor_line" for tag in tags),
        "substations": sum(tag.get("kind") == "substation" for tag in tags),
        "plants": sum(tag.get("kind") == "plant" for tag in tags),
        "minigrids": sum(tag.get("kind") == "minigrid" for tag in tags),
    }
    return {"type": "FeatureCollection", "features": features, "metadata": {
        "lat": lat, "lon": lon, "radius_km": radius_km, "counts": counts,
        "voltages_kv": voltages, "source": "OpenStreetMap power infrastructure (processed snapshot)", "is_live": False,
    }}
