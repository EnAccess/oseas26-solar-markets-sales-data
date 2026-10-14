"""Step 5: export EAE-conformant 0-1 rasters (COG) with YAML metadata.

Inputs:  outputs/solar_share_calibrated.tif, outputs/grid_share_pred.tif, population band of
         data/processed/feature_stack.tif, reports/cv_results.csv, reports/calibration.json
Outputs: outputs/<iso3>_ogs_penetration_<year>_1km.tif + .yml
         outputs/<iso3>_ogs_underserved_<year>_1km.tif + .yml
         reports/<layer>.png               quick-looks for the slides
Owner:   C (model); see Part 11 of the team playbook.

    python -m solar_markets.export --config config.yml

Layer 1 (penetration) shows where off-grid solar has arrived. Layer 2 (underserved) shows
households with neither grid nor solar per pixel: h * max(0, 1 - grid - solar). Both are
rescaled to 0-1 with a robust min-max (clipped at percentiles), 1 = high.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import yaml

from solar_markets.config import cli_args, get_paths, load_config

SOURCES = {
    "ntl": "VIIRS annual night lights V2.2, Earth Observation Group (CC BY 4.0)",
    "pop": "WorldPop 100 m population (CC BY 4.0)",
    "travel_min": "Oxford MAP accessibility to cities 2015 (CC BY 4.0)",
    "built": "ESA WorldCover v200, built-up class (CC BY 4.0)",
    "rwi": "Meta Relative Wealth Index, Chi et al. 2022 (CC BY-NC 4.0)",
    "dist_grid": "Gridfinder predicted grid lines, Arderne et al. 2020 (CC BY 4.0)",
}


def normalise(a: np.ndarray, percentiles: tuple[float, float], log: bool = False
              ) -> tuple[np.ndarray, float, float]:
    """Robust min-max to 0-1: values at or below the low percentile are 0, above the high one 1."""
    a = np.log1p(np.clip(a, 0, None)) if log else a.astype("float64")
    lo, hi = np.nanpercentile(a, percentiles)
    if hi <= lo:
        raise ValueError("Layer is constant between the clip percentiles; cannot normalise")
    return np.clip((a - lo) / (hi - lo), 0, 1).astype("float32"), float(lo), float(hi)


def unserved_households(households: np.ndarray, grid_share: np.ndarray,
                        solar_share: np.ndarray) -> np.ndarray:
    return households * np.clip(1 - grid_share - solar_share, 0, None)


def write_cog(arr: np.ndarray, profile: dict, nodata: float, description: str, out: Path) -> None:
    data = np.where(np.isnan(arr), nodata, arr).astype("float32")
    cog = {"driver": "COG", "width": profile["width"], "height": profile["height"], "count": 1,
           "dtype": "float32", "crs": profile["crs"], "transform": profile["transform"],
           "nodata": nodata, "compress": "deflate", "blocksize": 256}
    with rasterio.open(out, "w", **cog) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, description)
        dst.update_tags(direction="1 = high", metadata=out.with_suffix(".yml").name)


def validation_text(cv: pd.DataFrame | None, target: str) -> str:
    if cv is None:
        return "not available (run solar_markets.model)"
    d = cv[(cv["target"] == target) & (cv["model"] == "lightgbm")]
    parts = [f"{r.cv} CV R2 = {r.r2:.2f}, MAE = {r.mae_pp:.1f} pp" for r in d.itertuples()]
    return f"LightGBM, {target}: " + "; ".join(parts)


def metadata(cfg: dict, layer: dict, norm: tuple[float, float], cv: pd.DataFrame | None,
             cal: dict | None) -> dict:
    ex, country = cfg["export"], cfg["country"]
    lo_pct, hi_pct = ex["normalise_percentiles"]
    norm_text = (f"{'log1p, then ' if layer['log'] else ''}min-max between the {lo_pct}th "
                 f"({norm[0]:.4g}) and {hi_pct}th ({norm[1]:.4g}) percentiles, clipped to [0, 1]")
    cal_text = ("not available (run solar_markets.calibrate)" if cal is None else
                f"{cal['target_share']:.1%} of households ({cal['target_source']}); "
                f"average household size {cal['avg_household_size']:.2f}; "
                f"logit shift {cal['logit_shift']:+.3f}")
    return {
        "name": f"{layer['title']}, {country['name']}",
        "file": layer["file"],
        "version": ex["version"],
        "direction": layer["direction"],
        "units": "dimensionless index, 0-1",
        "reference_year": cfg["reference_year"],
        "resolution": f"30 arc-seconds ({cfg['grid']['resolution_deg']:.6f} deg, ~1 km), "
                      f"{cfg['grid']['crs']}",
        "extent": f"{country['name']} national boundary",
        "nodata": ex["nodata"],
        "normalisation": norm_text,
        "method": layer["method"],
        "labels": ex["labels_description"],
        "features": [SOURCES.get(f, f) for f in cfg["features"]],
        "validation": "; ".join(validation_text(cv, t) for t in layer["targets"]),
        "calibration": cal_text,
        "limitations": "see LIMITATIONS.md",
        "authors": ex["authors"],
        "licence": ex["licence"],
    }


def layers(cfg: dict) -> list[dict]:
    iso, year = cfg["country"]["iso3"].lower(), cfg["reference_year"]
    model = ("LightGBM regression of the household share using off-grid solar for lighting, "
             "trained on census sector labels with night lights, population, wealth, grid "
             "distance, travel time and built-up share; calibrated to the national total by a "
             "logit shift.")
    return [
        {"key": "penetration", "title": "Off-grid solar penetration",
         "file": f"{iso}_ogs_penetration_{year}_1km.tif", "log": False,
         "targets": ["solar_share"],
         "direction": "1 = highest predicted share of households using off-grid solar; "
                      "0 = no predicted solar use",
         "description": "Off-grid solar penetration (0-1, 1 = highest)",
         "method": model},
        {"key": "underserved", "title": "Underserved solar market",
         "file": f"{iso}_ogs_underserved_{year}_1km.tif", "log": True,
         "targets": ["solar_share", "grid_share"],
         "direction": "1 = most households with neither grid electricity nor off-grid solar "
                      "per pixel; 0 = none (or nobody lives there)",
         "description": "Underserved solar market (0-1, 1 = most unserved households)",
         "method": model + " A second model predicts the grid share; unserved households per "
                           "pixel = households x max(0, 1 - grid share - calibrated solar share)."},
    ]


def save_quicklook(arr: np.ndarray, title: str, cmap: str, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 5.2))
    im = ax.imshow(arr, cmap=cmap, vmin=0, vmax=1)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title(title)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    ex = cfg["export"]
    pct = tuple(ex["normalise_percentiles"])
    cal_file = paths.reports / "calibration.json"
    if not cal_file.exists():
        raise FileNotFoundError("reports/calibration.json not found; run solar_markets.calibrate")
    cal = json.loads(cal_file.read_text())
    cv_file = paths.reports / "cv_results.csv"
    cv = pd.read_csv(cv_file) if cv_file.exists() else None

    with rasterio.open(paths.outputs / "solar_share_calibrated.tif") as src:
        solar, profile = src.read(1).astype("float32"), src.profile
    with rasterio.open(paths.outputs / "grid_share_pred.tif") as src:
        grid_share = src.read(1).astype("float32")
    with rasterio.open(paths.processed / "feature_stack.tif") as src:
        pop = src.read(list(src.descriptions).index("pop") + 1).astype("float32")
    households = pop / cal["avg_household_size"]

    values = {"penetration": solar,
              "underserved": unserved_households(households, grid_share, solar)}
    for layer in layers(cfg):
        arr, lo, hi = normalise(values[layer["key"]], pct, log=layer["log"])
        arr[np.isnan(values[layer["key"]])] = np.nan
        out = paths.outputs / layer["file"]
        write_cog(arr, profile, ex["nodata"], layer["description"], out)
        meta = metadata(cfg, layer, (lo, hi), cv, cal)
        out.with_suffix(".yml").write_text(yaml.safe_dump(meta, sort_keys=False, width=100),
                                           encoding="utf-8")
        save_quicklook(arr, layer["description"],
                       "viridis" if layer["key"] == "penetration" else "magma_r",
                       paths.reports / f"{out.stem}.png")
        print(f"Wrote {out.name} + {out.with_suffix('.yml').name}: "
              f"{np.isfinite(arr).sum():,} pixels, median {np.nanmedian(arr):.2f}")
    print(f"Unserved households (total): {np.nansum(values['underserved']):,.0f}")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
