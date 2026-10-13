"""District assignment and MTF solar-device survey indicators for grid cells.

Inputs (checked into data/processed/RW/):
  rwanda_districts.geojson                       GADM level-2 district polygons (NAME_1 province, NAME_2 district)
  Household_Solar_Device_Use_and_Ownership.csv   MTF device module: one row per solar device, solar owners only

The survey file lists only households that own a solar device, so it cannot give a share on its
own. What it supports:
  * survey_solar_hh_sampled   unique ordinary households in the sample with a solar device
  * survey_solar_hh_weighted  survey-weighted estimate of households owning a solar device
                              (sum of the nationally representative household weight)
  * survey_solar_share        weighted solar households / (district population / household size).
                              An indicative district-level estimate that mixes two sources and an
                              assumed household size; left missing when outside [0, 1].
Refugee-camp households use a separate weight and are excluded from district estimates.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SURVEY_FILE = "Household_Solar_Device_Use_and_Ownership.csv"
DISTRICTS_FILE = "rwanda_districts.geojson"
WEIGHT = "Household weight (nationally representative sample households)"
# GADM stores Rwandan provinces under their Kinyarwanda names; the survey uses the English names.
PROVINCE_NAMES = {
    "Amajyaruguru": "Northern Province",
    "Amajyepfo": "Southern Province",
    "Iburasirazuba": "Eastern Province",
    "Iburengerazuba": "Western Province",
    "Umujyiwakigali": "Kigali City",
}


def _name(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.title()


def load_districts(processed_dir: Path) -> gpd.GeoDataFrame | None:
    path = processed_dir / DISTRICTS_FILE
    if not path.exists():
        return None
    gdf = gpd.read_file(path)[["NAME_1", "NAME_2", "geometry"]]
    gdf = gdf.rename(columns={"NAME_1": "province", "NAME_2": "district"})
    gdf["district"] = _name(gdf["district"])
    gdf["province"] = _name(gdf["province"]).replace(PROVINCE_NAMES)
    return gdf.to_crs("EPSG:4326")


def assign_districts(cells: pd.DataFrame, districts: gpd.GeoDataFrame) -> pd.DataFrame:
    """Attach district/province of the polygon containing each cell centre (NaN when outside all)."""
    points = gpd.GeoDataFrame(
        cells[["cell_id"]], geometry=gpd.points_from_xy(cells["lon"], cells["lat"]), crs="EPSG:4326"
    )
    joined = gpd.sjoin(points, districts, how="left", predicate="within")
    joined = joined.drop_duplicates("cell_id")[["cell_id", "district", "province"]]
    return cells.merge(joined, on="cell_id", how="left", validate="one_to_one")


def district_survey_stats(processed_dir: Path) -> pd.DataFrame | None:
    path = processed_dir / SURVEY_FILE
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df[df["Type of HH"].astype(str).str.strip() == "Ordinary HH"]
    households = df.drop_duplicates("Household ID").copy()
    households["district"] = _name(households["District"])
    return (
        households.groupby("district")
        .agg(survey_solar_hh_sampled=("Household ID", "size"), survey_solar_hh_weighted=(WEIGHT, "sum"))
        .reset_index()
    )


NAMES_FILE = "cell_admin_names.csv"


def attach_place_names(cells: pd.DataFrame, processed_dir: Path) -> pd.DataFrame:
    """Add admin_cell / admin_sector names and a readable, unique `place_name` for every analysis cell.

    Names come from scripts/process/build_cell_names.py (administrative cell containing the centre).
    Analysis cells sharing one administrative cell are numbered; unnamed ones show their coordinates.
    """
    out = cells.drop(columns=["admin_cell", "admin_sector", "place_name"], errors="ignore")
    path = processed_dir / NAMES_FILE
    if path.exists():
        names = pd.read_csv(path, usecols=["cell_id", "admin_cell", "admin_sector"])
        out = out.merge(names, on="cell_id", how="left", validate="one_to_one")
    else:
        out["admin_cell"] = np.nan
        out["admin_sector"] = np.nan
    base = out["admin_cell"].astype("string") + ", " + out["admin_sector"].astype("string")
    rank = base.groupby(base).cumcount() + 1
    count = base.map(base.value_counts())
    numbered = base.where(count.fillna(1) <= 1, base + " (" + rank.astype(str) + ")")
    coords = "Outside Rwanda boundary (" + out["lat"].round(3).astype(str) + ", " + out["lon"].round(3).astype(str) + ")"
    out["place_name"] = numbered.fillna(coords).astype(object)
    return out


def attach_survey(cells: pd.DataFrame, processed_dir: Path, household_size: float) -> pd.DataFrame:
    """Add district, province and district-level survey indicators to every cell."""
    out = cells.copy()
    districts = load_districts(processed_dir)
    if districts is None:
        logger.warning("No district boundaries found; survey indicators not attached")
        for col in ("district", "province", "survey_solar_hh_sampled", "survey_solar_hh_weighted",
                    "district_population", "survey_solar_share"):
            out[col] = np.nan
        return out

    out = assign_districts(out, districts)
    unmatched = int(out["district"].isna().sum())
    if unmatched:
        logger.info("%d cells have a centre outside every district polygon", unmatched)

    district_pop = out.groupby("district")["population_total"].sum(min_count=1).rename("district_population")
    out = out.merge(district_pop, on="district", how="left")

    stats = district_survey_stats(processed_dir)
    if stats is None:
        out["survey_solar_hh_sampled"] = np.nan
        out["survey_solar_hh_weighted"] = np.nan
        out["survey_solar_share"] = np.nan
        return out

    unknown = sorted(set(stats["district"]) - set(districts["district"]))
    if unknown:
        logger.warning("Survey districts without a boundary match: %s", unknown)
    out = out.merge(stats, on="district", how="left")
    households = out["district_population"] / household_size
    share = out["survey_solar_hh_weighted"] / households
    invalid = share.notna() & ~share.between(0, 1)
    if invalid.any():
        logger.warning("Dropping %d cells with an implausible district solar share", int(invalid.sum()))
    out["survey_solar_share"] = share.where(~invalid)
    return out
