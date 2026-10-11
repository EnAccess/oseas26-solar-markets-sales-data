"""Refresh grid distance features from live OpenStreetMap/Overpass data.

This intentionally updates only the grid-related columns and the scores that
depend on grid distance. Other model inputs and outputs are left unchanged.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "backend" / "data" / "processed" / "RW"
OUTPUTS = ROOT / "backend" / "outputs" / "RW"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RWANDA_BBOX = (28.80, -2.90, 30.95, -1.00)
UTM_EPSG = 32735


def fetch_grid_geometries() -> list[LineString | Point]:
    min_lon, min_lat, max_lon, max_lat = RWANDA_BBOX
    query = f"""[out:json][timeout:120];(
      way["power"~"^(line|minor_line|cable)$"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["power"="substation"]({min_lat},{min_lon},{max_lat},{max_lon});
      node["power"="substation"]({min_lat},{min_lon},{max_lat},{max_lon});
    );out geom tags;"""
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "OSEAS-solar-market-reality/1.0"},
    )
    with urllib.request.urlopen(request, timeout=150) as response:
        elements = json.load(response).get("elements", [])

    geometries: list[LineString | Point] = []
    for element in elements:
        if element.get("type") == "way" and element.get("geometry"):
            geometries.append(LineString((p["lon"], p["lat"]) for p in element["geometry"]))
        elif element.get("type") == "node" and "lat" in element:
            geometries.append(Point(element["lon"], element["lat"]))
    if not geometries:
        raise RuntimeError("Overpass returned no grid lines or substations for Rwanda.")
    return geometries


def refresh(path: Path, union) -> None:
    cells = pd.read_csv(path)
    points = gpd.GeoSeries(
        gpd.points_from_xy(cells["lon"], cells["lat"]), crs="EPSG:4326"
    ).to_crs(epsg=UTM_EPSG)
    cells["distance_to_grid_km"] = (
        points.distance(union).to_numpy() / 1000.0
    ).clip(0, 150).round(6)

    # A cell is grid-present when its polygon intersects mapped grid geometry.
    half = abs(float(cells["lon"].iloc[1] - cells["lon"].iloc[0])) / 2
    polygons = gpd.GeoSeries(
        [box(lon - half, lat - half, lon + half, lat + half)
         for lon, lat in zip(cells["lon"], cells["lat"])],
        crs="EPSG:4326",
    ).to_crs(epsg=UTM_EPSG)
    cells["grid_presence"] = polygons.intersects(union).astype(int)

    if "predicted_solar_penetration" in cells:
        def scale(series: pd.Series) -> pd.Series:
            low, high = series.quantile(0.02), series.quantile(0.98)
            if high <= low:
                return pd.Series(0.0, index=series.index)
            return ((series - low) / (high - low)).clip(0, 1)

        parts = np.column_stack(
            [
                scale(np.log1p(cells["population_density"])),
                scale(cells["distance_to_grid_km"]),
                1 - scale(np.log1p(cells["nighttime_radiance"])),
            ]
        )
        cells["energy_need_score"] = (parts @ [0.4, 0.4, 0.2]).round(4)
        cells["market_gap_score"] = (
            cells["energy_need_score"] * (1 - cells["predicted_solar_penetration"])
        ).round(4)

    cells.to_csv(path, index=False)


def main() -> None:
    geometries = fetch_grid_geometries()
    grid = gpd.GeoDataFrame({"geometry": geometries}, crs="EPSG:4326").to_crs(epsg=UTM_EPSG)
    union = grid.geometry.union_all() if hasattr(grid.geometry, "union_all") else grid.geometry.unary_union
    refresh(PROCESSED / "cells_features.csv", union)
    refresh(OUTPUTS / "cells.csv", union)
    print(f"Updated grid distances from {len(geometries)} live OSM geometries.")


if __name__ == "__main__":
    main()
