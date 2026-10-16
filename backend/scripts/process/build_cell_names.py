"""Name every 5 km analysis cell after the administrative cell (Akagari) containing its centre.

Boundaries: the administrative cell GeoJSON bundled with the frontend's `rwanda-location-lookup`
package (Cell / Sector / District / Province). Output is small and committed:

  data/processed/RW/cell_admin_names.csv   cell_id, admin_cell, admin_sector, admin_district, admin_province

Centres outside every boundary polygon (lakes, neighbouring countries) get no name.
Run from backend/:  python scripts/process/build_cell_names.py [--boundaries path/to/cells.geojson]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed" / "RW"
DEFAULT_BOUNDARIES = ROOT.parent / "frontend" / "node_modules" / "rwanda-location-lookup" / "data" / "cells.geojson"
OUT = PROCESSED / "cell_admin_names.csv"


def build(boundaries: Path) -> pd.DataFrame:
    cells = pd.read_csv(PROCESSED / "cells_features.csv", usecols=["cell_id", "lon", "lat"])
    points = gpd.GeoDataFrame(cells[["cell_id"]], geometry=gpd.points_from_xy(cells["lon"], cells["lat"]),
                              crs="EPSG:4326")
    admin = gpd.read_file(boundaries)[["Name", "Sector", "District", "Province", "geometry"]].to_crs("EPSG:4326")
    joined = gpd.sjoin(points, admin, how="left", predicate="within").drop_duplicates("cell_id")
    out = joined.rename(columns={"Name": "admin_cell", "Sector": "admin_sector", "District": "admin_district",
                                 "Province": "admin_province"})
    return out[["cell_id", "admin_cell", "admin_sector", "admin_district", "admin_province"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    args = parser.parse_args()
    if not args.boundaries.exists():
        print(f"Boundary file not found: {args.boundaries}. Run `npm install` in frontend/ first.")
        return 1
    names = build(args.boundaries)
    names.to_csv(OUT, index=False)
    print(f"Named {names['admin_cell'].notna().sum()} of {len(names)} analysis cells -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
