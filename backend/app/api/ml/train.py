"""Train, validate, predict and write all artefacts.  Run:  python -m app.ml.train"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from ...config import Settings, get_settings
from ...pipeline.build import build_dataset
from ...pipeline.export import write_geojson, write_raster
from ...pipeline.spatial_processing import GridSpec
from .explainability import feature_importance
from .predict import add_scores, predict_cells
from .validation import random_cv, spatial_cv

logger = logging.getLogger(__name__)


def make_models(seed: int) -> dict:
    return {
        "random_forest": RandomForestRegressor(
            n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=seed
        ),
        "xgboost": XGBRegressor(
            n_estimators=400, learning_rate=0.05, max_depth=4, subsample=0.8,
            colsample_bytree=0.8, objective="reg:squarederror", n_jobs=-1, random_state=seed,
        ),
    }


def run_training(settings: Settings, country_code: str) -> dict:
    code = country_code.upper()
    pdir, mdir, odir = settings.processed_path(code), settings.models_path(code), settings.outputs_path(code)
    meta = json.loads((pdir / "meta.json").read_text())
    spec = GridSpec(**meta["grid_spec"])
    training = pd.read_csv(pdir / "training.csv")
    cells = pd.read_csv(pdir / "cells_features.csv")

    features = settings.feature_list
    missing = [f for f in features if f not in training.columns]
    if missing:
        raise ValueError(f"FEATURES contains unknown columns: {missing}")

    X = training[features].to_numpy()
    y = training["solar_penetration"].clip(0, 1).to_numpy()
    lon, lat = training["lon"].to_numpy(), training["lat"].to_numpy()

    results, importance, fitted = {}, {}, {}
    for name, model in make_models(settings.random_seed).items():
        logger.info("Validating %s (%d labelled cells)", name, len(y))
        results[name] = {
            "random_cv": random_cv(model, X, y, settings.cv_folds, settings.random_seed),
            "spatial_cv": spatial_cv(model, X, y, lon, lat, settings.spatial_block_km,
                                     settings.spatial_buffer_km, settings.cv_folds),
        }
        fitted[name] = clone(model).fit(X, y)
        importance[name] = feature_importance(fitted[name], features)
        joblib.dump({"model": fitted[name], "features": features}, mdir / f"{name}.joblib")

    # Pick the model with the lowest SPATIAL RMSE (the honest estimate for unsampled areas).
    selected = min(results, key=lambda n: results[n]["spatial_cv"]["rmse"])
    logger.info("Selected model: %s", selected)

    cells["predicted_solar_penetration"] = predict_cells(fitted[selected], cells, features)
    cells = add_scores(cells, settings)
    cells = cells.merge(
        training[["cell_id", "solar_penetration"]].rename(columns={"solar_penetration": "observed_solar_penetration"}),
        on="cell_id", how="left",
    )
    cells.to_csv(odir / "cells.csv", index=False)
    write_raster(cells, spec, "predicted_solar_penetration", odir / "solar_penetration.tif")
    write_raster(cells, spec, "market_gap_score", odir / "market_gap.tif")
    write_geojson(
        cells, spec, odir / "solar_penetration.geojson",
        ["cell_id", "predicted_solar_penetration", "market_gap_score", "energy_need_score"],
    )

    metrics = {
        "country": code,
        "is_demo": meta["is_demo"],
        "selected_model": selected,
        "selection_criterion": "lowest spatial-CV RMSE",
        "features": features,
        "n_samples": len(y),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "models": results,
        "random_cv": results[selected]["random_cv"],
        "spatial_cv": results[selected]["spatial_cv"],
    }
    (mdir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (mdir / "feature_importance.json").write_text(
        json.dumps({"selected_model": selected, "is_demo": meta["is_demo"],
                    "importance": importance[selected], "by_model": importance}, indent=2)
    )
    return metrics


def build_and_train(settings: Settings | None = None, country_code: str | None = None) -> dict:
    settings = settings or get_settings()
    code = (country_code or settings.default_country).upper()
    build_dataset(settings, code)
    return run_training(settings, code)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build dataset, train models, write predictions.")
    ap.add_argument("--country", default=None, help="Country code, e.g. RW")
    args = ap.parse_args()
    m = build_and_train(country_code=args.country)
    print(json.dumps({k: m[k] for k in ("selected_model", "random_cv", "spatial_cv")}, indent=2))
