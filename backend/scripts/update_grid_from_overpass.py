"""Refresh mapped electricity infrastructure for Rwanda from OpenStreetMap (Overpass API).

Writes raw inputs, then rebuilds the processed dataset so distance-to-grid, grid presence
and the market-opportunity scores are recalculated by the shared pipeline:

  data/raw/RW/grid.geojson               power=line / minor_line / cable (LineStrings)
  data/raw/RW/power_facilities.geojson   power=substation / plant (points; polygons -> centroid)
  data/raw/RW/infrastructure.meta.json   query, OSM snapshot timestamp, retrieval time, counts

Run from backend/:  python scripts/update_grid_from_overpass.py [--from-file overpass.json] [--no-build]

OpenStreetMap coverage is incomplete. A mapped line is not proof of a household connection.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RWANDA_BBOX = (28.80, -2.90, 30.95, -1.00)  # min_lon, min_lat, max_lon, max_lat
LINE_TAGS = ("line", "minor_line", "cable")
FACILITY_TAGS = ("substation", "plant")
KEEP_TAGS = ("power", "voltage", "name", "operator", "plant:source", "plant:output:electricity",
             "substation", "location")


def overpass_query() -> str:
    min_lon, min_lat, max_lon, max_lat = RWANDA_BBOX
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return (
        "[out:json][timeout:240];("
        f'way["power"~"^({"|".join(LINE_TAGS)})$"]({bbox});'
        f'way["power"~"^({"|".join(FACILITY_TAGS)})$"]({bbox});'
        f'node["power"~"^({"|".join(FACILITY_TAGS)})$"]({bbox});'
        ");out geom tags;"
    )


def fetch_overpass(query: str) -> dict:
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "OSEAS-solar-market-reality/1.0"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def _props(element: dict) -> dict:
    tags = element.get("tags", {})
    props = {k: tags[k] for k in KEEP_TAGS if k in tags}
    props["osm_id"] = f"{element['type']}/{element['id']}"
    return props


def to_feature_collections(payload: dict) -> tuple[dict, dict]:
    """Split Overpass elements into line and facility FeatureCollections (no invented geometry)."""
    lines, facilities = [], []
    for element in payload.get("elements", []):
        power = element.get("tags", {}).get("power")
        if element["type"] == "way" and power in LINE_TAGS:
            coords = [[p["lon"], p["lat"]] for p in element.get("geometry", [])]
            if len(coords) >= 2:
                lines.append({"type": "Feature", "properties": _props(element),
                              "geometry": {"type": "LineString", "coordinates": coords}})
        elif power in FACILITY_TAGS:
            if element["type"] == "node":
                lon, lat = element["lon"], element["lat"]
            else:  # mapped as an area: use the vertex centroid as a display point
                pts = element.get("geometry", [])
                if not pts:
                    continue
                lon = sum(p["lon"] for p in pts) / len(pts)
                lat = sum(p["lat"] for p in pts) / len(pts)
            facilities.append({"type": "Feature", "properties": _props(element),
                               "geometry": {"type": "Point", "coordinates": [lon, lat]}})
    return ({"type": "FeatureCollection", "features": lines},
            {"type": "FeatureCollection", "features": facilities})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-file", type=Path, help="Use a saved Overpass JSON response instead of querying")
    parser.add_argument("--no-build", action="store_true", help="Only write raw files; skip dataset rebuild")
    args = parser.parse_args()

    query = overpass_query()
    payload = json.loads(args.from_file.read_text(encoding="utf-8")) if args.from_file else fetch_overpass(query)
    lines, facilities = to_feature_collections(payload)
    if not lines["features"]:
        print("Overpass returned no power lines for Rwanda; raw files left unchanged.")
        return 1

    raw_dir = ROOT / "data" / "raw" / "RW"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "grid.geojson").write_text(json.dumps(lines), encoding="utf-8")
    (raw_dir / "power_facilities.geojson").write_text(json.dumps(facilities), encoding="utf-8")
    meta = {
        "source": "OpenStreetMap contributors via Overpass API",
        "licence": "ODbL 1.0",
        "endpoint": OVERPASS_URL,
        "query": query,
        "osm_snapshot": payload.get("osm3s", {}).get("timestamp_osm_base"),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "lines": len(lines["features"]),
            "facilities": len(facilities["features"]),
        },
    }
    (raw_dir / "infrastructure.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Saved {meta['counts']} (OSM snapshot {meta['osm_snapshot']}) to {raw_dir}")

    if not args.no_build:
        from app.config import get_settings
        from app.pipeline.build import build_dataset

        build_dataset(get_settings(), "RW")
        print("Processed dataset rebuilt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
