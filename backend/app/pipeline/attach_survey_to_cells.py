"""Attach district-level MTF survey stats to each grid cell.

Every cell gets the stats of the district it sits in. Households with a
solar device are counted from the raw survey CSV, weighted by the
nationally representative household weight.

Run:  python -m app.pipeline.attach_survey_to_cells
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

BASE = Path(__file__).resolve().parents[2] / "data" / "processed" / "RW"
CELLS = BASE / "cells_features.csv"
GEO = BASE / "rwanda_districts.geojson"
SURVEY = BASE / "Household_Solar_Device_Use_and_Ownership.csv"
OUT = BASE / "cells_with_survey.csv"

W = "Household weight (nationally representative sample households)"


def district_stats() -> pd.DataFrame:
    df = pd.read_csv(SURVEY)
    df["District"] = df["District"].astype(str).str.strip().str.title()
    df["has_solar"] = df["Solar device"].notna() & (df["Solar device"].astype(str).str.strip() != "")

    agg = df.groupby("District").apply(lambda g: pd.Series({
        "households_surveyed": int(len(g)),
        "solar_households": int(g["has_solar"].sum()),
        "solar_pct": round(100 * g["has_solar"].sum() / len(g), 2),
        "solar_households_weighted": float(g.loc[g["has_solar"], W].sum()),
    })).reset_index()
    return agg


def assign_districts(cells: pd.DataFrame) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(
        cells,
        geometry=gpd.points_from_xy(cells["lon"], cells["lat"]),
        crs="EPSG:4326",
    )
    districts = gpd.read_file(GEO)[["NAME_2", "geometry"]].rename(columns={"NAME_2": "District"})
    districts["District"] = districts["District"].astype(str).str.strip().str.title()
    joined = gpd.sjoin(gdf, districts, how="left", predicate="within")
    return joined.drop(columns=["index_right"], errors="ignore")


def main() -> None:
    cells = pd.read_csv(CELLS)
    print(f"Loaded {len(cells)} cells")

    stats = district_stats()
    print(f"Computed stats for {len(stats)} districts")

    joined = assign_districts(cells)
    unmatched = joined["District"].isna().sum()
    if unmatched:
        print(f"WARNING: {unmatched} cells did not fall inside any district polygon")

    enriched = joined.merge(stats, on="District", how="left")
    enriched = enriched.drop(columns=["geometry"])
    enriched.to_csv(OUT, index=False)
    print(f"Wrote {len(enriched)} rows → {OUT}")
    print(enriched[["cell_id", "District", "solar_households", "solar_pct"]].head())


if __name__ == "__main__":
    main()