"""Live OpenStreetMap grid checks for a clicked map location."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from .deps import country_code

router = APIRouter()
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _feature(element: dict) -> dict | None:
    tags = element.get("tags", {})
    kind = tags.get("power")
    if element["type"] == "way" and element.get("geometry"):
        geometry = {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in element["geometry"]]}
        kind = "grid_line" if kind in {"line", "minor_line", "cable"} else kind
    elif element["type"] == "node" and "lat" in element:
        geometry = {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
        kind = "grid_point" if kind in {"substation", "plant", "generator"} else kind
    else:
        return None
    return {"type": "Feature", "geometry": geometry, "properties": {
        "kind": kind, "power": tags.get("power"), "name": tags.get("name"),
        "voltage": tags.get("voltage"),
        "source": tags.get("plant:source") or tags.get("generator:source"),
    }}


@router.get("/grid/check", tags=["map"], summary="Check live mapped grid infrastructure near a point")
async def grid_check(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10, ge=1, le=50),
    _: str = Depends(country_code),
) -> dict:
    radius_m = int(radius_km * 1000)
    query = f"""[out:json][timeout:25];(
      way[\"power\"~\"^(line|minor_line|cable)$\"](around:{radius_m},{lat},{lon});
      node[\"power\"~\"^(substation|plant|generator)$\"](around:{radius_m},{lat},{lon});
    );out geom tags 500;"""
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "OSEAS-solar-market-reality/1.0"}) as client:
            response = await client.post(OVERPASS_URL, data={"data": query})
            response.raise_for_status()
            elements = response.json().get("elements", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "The live OpenStreetMap grid service is unavailable. Try again shortly.") from exc

    features = [feature for element in elements if (feature := _feature(element))]
    tags = [element.get("tags", {}) for element in elements]
    voltages = sorted({int(value) / 1000 for tag in tags for value in str(tag.get("voltage", "")).split(";")
                       if value.strip().isdigit()}, reverse=True)
    counts = {
        "lines": sum(tag.get("power") in {"line", "cable"} for tag in tags),
        "minor": sum(tag.get("power") == "minor_line" for tag in tags),
        "substations": sum(tag.get("power") == "substation" for tag in tags),
        "plants": sum(tag.get("power") in {"plant", "generator"} for tag in tags),
    }
    return {"type": "FeatureCollection", "features": features, "metadata": {
        "lat": lat, "lon": lon, "radius_km": radius_km, "counts": counts,
        "voltages_kv": voltages, "source": "OpenStreetMap via Overpass API", "is_live": True,
    }}