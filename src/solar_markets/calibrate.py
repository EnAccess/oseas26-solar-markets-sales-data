"""Step 4: logit-shift calibration so the national total matches the control total.

Inputs:  outputs/solar_share_pred.tif, population band of data/processed/feature_stack.tif,
         calibration target in config.yml (or reports/labels_summary.json when left null),
         data/processed/labels.gpkg + labels_district.csv (district check)
Outputs: outputs/solar_share_calibrated.tif
         reports/calibration.json          target, household size, shift, totals, district MAE
Owner:   C (model); see Part 10 of the team playbook.

    python -m solar_markets.calibrate --config config.yml

Every pixel is shifted by the same constant on the logit scale, chosen so that predicted solar
households sum to the target. Values stay in 0-1 and the ranking of places does not change:
calibration changes how much solar the map shows, not where.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.optimize import brentq
from scipy.special import expit, logit

from solar_markets.config import cli_args, get_paths, load_config
from solar_markets.features import Grid, area_zones, zone_means

EPS = 1e-4


def calibration_target(cal: dict, reports: Path) -> tuple[float, float, str]:
    """National solar share, average household size and the source of the share."""
    summary_file = reports / "labels_summary.json"
    summary = json.loads(summary_file.read_text()) if summary_file.exists() else {}
    share, hh_size = cal.get("target_share"), cal.get("avg_household_size")
    source = cal["target_source"]
    if share is None:
        if "solar_share" not in summary:
            raise FileNotFoundError(f"Set calibration.target_share or run the labels stage "
                                    f"({summary_file.name} not found)")
        share, source = summary["solar_share"], f"{source} ({summary_file.name})"
    if hh_size is None:
        if "avg_household_size" not in summary:
            raise FileNotFoundError("Set calibration.avg_household_size or run the labels stage")
        hh_size = summary["avg_household_size"]
    return float(share), float(hh_size), source


def logit_shift(p: np.ndarray, households: np.ndarray, target_share: float
                ) -> tuple[np.ndarray, float]:
    """Shift `p` on the logit scale so that sum(p * households) = target_share * sum(households).

    Pixels where `p` or `households` is NaN stay NaN and are left out of the totals.
    """
    if not 0 < target_share < 1:
        raise ValueError(f"target share must be between 0 and 1, got {target_share}")
    mask = np.isfinite(p) & np.isfinite(households)
    lp, h = logit(np.clip(p[mask], EPS, 1 - EPS)), households[mask]
    target = target_share * h.sum()
    delta = brentq(lambda d: (expit(lp + d) * h).sum() - target, -20, 20)
    out = np.full(p.shape, np.nan, dtype="float32")
    out[mask] = expit(lp + delta)
    return out, float(delta)


def district_check(p_cal: np.ndarray, households: np.ndarray, labels: gpd.GeoDataFrame,
                   districts: pd.DataFrame, grid: Grid) -> pd.DataFrame:
    """Household-weighted calibrated share per district next to the census district share."""
    polys = labels.dissolve(by="district_code").reset_index()[["district_code", "geometry"]]
    polys = polys.to_crs(grid.crs)
    zones = area_zones(polys, grid)
    polys["solar_share_pred"] = zone_means(zones, len(polys), p_cal, households)
    out = polys.drop(columns="geometry").merge(
        districts[["district_code", "district", "solar_share"]], on="district_code")
    out["error_pp"] = 100 * (out["solar_share_pred"] - out["solar_share"])
    return out


def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    share, hh_size, source = calibration_target(cfg["calibration"], paths.reports)

    with rasterio.open(paths.outputs / "solar_share_pred.tif") as src:
        pred, profile = src.read(1).astype("float32"), src.profile
    with rasterio.open(paths.processed / "feature_stack.tif") as src:
        pop = src.read(list(src.descriptions).index("pop") + 1).astype("float32")
        grid = Grid(src.transform, src.width, src.height, str(src.crs))
    households = pop / hh_size

    p_cal, delta = logit_shift(pred, households, share)
    mask = np.isfinite(p_cal)
    before = float(np.nansum(np.where(mask, pred * households, np.nan)))
    after = float(np.nansum(p_cal * households))
    total_hh = float(households[mask].sum())

    out = paths.outputs / "solar_share_calibrated.tif"
    with rasterio.open(out, "w", **(profile | {"count": 1, "dtype": "float32"})) as dst:
        dst.write(p_cal, 1)
        dst.set_band_description(1, "calibrated off-grid solar share of households (0-1)")

    report = {
        "target_share": share,
        "target_source": source,
        "avg_household_size": hh_size,
        "households_total": total_hh,
        "solar_households_before": before,
        "solar_households_after": after,
        "solar_households_target": share * total_hh,
        "logit_shift": delta,
    }
    labels_path = paths.processed / "labels.gpkg"
    districts_path = paths.processed / "labels_district.csv"
    if labels_path.exists() and districts_path.exists():
        check = district_check(p_cal, households, gpd.read_file(labels_path),
                               pd.read_csv(districts_path), grid)
        check.to_csv(paths.reports / "calibration_districts.csv", index=False)
        report["district_mae_pp"] = float(check["error_pp"].abs().mean())
        worst = check.loc[check["error_pp"].abs().idxmax()]
        report["district_worst"] = {"district": str(worst["district"]),
                                    "error_pp": float(worst["error_pp"])}
    (paths.reports / "calibration.json").write_text(json.dumps(report, indent=2))

    print(f"Target: {share:.1%} of {total_hh:,.0f} households ({source})")
    print(f"Solar households: model {before:,.0f} -> calibrated {after:,.0f}; "
          f"logit shift {delta:+.3f}" + ("  (small: the model level was already close)"
                                        if abs(delta) < 0.3 else ""))
    if "district_mae_pp" in report:
        print(f"District check: MAE {report['district_mae_pp']:.1f} pp, worst "
              f"{report['district_worst']['district']} ({report['district_worst']['error_pp']:+.1f} pp)")
    print(f"Wrote {out}")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
