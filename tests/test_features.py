import copy
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from shapely.geometry import LineString, box

from solar_markets import features as F
from solar_markets.config import DEFAULT_CONFIG, load_config

CFG = load_config(DEFAULT_CONFIG)


def small_cfg(tmp_path):
    """A 24 x 24 pixel country with all paths under tmp_path."""
    cfg = copy.deepcopy(CFG)
    cfg["country"]["bbox"] = [30.0, -2.0, 30.2, -1.8]
    cfg["paths"] = {k: str(tmp_path / k) for k in cfg["paths"]}
    for k in cfg["paths"]:
        (tmp_path / k).mkdir()
    return cfg


def test_make_grid_snaps_country_bbox_to_whole_pixels():
    grid = F.make_grid(CFG)
    assert grid.shape == (228, 258)
    assert grid.transform.c == pytest.approx(28.80)
    assert grid.transform.f == pytest.approx(-1.00)


def test_dist_grid_counts_lines_across_the_border(tmp_path):
    grid = F.make_grid(small_cfg(tmp_path))
    # A north-south line 0.05 deg (6 pixels) east of the grid's east edge.
    x = grid.transform.c + grid.width * grid.res + 0.05
    lines = gpd.GeoDataFrame(geometry=[LineString([(x, -2.5), (x, -1.5)])], crs="EPSG:4326")
    dist = F.dist_grid_band(lines, grid, pad_km=30)

    _, lat = grid.centres()
    km_x = grid.res * F.KM_PER_DEG * math.cos(math.radians(lat.mean()))
    # The line is burned into the pixel that contains it; distance runs to that pixel centre.
    line_col = math.floor((x - grid.transform.c) / grid.res)
    expected = (line_col - np.arange(grid.width)) * km_x
    assert np.allclose(dist[10], expected, atol=1e-3)
    assert (np.diff(dist[10]) < 0).all()   # closer towards the east


def test_rwi_band_takes_nearest_point(tmp_path):
    grid = F.make_grid(small_cfg(tmp_path))
    rwi = pd.DataFrame({"latitude": [-1.85, -1.95], "longitude": [30.05, 30.15], "rwi": [1.0, -1.0]})
    band = F.rwi_band(rwi, grid)
    assert band[0, 0] == 1.0      # north-west corner
    assert band[-1, -1] == -1.0   # south-east corner


def test_zone_means_are_population_weighted_with_fallback():
    zones = np.array([[0, 0, 1], [1, -1, 2]])
    values = np.array([[1.0, 3.0, 5.0], [7.0, 100.0, np.nan]])
    weights = np.array([[1.0, 3.0, 0.0], [0.0, 1.0, 1.0]])
    out = F.zone_means(zones, 4, values, weights)
    assert out[0] == pytest.approx((1 + 9) / 4)     # weighted
    assert out[1] == pytest.approx(6.0)             # zero weight -> plain mean
    assert np.isnan(out[2]) and np.isnan(out[3])    # only NaN / no pixels


def test_run_end_to_end_on_synthetic_inputs(tmp_path):
    cfg = small_cfg(tmp_path)
    raw, interim, processed = (tmp_path / k for k in ("raw", "interim", "processed"))
    grid = F.make_grid(cfg)

    # Country = west 3/4 of the bbox; two sectors split north/south, one tiny sector.
    (raw / "boundaries").mkdir()
    country = box(30.0, -2.0, 30.15, -1.8)
    gpd.GeoDataFrame(geometry=[country], crs="EPSG:4326").to_file(
        raw / cfg["labels"]["boundaries"]["district"])
    sectors = gpd.GeoDataFrame({
        "area_id": [1101, 1102, 1103],
        "district_code": [11, 11, 12],
        "solar_share": [0.2, 0.4, 0.1],
    }, geometry=[box(30.0, -1.9, 30.15, -1.8), box(30.0, -2.0, 30.15, -1.9),
                 box(30.101, -1.952, 30.102, -1.951)], crs="EPSG:4326")
    sectors.to_file(processed / "labels.gpkg", layer="sectors", driver="GPKG")

    rng = np.random.default_rng(0)
    ee = rng.uniform(1, 10, size=(4, *grid.shape)).astype("float32")
    ee[0, 0, 0] = -9999
    profile = grid.profile(4) | {"nodata": -9999}
    with rasterio.open(interim / cfg["feature_data"]["ee_stack"], "w", **profile) as dst:
        dst.write(ee)

    (raw / "rwi").mkdir()
    pd.DataFrame({"latitude": [-1.85, -1.95], "longitude": [30.075, 30.075], "rwi": [0.5, -0.5]}) \
        .to_csv(raw / cfg["feature_data"]["rwi"], index=False)
    (raw / "grid").mkdir()
    gpd.GeoDataFrame(geometry=[LineString([(30.0, -1.9), (30.2, -1.9)])], crs="EPSG:4326") \
        .to_file(raw / cfg["feature_data"]["grid_clipped"], driver="GPKG")

    F.run(cfg)

    with rasterio.open(processed / "feature_stack.tif") as src:
        assert src.descriptions == tuple(cfg["features"])
        stack = src.read()
    assert np.isnan(stack[:, :, -1]).all()           # east quarter is outside the country
    assert np.isnan(stack[0, 0, 0])                  # EE nodata becomes NaN
    assert np.nanmin(stack[cfg["features"].index("dist_grid")]) < 1

    table = pd.read_csv(processed / "train_table.csv")
    assert list(table["area_id"]) == [1101, 1102, 1103]
    assert table[cfg["features"]].notna().all().all()
    assert table.loc[2, "n_pixels"] == 1              # tiny sector gets its own pixel
    assert table.loc[0, "rwi"] == pytest.approx(0.5)
    assert (tmp_path / "reports" / "feature_bands.png").exists()
