"""Independent check: compare our labels and model with the Rwanda DHS 2025 survey, by district.

Inputs:  DHS household recode (data/raw/dhs; never committed, DHS terms forbid redistribution),
         data/processed/labels_district.csv, reports/calibration_districts.csv
Outputs: reports/dhs_validation.csv     household-weighted shares per district, DHS vs ours
         reports/dhs_validation.json    national DHS shares and agreement statistics
         reports/dhs_validation.png     scatter plots, one point per district
Owner:   A (labels & data); see Part 18 of the team playbook (DHS as an independent check).

    python -m solar_markets.validate --config config.yml

DHS 2025 asks each household its main type of light (hv262) with solar separate from grid, and
its sample is designed for district estimates. It is three years newer than the census, so we
compare the pattern (correlation, rank correlation) and report the level difference separately.
Only district aggregates are written; no household data leaves data/raw.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_markets.config import cli_args, get_paths, load_config

GROUPS = ("solar", "grid", "none")


def dhs_households(path: Path, dcfg: dict) -> pd.DataFrame:
    """One row per household: district, weight and lighting group (solar / grid / none)."""
    import pyreadstat

    cols = dcfg["columns"]
    hh, _ = pyreadstat.read_dta(str(path), usecols=list(cols.values()))
    hh = hh.rename(columns={v: k for k, v in cols.items()})
    hh = hh.dropna(subset=["light", "district", "weight"])
    hh = hh[~hh["light"].isin(dcfg.get("missing_codes", []))].copy()
    hh["weight"] = hh["weight"] / 1e6            # DHS weights carry 6 implied decimals
    hh["group"] = np.where(hh["light"].isin(dcfg["solar_codes"]), "solar",
                           np.where(hh["light"].isin(dcfg["grid_codes"]), "grid", "none"))
    hh["district_code"] = hh["district"].astype(int)
    return hh


def weighted_shares(hh: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Household-weighted share of each lighting group, overall or per `by`."""
    keys = hh[by] if by else pd.Series(0, index=hh.index)
    w = hh["weight"]
    out = pd.DataFrame({"n_households_sample": hh.groupby(keys).size()})
    for g in GROUPS:
        out[f"dhs_{g}"] = (w * (hh["group"] == g)).groupby(keys).sum() / w.groupby(keys).sum()
    return out.reset_index(names=by or "all")


def agreement(df: pd.DataFrame, ours: str, dhs: str) -> dict:
    d = df[[ours, dhs]].dropna()
    return {
        "n_districts": len(d),
        "pearson_r": float(np.corrcoef(d[ours], d[dhs])[0, 1]),
        "rank_r": float(d.rank().corr().iloc[0, 1]),
        "mae_pp": float(100 * (d[ours] - d[dhs]).abs().mean()),
        "mean_diff_pp": float(100 * (d[ours] - d[dhs]).mean()),   # ours - DHS
    }


COMPARISONS = [  # (our column, DHS column, description)
    ("solar_share", "dhs_solar", "solar share, census labels (solar/grid split estimated)"),
    ("solar_share_pred", "dhs_solar", "solar share, our calibrated 1 km model"),
    ("grid_share", "dhs_grid", "grid share, census labels"),
    ("unserved_share", "dhs_none", "neither grid nor solar, census labels (measured)"),
]


def save_plot(df: pd.DataFrame, year: int, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = [c for c in (COMPARISONS[0], COMPARISONS[1], COMPARISONS[3]) if c[0] in df]
    fig, axes = plt.subplots(1, len(panels), figsize=(5 * len(panels), 4.8), squeeze=False)
    for ax, (ours, dhs, title) in zip(axes[0], panels):
        ax.scatter(df[dhs], df[ours], s=18)
        ax.plot([0, 1], [0, 1], color="grey", lw=1)
        hi = float(max(df[dhs].max(), df[ours].max())) * 1.1
        ax.set(xlim=(0, hi), ylim=(0, hi), xlabel=f"DHS {year} (district)", ylabel="ours (2022)",
               title=title.split(",")[0] + "\n" + title.split(", ")[1])
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    dcfg = cfg["validation"]["dhs"]
    path = paths.raw / dcfg["household_file"]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; see data/README.md (DHS, needs an approved account)")

    hh = dhs_households(path, dcfg)
    national = weighted_shares(hh).iloc[0]
    by_district = weighted_shares(hh, "district_code")

    ours = pd.read_csv(paths.processed / "labels_district.csv")[
        ["district_code", "district", "solar_share", "grid_share", "unserved_share"]]
    cal_file = paths.reports / "calibration_districts.csv"
    if cal_file.exists():
        ours = ours.merge(pd.read_csv(cal_file)[["district_code", "solar_share_pred"]],
                          on="district_code", how="left")
    table = ours.merge(by_district, on="district_code", how="inner")
    table.to_csv(paths.reports / "dhs_validation.csv", index=False)

    summary = {
        "survey": f"Rwanda DHS {dcfg['year']}",
        "households": len(hh),
        "national": {g: float(national[f"dhs_{g}"]) for g in GROUPS},
        "agreement": {desc: agreement(table, o, d) for o, d, desc in COMPARISONS if o in table},
    }
    (paths.reports / "dhs_validation.json").write_text(json.dumps(summary, indent=2))
    save_plot(table, dcfg["year"], paths.reports / "dhs_validation.png")

    print(f"{summary['survey']}: {len(hh):,} households, {len(table)} districts")
    print("National (weighted): " + ", ".join(f"{g} {v:.1%}" for g, v in summary["national"].items()))
    for desc, a in summary["agreement"].items():
        print(f"  {desc:58s} r={a['pearson_r']:.2f}  rank r={a['rank_r']:.2f}  "
              f"MAE={a['mae_pp']:.1f} pp  ours-DHS={a['mean_diff_pp']:+.1f} pp")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
