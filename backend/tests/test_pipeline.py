"""Processed dataset schema, joins and survey aggregation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.pipeline import survey
from app.pipeline.build import join_nightlights_cache

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed" / "RW"
REQUIRED = ["cell_id", "row", "col", "lon", "lat", "population_density", "population_total", "nighttime_radiance",
            "relative_wealth", "distance_to_grid_km", "grid_presence", "district", "province",
            "survey_solar_share", "survey_solar_hh_sampled"]


@pytest.fixture(scope="module")
def cells():
    return pd.read_csv(PROCESSED / "cells_features.csv")


def test_processed_schema_and_keys(cells):
    assert set(REQUIRED) <= set(cells.columns)
    assert cells["cell_id"].is_unique
    assert cells[["row", "col"]].duplicated().sum() == 0
    assert cells["lat"].between(-3, -1).all() and cells["lon"].between(28.7, 31).all()


def test_values_are_physically_plausible(cells):
    assert (cells["population_density"].dropna() >= 0).all()
    assert (cells["nighttime_radiance"].dropna() >= 0).all()
    assert (cells["distance_to_grid_km"].dropna() >= 0).all()
    assert cells["grid_presence"].dropna().isin([0, 1]).all()
    assert cells["survey_solar_share"].dropna().between(0, 1).all()


def test_population_density_matches_cell_total(cells):
    meta = json.loads((PROCESSED / "meta.json").read_text())
    area = meta["grid_spec"]["res_km"] ** 2
    both = cells.dropna(subset=["population_total"])
    assert np.allclose(both["population_total"] / area, both["population_density"])


def test_missing_population_is_not_filled_with_zero_or_median(cells):
    # Cells outside the WorldPop footprint stay missing rather than receiving a surrogate value.
    assert cells["population_density"].isna().any()


def test_survey_counts_unique_ordinary_households():
    stats = survey.district_survey_stats(PROCESSED)
    raw = pd.read_csv(PROCESSED / survey.SURVEY_FILE, encoding="utf-8-sig")
    ordinary = raw[raw["Type of HH"] == "Ordinary HH"]
    assert stats["survey_solar_hh_sampled"].sum() == ordinary["Household ID"].nunique()
    assert stats["survey_solar_hh_sampled"].sum() < len(ordinary)  # device rows != households
    assert len(stats) == 30


def test_every_survey_district_matches_a_boundary(cells):
    stats = survey.district_survey_stats(PROCESSED)
    assert set(stats["district"]) <= set(cells["district"].dropna())
    assert set(cells["province"].dropna()) == {
        "Kigali City", "Northern Province", "Southern Province", "Eastern Province", "Western Province"}


def test_cells_outside_districts_have_no_survey_values(cells):
    outside = cells[cells["district"].isna()]
    assert len(outside) > 0
    assert outside["survey_solar_share"].isna().all()


def test_nightlights_cache_rejects_mismatched_grid(tmp_path):
    cache = pd.DataFrame({"cell_id": ["RW_0001"], "lon": [30.0], "lat": [-2.0], "nighttime_radiance": [1.5]})
    cache.to_csv(tmp_path / "cells_with_nightlights.csv", index=False)
    grid = pd.DataFrame({"cell_id": ["RW_0001"], "lon": [30.0], "lat": [-2.0], "nighttime_radiance": [np.nan]})
    joined, source = join_nightlights_cache(grid, tmp_path)
    assert joined.loc[0, "nighttime_radiance"] == 1.5 and source["status"] == "real"

    moved = grid.assign(lon=[30.05])
    unchanged, source = join_nightlights_cache(moved, tmp_path)
    assert pd.isna(unchanged.loc[0, "nighttime_radiance"]) and source is None


def test_meta_records_provenance():
    meta = json.loads((PROCESSED / "meta.json").read_text())
    assert meta["is_demo"] is False
    for key in ("population", "relative_wealth", "night_lights", "grid", "survey"):
        assert meta["sources"][key]["status"] == "real", key
    assert meta["sources"]["minigrids"]["status"] == "missing"
    assert meta["training_labels"] == "not_written"
