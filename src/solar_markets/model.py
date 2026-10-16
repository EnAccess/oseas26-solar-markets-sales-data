"""Step 3: train LightGBM, report random vs blocked CV, explain with SHAP, predict every pixel.

Inputs:  data/processed/train_table.csv, data/processed/feature_stack.tif,
         data/processed/labels.gpkg (for the re-aggregation check)
Outputs: reports/cv_results.csv            random vs blocked CV, LightGBM vs baselines
         models/lgbm_<target>.txt          final models trained on all areas
         reports/feature_importance.png    SHAP summary for solar_share
         reports/feature_effects.csv       mean |SHAP| and direction per feature and target
         reports/shap_values.csv           per-area SHAP values (top drivers for the web map)
         outputs/<target>_pred.tif         prediction for every pixel, 0-1
         reports/reaggregation.csv/.png    pixel predictions averaged back to areas vs labels
Owner:   C (model); see Part 9 of the team playbook.

    python -m solar_markets.model --config config.yml

Each target in `model.targets` gets its own model. Random CV mixes neighbouring areas between
train and test sets and is optimistic; blocked CV holds out whole districts and is the honest
estimate for a district the model has never seen.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
import rasterio
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

from solar_markets.config import cli_args, get_paths, load_config
from solar_markets.features import Grid, area_zones, zone_means


def transform(df: pd.DataFrame, log_features: list[str]) -> pd.DataFrame:
    """Apply log1p (after clipping at 0) to skewed features; the same for areas and pixels."""
    out = df.copy()
    for c in log_features:
        if c in out:
            out[c] = np.log1p(out[c].clip(lower=0))
    return out


def model_factories(params: dict) -> dict:
    return {
        "mean": None,
        "linear": LinearRegression,
        "lightgbm": lambda: lgb.LGBMRegressor(**params),
    }


def cross_validate(X: np.ndarray, y: np.ndarray, groups: np.ndarray, splitter, cv_name: str,
                   params: dict) -> tuple[list[dict], dict[str, np.ndarray]]:
    """Out-of-fold predictions and scores for the mean baseline, linear and LightGBM."""
    rows, preds = [], {}
    split_groups = groups if isinstance(splitter, GroupKFold) else None
    for name, make in model_factories(params).items():
        pred = np.zeros_like(y)
        for tr, te in splitter.split(X, y, split_groups):
            if make is None:
                pred[te] = y[tr].mean()
            else:
                pred[te] = np.clip(make().fit(X[tr], y[tr]).predict(X[te]), 0, 1)
        rows.append({"cv": cv_name, "model": name, "r2": r2_score(y, pred),
                     "mae_pp": 100 * mean_absolute_error(y, pred), "n_areas": len(y)})
        preds[name] = pred
    return rows, preds


def splitters(mcfg: dict, n_groups: int) -> list[tuple[str, object]]:
    k = mcfg["n_splits"]
    return [
        ("random", KFold(k, shuffle=True, random_state=mcfg["random_state"])),
        (f"blocked by {mcfg['block_column']}", GroupKFold(min(k, n_groups))),
    ]


def feature_effects(shap_values: np.ndarray, X: pd.DataFrame) -> pd.DataFrame:
    """Mean |SHAP| and the sign of the relation between a feature and its SHAP value.

    A positive direction reads "higher values of the feature go with higher predictions".
    These are hypotheses about association, not causes.
    """
    rows = []
    for i, name in enumerate(X.columns):
        varies = X[name].nunique() > 1 and np.ptp(shap_values[:, i]) > 0
        rho = spearmanr(X[name], shap_values[:, i]).statistic if varies else np.nan
        rows.append({"feature": name, "mean_abs_shap": np.abs(shap_values[:, i]).mean(),
                     "direction": "+" if rho > 0 else "-" if rho < 0 else "0",
                     "spearman_feature_vs_shap": rho})
    return pd.DataFrame(rows).sort_values("mean_abs_shap", ascending=False)


def save_shap_summary(shap_values: np.ndarray, X: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    shap.summary_plot(shap_values, X, show=False)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close("all")


def predict_pixels(model, stack: np.ndarray, band_names: list[str], features: list[str],
                   log_features: list[str]) -> np.ndarray:
    """Predict every pixel with all features present; NaN elsewhere."""
    flat = pd.DataFrame({n: stack[i].ravel() for i, n in enumerate(band_names)})[features]
    flat = transform(flat, log_features)
    valid = flat.notna().all(axis=1).to_numpy()
    pred = np.full(len(flat), np.nan, dtype="float32")
    if valid.any():
        pred[valid] = np.clip(model.predict(flat[valid]), 0, 1)
    return pred.reshape(stack.shape[1:])


def reaggregate(preds: dict[str, np.ndarray], pop: np.ndarray, labels: gpd.GeoDataFrame,
                grid: Grid) -> pd.DataFrame:
    """Population-weighted mean of pixel predictions per area, next to the area labels."""
    labels = labels.to_crs(grid.crs).reset_index(drop=True)
    zones = area_zones(labels, grid)
    out = pd.DataFrame({"area_id": labels["area_id"]})
    for target, pred in preds.items():
        out[target] = labels[target]
        out[f"{target}_pred"] = zone_means(zones, len(labels), pred, pop)
    return out


def save_reaggregation_plot(table: pd.DataFrame, targets: list[str], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(targets), figsize=(5 * len(targets), 4.6), squeeze=False)
    for ax, t in zip(axes[0], targets):
        d = table.dropna(subset=[t, f"{t}_pred"])
        ax.scatter(d[t], d[f"{t}_pred"], s=10, alpha=0.6)
        ax.plot([0, 1], [0, 1], color="grey", lw=1)
        ax.set(xlim=(0, 1), ylim=(0, 1), xlabel=f"{t} (labels)",
               ylabel=f"{t} (pixel predictions, re-aggregated)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- pipeline stage

def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    mcfg = cfg["model"]
    features = list(cfg["features"])
    log_features = cfg.get("log_features", [])
    targets = list(mcfg["targets"])
    block = mcfg["block_column"]

    table = pd.read_csv(paths.processed / "train_table.csv")
    with rasterio.open(paths.processed / "feature_stack.tif") as src:
        stack, profile = src.read(), src.profile
        band_names = list(src.descriptions)
        grid = Grid(src.transform, src.width, src.height, str(src.crs))

    cv_rows, effects, shap_frames, pixel_preds = [], [], [], {}
    for target in targets:
        df = table.dropna(subset=[*features, target, block])
        dropped = len(table) - len(df)
        print(f"{target}: {len(df)} areas" + (f" ({dropped} dropped, missing values)" if dropped
                                               else ""))
        X_df = transform(df[features], log_features)
        X, y, groups = X_df.to_numpy(), df[target].to_numpy(), df[block].to_numpy()

        for cv_name, splitter in splitters(mcfg, len(np.unique(groups))):
            rows, _ = cross_validate(X, y, groups, splitter, cv_name, mcfg["lightgbm"])
            cv_rows += [{"target": target, **r} for r in rows]

        final = lgb.LGBMRegressor(**mcfg["lightgbm"]).fit(X_df, y)
        final.booster_.save_model(str(paths.models / f"lgbm_{target}.txt"))

        import shap

        sv = shap.TreeExplainer(final).shap_values(X_df)
        effects.append(feature_effects(sv, X_df).assign(target=target))
        shap_frames.append(pd.DataFrame(sv, columns=features)
                           .assign(area_id=df["area_id"].to_numpy(), target=target))
        if target == targets[0]:
            save_shap_summary(sv, X_df, paths.reports / "feature_importance.png")

        pred = predict_pixels(final, stack, band_names, features, log_features)
        pixel_preds[target] = pred
        out = paths.outputs / f"{target}_pred.tif"
        with rasterio.open(out, "w", **(profile | {"count": 1, "dtype": "float32"})) as dst:
            dst.write(pred, 1)
            dst.set_band_description(1, f"predicted {target} (0-1)")
        print(f"  wrote {out.name}: {np.isfinite(pred).sum():,} pixels, "
              f"median {np.nanmedian(pred):.3f}")

    cv = pd.DataFrame(cv_rows)
    cv.to_csv(paths.reports / "cv_results.csv", index=False)
    pd.concat(effects).to_csv(paths.reports / "feature_effects.csv", index=False)
    pd.concat(shap_frames).to_csv(paths.reports / "shap_values.csv", index=False)
    print("\nCross-validation (MAE in percentage points):")
    print(cv.round(3).to_string(index=False))

    labels_path = paths.processed / "labels.gpkg"
    if labels_path.exists():
        pop = stack[band_names.index("pop")]
        reagg = reaggregate(pixel_preds, pop, gpd.read_file(labels_path), grid)
        reagg.to_csv(paths.reports / "reaggregation.csv", index=False)
        save_reaggregation_plot(reagg, targets, paths.reports / "reaggregation.png")
        for t in targets:
            d = reagg.dropna(subset=[t, f"{t}_pred"])
            print(f"Re-aggregated {t}: MAE {100 * mean_absolute_error(d[t], d[f'{t}_pred']):.1f} pp "
                  f"over {len(d)} areas")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
