"""Random and spatially blocked cross-validation with a distance buffer."""
from __future__ import annotations

import logging

import numpy as np
from scipy.spatial import cKDTree
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

logger = logging.getLogger(__name__)
KM_PER_DEG = 111.32


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def coords_to_km(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    x = lon * KM_PER_DEG * np.cos(np.radians(np.mean(lat)))
    return np.column_stack([x, lat * KM_PER_DEG])


def spatial_block_ids(lon: np.ndarray, lat: np.ndarray, block_km: float) -> np.ndarray:
    xy = coords_to_km(lon, lat)
    bx, by = np.floor(xy[:, 0] / block_km).astype(int), np.floor(xy[:, 1] / block_km).astype(int)
    return np.array([f"{a}_{b}" for a, b in zip(bx, by)])


def _out_of_fold(model, X, y, splits) -> dict:
    oof = np.full(len(y), np.nan)
    n_folds = 0
    for train, test in splits:
        if len(train) < 10 or len(test) == 0:
            continue
        fitted = clone(model).fit(X[train], y[train])
        oof[test] = np.clip(fitted.predict(X[test]), 0, 1)
        n_folds += 1
    mask = ~np.isnan(oof)
    if mask.sum() < 5:
        raise ValueError("Too few out-of-fold predictions to compute metrics.")
    return {**regression_metrics(y[mask], oof[mask]), "n_folds": n_folds, "n_evaluated": int(mask.sum())}


def random_cv(model, X, y, n_splits: int, seed: int) -> dict:
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return _out_of_fold(model, X, y, kf.split(X))


def spatial_cv(model, X, y, lon, lat, block_km: float, buffer_km: float, n_splits: int) -> dict:
    """Whole spatial blocks are held out; training points within `buffer_km` of any test point
    are removed so that near neighbours never sit on both sides of the split."""
    blocks = spatial_block_ids(lon, lat, block_km)
    n_groups = len(np.unique(blocks))
    n_splits = min(n_splits, n_groups)
    if n_splits < 2:
        raise ValueError(f"Need at least 2 spatial blocks; got {n_groups}. Reduce SPATIAL_BLOCK_KM.")
    xy = coords_to_km(lon, lat)

    def splits():
        for train, test in GroupKFold(n_splits=n_splits).split(X, y, blocks):
            if buffer_km > 0:
                d, _ = cKDTree(xy[test]).query(xy[train])
                train = train[d > buffer_km]
            yield train, test

    res = _out_of_fold(model, X, y, splits())
    res.update({"n_blocks": n_groups, "block_km": block_km, "buffer_km": buffer_km})
    return res
