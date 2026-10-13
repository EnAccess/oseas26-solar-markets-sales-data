"""Step 1: build survey labels (solar, grid and unserved household shares per area).

Inputs:  census person-level microdata (data/raw/census), sector + district boundaries
         (data/raw/boundaries), sector code list (data/reference/rwa_sectors.csv)
Outputs: data/processed/labels.gpkg       one polygon per sector with household shares
         data/processed/labels_district.csv
         reports/labels_summary.json       weighted national figures used by calibration
         reports/labels_solar_share.png    quick-look map
Owner:   A (labels & data); see Part 7 of the team playbook.

    python -m solar_markets.labels --config config.yml

The public census file has one row per person, with the household answers repeated on every
member's row. We keep one row per household and weight it with the household weight.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from solar_markets.config import PROJECT_ROOT, cli_args, get_paths, load_config

GROUPS = ("solar", "grid", "unserved", "other")


# ---------------------------------------------------------------- reading the census

def find_census_file(folder: Path) -> Path:
    files = sorted(p for ext in ("*.dta", "*.sav", "*.csv") for p in folder.glob(ext))
    if not files:
        raise FileNotFoundError(
            f"No census file (.dta, .sav or .csv) in {folder}. "
            "Download PHC5_Public_microdata_2022 as described in data/README.md."
        )
    return files[0]


def read_census(path: Path, columns: dict[str, str]) -> pd.DataFrame:
    """Read only the needed columns, renamed to the keys of `columns`."""
    wanted = {v.lower(): k for k, v in columns.items()}
    if path.suffix == ".csv":
        df = pd.read_csv(path, usecols=lambda c: c.lower() in wanted)
    else:
        import pyreadstat

        reader = pyreadstat.read_dta if path.suffix == ".dta" else pyreadstat.read_sav
        _, meta = reader(str(path), metadataonly=True)
        usecols = [c for c in meta.column_names if c.lower() in wanted]
        df, _ = reader(str(path), usecols=usecols)
    df = df.rename(columns=lambda c: wanted[c.lower()])
    missing = set(columns) - set(df.columns)
    if missing:
        raise KeyError(f"Columns {sorted(columns[m] for m in missing)} not found in {path.name}")
    return df


def to_households(persons: pd.DataFrame) -> pd.DataFrame:
    """One row per household, with household size from the number of member rows."""
    size = persons.groupby("household_id").size().rename("household_size")
    hh = persons.drop_duplicates("household_id").set_index("household_id").join(size)
    hh = hh.dropna(subset=["weight", "lighting", "sector"])
    hh["sector_code"] = hh["sector"].astype(int)
    hh["lighting"] = hh["lighting"].astype(int)
    return hh.reset_index()


def classify_lighting(codes: pd.Series, census_cfg: dict) -> pd.Series:
    """Map lighting codes to solar / grid / unserved / other; missing codes become NaN."""
    group = pd.Series("other", index=codes.index, dtype=object)
    for name in ("solar", "grid", "unserved"):
        group[codes.isin(census_cfg[f"{name}_codes"])] = name
    group[codes.isin(census_cfg.get("missing_codes", []))] = np.nan
    return group


# ---------------------------------------------------------------- aggregation

def aggregate_shares(hh: pd.DataFrame, by: str) -> pd.DataFrame:
    """Weighted share of households in each lighting group, per area."""
    hh = hh.dropna(subset=["group"])
    w = hh["weight"]
    out = pd.DataFrame({
        "n_households_sample": hh.groupby(by).size(),
        "n_households": w.groupby(hh[by]).sum(),
    })
    for g in GROUPS:
        out[f"{g}_share"] = (w * (hh["group"] == g)).groupby(hh[by]).sum() / out["n_households"]
    if "grid_connected" in hh:
        out["grid_connected_share"] = (
            (w * (hh["grid_connected"] == 1)).groupby(hh[by]).sum() / out["n_households"]
        )
    if "urban" in hh:
        out["urban_share"] = (w * (hh["urban"] == 1)).groupby(hh[by]).sum() / out["n_households"]
    return out.reset_index()


def national_summary(hh: pd.DataFrame) -> dict:
    valid = hh.dropna(subset=["group"])
    w = valid["weight"]
    summary = {g + "_share": float((w * (valid["group"] == g)).sum() / w.sum()) for g in GROUPS}
    summary.update(
        n_households_sample=len(valid),
        n_households_weighted=float(w.sum()),
        avg_household_size=float(np.average(hh["household_size"], weights=hh["weight"])),
    )
    return summary


# ---------------------------------------------------------------- geometry

def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").replace("'", "").split())


def sector_polygons(district_file: Path, sector_file: Path, reference: pd.DataFrame,
                    fixes: pd.DataFrame) -> gpd.GeoDataFrame:
    """Sector polygons with census sector codes.

    The boundary file has sector names only, and names repeat across districts, so we find
    each sector's district spatially and match on (district, sector) name.
    """
    districts = gpd.read_file(district_file)[["shapeName", "geometry"]]
    sectors = gpd.read_file(sector_file)[["shapeName", "geometry"]]

    points = sectors.copy()
    points["geometry"] = sectors.representative_point()
    joined = gpd.sjoin(points, districts.rename(columns={"shapeName": "district_b"}),
                       predicate="within", how="left")
    sectors["district_b"] = joined["district_b"].reindex(sectors.index)

    fix = {(norm_name(r.district), norm_name(r.boundary_name)): r.census_name
           for r in fixes.itertuples()}
    sectors["key"] = [
        (norm_name(d), norm_name(fix.get((norm_name(d), norm_name(s)), s)))
        for d, s in zip(sectors["district_b"], sectors["shapeName"])
    ]
    ref = reference.assign(key=[(norm_name(d), norm_name(s))
                                for d, s in zip(reference["district"], reference["sector"])])
    merged = sectors.merge(ref, on="key", how="left")

    unmatched = merged[merged["sector_code"].isna()]
    if len(unmatched):
        raise ValueError(
            "Boundary sectors without a census code; add them to the name-fixes CSV:\n"
            + unmatched[["district_b", "shapeName"]].to_string()
        )
    if merged["sector_code"].duplicated().any():
        raise ValueError("Several boundary polygons matched the same census sector code")
    keep = ["sector_code", "sector", "district_code", "district", "province", "geometry"]
    return gpd.GeoDataFrame(merged[keep], geometry="geometry", crs=sectors.crs)


# ---------------------------------------------------------------- pipeline stage

def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    lab = cfg["labels"]
    if lab["source"] != "census":
        raise NotImplementedError("Only labels.source = census is implemented so far")
    census_cfg = lab["census"]

    path = find_census_file(paths.raw / census_cfg["folder"])
    print(f"Reading {path.name} ...")
    persons = read_census(path, census_cfg["columns"])
    hh = to_households(persons)
    hh["group"] = classify_lighting(hh["lighting"], census_cfg)
    print(f"  {len(persons):,} person rows -> {len(hh):,} households")

    reference = pd.read_csv(PROJECT_ROOT / lab["reference"])
    fixes = pd.read_csv(PROJECT_ROOT / lab["name_fixes"])
    hh = hh.merge(reference[["sector_code", "district_code"]], on="sector_code", how="left")

    by_sector = aggregate_shares(hh, "sector_code")
    by_district = aggregate_shares(hh, "district_code").merge(
        reference.drop_duplicates("district_code")[["district_code", "district", "province"]],
        on="district_code")

    polys = sector_polygons(paths.raw / lab["boundaries"]["district"],
                            paths.raw / lab["boundaries"]["sector"], reference, fixes)
    labels = polys.merge(by_sector, on="sector_code", how="left")
    labels.insert(0, "area_id", labels["sector_code"].astype(int))
    labels["source"] = "Rwanda PHC5 2022 (NISR), main source of lighting"

    no_data = labels["solar_share"].isna().sum()
    if no_data:
        print(f"  warning: {no_data} sectors have no census households")

    summary = national_summary(hh)
    summary.update(source=path.name, admin_level="sector", n_sectors=len(labels))

    labels.to_file(paths.processed / "labels.gpkg", layer="sectors", driver="GPKG")
    by_district.to_csv(paths.processed / "labels_district.csv", index=False)
    (paths.reports / "labels_summary.json").write_text(json.dumps(summary, indent=2))
    save_quicklook(labels, paths.reports / "labels_solar_share.png")

    print("National (household-weighted):")
    for k in ("solar_share", "grid_share", "unserved_share", "other_share"):
        print(f"  {k:15s} {summary[k]:6.1%}")
    print(f"  avg household size {summary['avg_household_size']:.2f}")
    print(f"Wrote {paths.processed / 'labels.gpkg'} ({len(labels)} sectors)")


def save_quicklook(labels: gpd.GeoDataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, col, title in zip(axes, ["solar_share", "unserved_share"],
                              ["Households using off-grid solar", "Households with no grid or solar"]):
        labels.plot(column=col, ax=ax, legend=True, cmap="viridis", vmin=0,
                    missing_kwds={"color": "lightgrey"})
        ax.set_title(f"{title} (share, census 2022)")
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
