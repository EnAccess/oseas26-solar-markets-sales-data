import copy
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
import yaml
from shapely.geometry import box

from solar_markets import calibrate as C
from solar_markets import export as E
from solar_markets import features as F
from solar_markets.config import DEFAULT_CONFIG, load_config

CFG = load_config(DEFAULT_CONFIG)


def test_logit_shift_hits_target_and_keeps_ranking():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.01, 0.6, size=500)
    h = rng.uniform(0, 100, size=500)
    p[:5] = np.nan
    out, delta = C.logit_shift(p, h, 0.156)
    ok = np.isfinite(p)
    assert np.isnan(out[:5]).all()
    assert (out[ok] * h[ok]).sum() == pytest.approx(0.156 * h[ok].sum(), rel=1e-6)
    assert ((out[ok] > 0) & (out[ok] < 1)).all()
    assert (np.argsort(out[ok]) == np.argsort(p[ok])).all()
    assert delta != 0


def test_logit_shift_rejects_impossible_target():
    with pytest.raises(ValueError):
        C.logit_shift(np.array([0.2]), np.array([1.0]), 1.2)


def test_calibration_target_uses_labels_summary_unless_overridden(tmp_path):
    (tmp_path / "labels_summary.json").write_text(
        json.dumps({"solar_share": 0.156, "avg_household_size": 4.1}))
    cal = {"target_share": None, "avg_household_size": None, "target_source": "census"}
    share, size, source = C.calibration_target(cal, tmp_path)
    assert (share, size) == (0.156, 4.1) and "labels_summary.json" in source
    share, size, source = C.calibration_target(cal | {"target_share": 0.2}, tmp_path)
    assert (share, size, source) == (0.2, 4.1, "census")


def test_normalise_clips_at_percentiles():
    a = np.append(np.arange(100, dtype="float32"), [np.nan, 1e6])
    out, lo, hi = E.normalise(a, (2, 98))
    assert np.nanmin(out) == 0 and np.nanmax(out) == 1
    assert np.isnan(out[100])
    assert lo < hi


def test_unserved_households_never_negative():
    out = E.unserved_households(np.array([10.0, 10.0]), np.array([0.5, 0.9]), np.array([0.2, 0.3]))
    assert out.tolist() == pytest.approx([3.0, 0.0])


def test_calibrate_and_export_end_to_end(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["country"]["bbox"] = [30.0, -2.0, 30.2, -1.8]
    cfg["paths"] = {k: str(tmp_path / k) for k in cfg["paths"]}
    for k in cfg["paths"]:
        (tmp_path / k).mkdir()
    out_dir, processed, reports = (tmp_path / k for k in ("outputs", "processed", "reports"))
    grid = F.make_grid(cfg)
    rng = np.random.default_rng(2)

    bands = {n: rng.uniform(0, 5, size=grid.shape).astype("float32") for n in cfg["features"]}
    bands["pop"] = rng.uniform(0, 2000, size=grid.shape).astype("float32")
    for b in bands.values():
        b[:, -1] = np.nan
    F.write_stack(bands, cfg["features"], grid, processed / "feature_stack.tif")
    for target, hi in (("solar_share", 0.4), ("grid_share", 0.6)):
        pred = rng.uniform(0, hi, size=grid.shape).astype("float32")
        pred[:, -1] = np.nan
        with rasterio.open(out_dir / f"{target}_pred.tif", "w", **grid.profile(1)) as dst:
            dst.write(pred, 1)

    # Two districts (west / east halves), one sector each.
    half = grid.transform.c + 12 * grid.res
    labels = gpd.GeoDataFrame(
        {"area_id": [1101, 1201], "district_code": [11, 12]},
        geometry=[box(30.0, -2.0, half, -1.8), box(half, -2.0, 30.2, -1.8)], crs="EPSG:4326")
    labels.to_file(processed / "labels.gpkg", layer="sectors", driver="GPKG")
    pd.DataFrame({"district_code": [11, 12], "district": ["West", "East"],
                  "solar_share": [0.1, 0.2]}).to_csv(processed / "labels_district.csv",
                                                     index=False)
    (reports / "labels_summary.json").write_text(
        json.dumps({"solar_share": 0.156, "avg_household_size": 4.0}))
    pd.DataFrame({"target": ["solar_share", "grid_share"] * 2, "cv": ["random"] * 2 + ["blocked"] * 2,
                  "model": "lightgbm", "r2": [0.6, 0.7, 0.4, 0.5],
                  "mae_pp": [4.0, 5.0, 6.0, 7.0]}).to_csv(reports / "cv_results.csv", index=False)

    C.run(cfg)
    report = json.loads((reports / "calibration.json").read_text())
    assert report["solar_households_after"] == pytest.approx(report["solar_households_target"],
                                                             rel=1e-6)
    assert set(pd.read_csv(reports / "calibration_districts.csv")["district"]) == {"West", "East"}

    E.run(cfg)
    for layer in E.layers(cfg):
        tif = out_dir / layer["file"]
        with rasterio.open(tif) as src:
            assert src.crs.to_epsg() == 4326
            assert src.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"
            assert src.nodata == cfg["export"]["nodata"]
            a = src.read(1, masked=True)
        assert a.min() >= 0 and a.max() <= 1 and a.max() == 1
        assert a.mask[:, -1].all() and not a.mask[:, :-1].any()
        meta = yaml.safe_load(tif.with_suffix(".yml").read_text(encoding="utf-8"))
        for key in ["direction", "reference_year", "method", "labels", "features", "limitations",
                    "validation", "calibration", "licence"]:
            assert meta.get(key), key
        assert "blocked CV R2 = 0.40" in meta["validation"]
        assert (reports / f"{tif.stem}.png").exists()
