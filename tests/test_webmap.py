import copy
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from solar_markets import calibrate as C
from solar_markets import export as E
from solar_markets import features as F
from solar_markets import model as M
from solar_markets import webmap as W
from solar_markets.config import DEFAULT_CONFIG, load_config

CFG = load_config(DEFAULT_CONFIG)
FEATURES = CFG["features"]


def test_top_drivers_text():
    shap = pd.DataFrame({"area_id": [1, 2], "ntl": [-0.05, 0.0], "rwi": [0.01, 0.02],
                         "dist_grid": [0.03, -0.001]})
    values = pd.DataFrame({"ntl": [0.1, 5.0], "rwi": [-1.0, 1.0], "dist_grid": [9.0, 1.0]},
                          index=[1, 2])
    out = W.top_drivers(shap, values, ["ntl", "rwi", "dist_grid"], n=2)
    assert out[1] == "low night lights (-5.0 pp); high distance to the grid (+3.0 pp)"
    assert out[2].startswith("high wealth (RWI) (+2.0 pp)")


def test_zone_sums_ignore_nan_and_unzoned():
    zones = np.array([0, 0, 1, -1])
    assert W.zone_sums(zones, 3, np.array([1.0, np.nan, 2.0, 5.0])).tolist() == [1.0, 2.0, 0.0]


def test_pipeline_from_features_to_map(tmp_path):
    """Synthetic feature stack -> model -> calibrate -> export -> web map."""
    cfg = copy.deepcopy(CFG)
    cfg["country"]["bbox"] = [30.0, -2.0, 30.2, -1.8]
    cfg["paths"] = {k: str(tmp_path / k) for k in cfg["paths"]}
    for k in cfg["paths"]:
        (tmp_path / k).mkdir()
    cfg["model"]["lightgbm"] = cfg["model"]["lightgbm"] | {"min_child_samples": 3,
                                                           "n_estimators": 50}
    processed, reports = tmp_path / "processed", tmp_path / "reports"
    grid = F.make_grid(cfg)
    rng = np.random.default_rng(3)

    bands = {n: rng.uniform(0, 5, size=grid.shape).astype("float32") for n in FEATURES}
    bands["pop"] = rng.uniform(10, 2000, size=grid.shape).astype("float32")
    for b in bands.values():
        b[:, -1] = np.nan
    F.write_stack(bands, FEATURES, grid, processed / "feature_stack.tif")

    res = grid.res
    rows = []
    for i in range(6):
        for j in range(6):
            x0, y1 = grid.transform.c + 4 * j * res, grid.transform.f - 4 * i * res
            rows.append({"area_id": 100 + 6 * i + j, "sector": f"Sector {6 * i + j}",
                         "district_code": i, "district": f"District {i}",
                         "geometry": box(x0, y1 - 4 * res, x0 + 4 * res, y1)})
    labels = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    table = F.training_table(labels, bands, FEATURES, grid)
    labels["solar_share"] = np.clip(0.05 + table["dist_grid"] / 20, 0, 1)
    labels["grid_share"] = np.clip(1 - table["dist_grid"] / 5, 0, 1) * 0.7
    table[["solar_share", "grid_share"]] = labels[["solar_share", "grid_share"]]
    table.to_csv(processed / "train_table.csv", index=False)
    labels.to_file(processed / "labels.gpkg", layer="sectors", driver="GPKG")
    labels.groupby(["district_code", "district"], as_index=False)["solar_share"].mean().to_csv(
        processed / "labels_district.csv", index=False)
    (reports / "labels_summary.json").write_text(
        json.dumps({"solar_share": 0.156, "avg_household_size": 4.0}))

    M.run(cfg)
    C.run(cfg)
    E.run(cfg)
    W.run(cfg)

    summary = gpd.read_file(processed / "sector_summary.gpkg")
    assert len(summary) == 36
    assert sorted(summary["rank_unserved"]) == list(range(1, 37))
    assert summary["pred_solar_share"].between(0, 1).all()
    assert (summary["unserved_hh"] >= 0).all()
    assert summary["top_drivers"].str.contains(r"\(\S+ pp\)").all()
    assert summary["households"].sum() == pytest.approx(np.nansum(bands["pop"]) / 4.0, rel=1e-4)

    ranked = pd.read_csv(reports / "top_underserved_sectors.csv")
    assert ranked["unserved_hh"].is_monotonic_decreasing

    html = (tmp_path / "docs" / "map.html").read_text(encoding="utf-8")
    assert "Top 10 underserved sectors" in html
    assert "Underserved solar market (0-1)" in html and "Source: Night lights" in html
    assert ranked.loc[0, "sector"] in html
