import copy

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from shapely.geometry import box
from sklearn.model_selection import GroupKFold, KFold

from solar_markets import features as F
from solar_markets import model as M
from solar_markets.config import DEFAULT_CONFIG, load_config

CFG = load_config(DEFAULT_CONFIG)
FEATURES = CFG["features"]


def test_transform_logs_only_listed_features_and_clips_negatives():
    df = pd.DataFrame({"ntl": [-0.5, np.e - 1], "rwi": [-1.0, 2.0]})
    out = M.transform(df, ["ntl", "pop"])
    assert out["ntl"].tolist() == pytest.approx([0.0, 1.0])
    assert out["rwi"].tolist() == [-1.0, 2.0]


def synthetic_signal(n=200, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.uniform(0, 1, size=(n, 3))
    y = np.clip(0.1 + 0.6 * X[:, 0] * (X[:, 1] > 0.5), 0, 1)
    return X, y, np.repeat(np.arange(n // 10), 10)


def test_lightgbm_beats_mean_baseline_on_learnable_signal():
    X, y, groups = synthetic_signal()
    params = CFG["model"]["lightgbm"] | {"min_child_samples": 5}
    rows, preds = M.cross_validate(X, y, groups, KFold(5, shuffle=True, random_state=0),
                                   "random", params)
    scores = {r["model"]: r for r in rows}
    assert scores["lightgbm"]["r2"] > 0.8
    assert scores["mean"]["r2"] < 0.05
    assert all(((p >= 0) & (p <= 1)).all() for p in preds.values())


def test_blocked_cv_keeps_groups_together():
    X, y, groups = synthetic_signal()
    for tr, te in GroupKFold(5).split(X, y, groups):
        assert not set(groups[tr]) & set(groups[te])
    names = [name for name, _ in M.splitters(CFG["model"], n_groups=3)]
    assert names == ["random", "blocked by district_code"]
    assert M.splitters(CFG["model"], n_groups=3)[1][1].n_splits == 3


def test_feature_effects_direction():
    X = pd.DataFrame({"a": [0.0, 1, 2, 3], "b": [3.0, 2, 1, 0]})
    sv = np.array([[-1.0, 0.1], [0, 0.1], [1, 0.1], [2, 0.1]])
    eff = M.feature_effects(sv, X).set_index("feature")
    assert eff.loc["a", "direction"] == "+"
    assert eff.index[0] == "a"   # sorted by importance


def test_run_end_to_end_on_synthetic_stack(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["country"]["bbox"] = [30.0, -2.0, 30.2, -1.8]
    cfg["paths"] = {k: str(tmp_path / k) for k in cfg["paths"]}
    for k in cfg["paths"]:
        (tmp_path / k).mkdir()
    cfg["model"]["lightgbm"] = cfg["model"]["lightgbm"] | {"min_child_samples": 3,
                                                           "n_estimators": 50}
    grid = F.make_grid(cfg)
    rng = np.random.default_rng(1)

    # Feature stack: random bands, NaN in the last column (outside the country).
    bands = {n: rng.uniform(0, 5, size=grid.shape).astype("float32") for n in FEATURES}
    for b in bands.values():
        b[:, -1] = np.nan
    stack_path = tmp_path / "processed" / "feature_stack.tif"
    F.write_stack(bands, FEATURES, grid, stack_path)

    # 36 square areas of 4 x 4 pixels in 6 districts; labels follow night lights.
    res = grid.res
    geoms, ids = [], []
    for i in range(6):
        for j in range(6):
            x0 = grid.transform.c + 4 * j * res
            y1 = grid.transform.f - 4 * i * res
            geoms.append(box(x0, y1 - 4 * res, x0 + 4 * res, y1))
            ids.append(100 + 6 * i + j)
    labels = gpd.GeoDataFrame({"area_id": ids, "district_code": np.repeat(np.arange(6), 6)},
                              geometry=geoms, crs="EPSG:4326")
    table = F.training_table(labels.assign(solar_share=0.0, grid_share=0.0), bands, FEATURES,
                             grid)
    table["solar_share"] = np.clip(table["ntl"] / 5, 0, 1)
    table["grid_share"] = np.clip(1 - table["ntl"] / 5, 0, 1)
    table.to_csv(tmp_path / "processed" / "train_table.csv", index=False)
    labels.merge(table[["area_id", "solar_share", "grid_share"]], on="area_id").to_file(
        tmp_path / "processed" / "labels.gpkg", layer="sectors", driver="GPKG")

    M.run(cfg)

    cv = pd.read_csv(tmp_path / "reports" / "cv_results.csv")
    assert len(cv) == 2 * 2 * 3          # targets x CV schemes x models
    assert set(cv["cv"]) == {"random", "blocked by district_code"}
    for target in ("solar_share", "grid_share"):
        assert (tmp_path / "models" / f"lgbm_{target}.txt").exists()
        with rasterio.open(tmp_path / "outputs" / f"{target}_pred.tif") as src:
            pred = src.read(1)
        assert np.isnan(pred[:, -1]).all()
        inside = pred[:, :-1]
        assert np.isfinite(inside).all() and inside.min() >= 0 and inside.max() <= 1
    eff = pd.read_csv(tmp_path / "reports" / "feature_effects.csv")
    top = eff[eff["target"] == "solar_share"].iloc[0]
    assert top["feature"] == "ntl" and top["direction"] == "+"
    reagg = pd.read_csv(tmp_path / "reports" / "reaggregation.csv")
    assert reagg["solar_share_pred"].notna().all()
    assert (tmp_path / "reports" / "feature_importance.png").exists()
