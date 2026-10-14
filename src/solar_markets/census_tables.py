"""Sector labels from the published PHC5 2022 tables (no microdata login needed).

Source: NISR, "RPHC5 Thematic Report: Housing and Households Characteristics", Excel tables
(statistics.gov.rw). These tables cover the full census (3.3 million households).

    Table C1.3  main source of lighting by sector: "Electricity" (grid + solar together),
                kerosene, candles, firewood, batteries, flashlight, lantern, biogas, other
    Table C1.5  households connected to the national grid or a private mini-grid, by sector
    Table 8.12  main source of lighting by province, with solar separate from grid
    Table 5.1   mean household size

What is measured per sector: the electrified share (grid or solar as main light), the unserved
share and the grid-connected share. What is estimated: the split of "electrified" into solar
and grid. Per sector, solar ~ electrified - grid-connected; this is then scaled within each
province so the province solar share matches Table 8.12, and capped at the electrified share.
Grid = electrified - solar, so grid + solar always equals the measured electrified share.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from solar_markets.labels import norm_name

UNSERVED = ["Kerosene/ Paraffin lamp", "Candles", "Firewood", "Batteries/ Bulb",
            "Flashlight/ Phone Flashlight", "Rechargeable Batteries", "Lantern"]
OTHER = ["Biogas", "Other source of energy for lighting"]
SHEETS = {"lighting": "Table-C1.3", "grid": "Table-C1.5", "province": "Table-8.12",
          "household_size": "Table-5.1"}


def read_sheet(path: Path, sheet: str) -> list[tuple]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = [r for r in wb[sheet].iter_rows(values_only=True)
                if r and "Back to Tables" not in str(r[0])]   # skip the navigation link row
    finally:
        wb.close()
    # The sheets start with an empty column A; drop leading columns that are empty everywhere.
    while rows and all(r[0] is None for r in rows):
        rows = [r[1:] for r in rows]
    return rows


def sector_table(rows: list[tuple], first_column: str) -> pd.DataFrame:
    """Sector rows of a "district header, indented sectors" table, columns named by the header.

    The header is the last row before the data whose second cell is `first_column`; when a
    name repeats (percentage and count blocks), the first block keeps the name and later ones
    get " (count)".
    """
    head_idx = max(i for i, r in enumerate(rows) if len(r) > 1 and r[1] == first_column)
    names = []
    group = rows[head_idx - 1][1:] if head_idx else ()
    for j, c in enumerate(rows[head_idx][1:]):
        # A column without its own header (e.g. "Total count") is named by the row above.
        if c is None and j < len(group):
            c = group[j]
        name = str(c).strip() if c is not None else ""
        names.append(f"{name} (count)" if name in names else name)
    records, district = [], None
    for r in rows[head_idx + 1:]:
        label = r[0]
        if label is None or str(label).startswith("Source"):
            continue
        values = r[1:len(names) + 1]
        if all(v is None for v in values):
            district = str(label).strip()
            continue
        name = str(label).strip()
        if name in ("Rwanda", "Total") or district is None:
            continue
        records.append({"district": district, "sector": name,
                        **{n: v for n, v in zip(names, values) if n}})
    return pd.DataFrame(records)


def province_solar(rows: list[tuple]) -> dict[str, float]:
    """Province -> share of households whose main light is solar (Table 8.12, Total column)."""
    out, province = {}, None
    for r in rows:
        label = r[0]
        if label is None:
            continue
        values = [v for v in r[1:] if v is not None]
        if not values:
            province = str(label).strip()
        elif str(label).strip() == "Solar power" and province:
            out[province] = float(values[-1])
    return out


def national_household_size(rows: list[tuple]) -> float:
    for r in rows:
        if r[0] is not None and str(r[0]).strip() == "Rwanda":
            return float([v for v in r[1:] if isinstance(v, (int, float))][-1])
    raise ValueError("No 'Rwanda' row in the household size table")


def match_codes(table: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    ref = reference.assign(key=[(norm_name(d), norm_name(s))
                                for d, s in zip(reference["district"], reference["sector"])])
    table = table.assign(key=[(norm_name(d), norm_name(s))
                              for d, s in zip(table["district"], table["sector"])])
    merged = table.drop(columns=["district", "sector"]).merge(
        ref[["key", "sector_code", "district_code", "province"]], on="key", how="left")
    if merged["sector_code"].isna().any():
        raise ValueError("Census table sectors without a code in the reference list:\n"
                         + table.loc[merged["sector_code"].isna().to_numpy(),
                                     ["district", "sector"]].to_string())
    if len(merged) != len(reference):
        raise ValueError(f"Expected {len(reference)} sectors, found {len(merged)}")
    return merged.drop(columns="key")


def split_solar(electrified: np.ndarray, connected: np.ndarray, n: np.ndarray,
                target: float) -> np.ndarray:
    """Solar share per sector inside one province.

    Starts from max(0, electrified - connected), scaled by one factor so the household-weighted
    province share equals `target`, and never above the electrified share.
    """
    raw = np.clip(electrified - connected, 0, electrified)
    if (raw * n).sum() == 0:
        raw = electrified.copy()
    cap = (electrified * n).sum()
    goal = min(target * n.sum(), cap)

    def gap(k):
        return (np.minimum(raw * k, electrified) * n).sum() - goal

    hi = 1.0
    while gap(hi) < 0 and hi < 1e6:
        hi *= 2
    k = brentq(gap, 0.0, hi) if gap(hi) > 0 else hi
    return np.minimum(raw * k, electrified)


def weighted(df: pd.DataFrame, by: str, cols: list[str]) -> pd.DataFrame:
    w = df["n_households"]
    out = df.groupby(by).agg(n_households=("n_households", "sum"),
                             n_sectors=("sector_code", "size"))
    for c in cols:
        out[c] = (df[c] * w).groupby(df[by]).sum() / out["n_households"]
    return out.reset_index()


def labels_from_tables(path: Path, reference: pd.DataFrame
                       ) -> tuple[pd.DataFrame, pd.DataFrame, dict, str]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; see data/README.md (published census tables)")
    light = sector_table(read_sheet(path, SHEETS["lighting"]), "Electricity")
    grid = sector_table(read_sheet(path, SHEETS["grid"]), "Grid connected Households")
    solar_by_province = province_solar(read_sheet(path, SHEETS["province"]))
    hh_size = national_household_size(read_sheet(path, SHEETS["household_size"]))

    light = match_codes(light, reference)
    grid = match_codes(grid, reference)[["sector_code", "Grid connected Households",
                                         "Not connected Households"]]
    df = light.merge(grid, on="sector_code")

    stated = 1 - df["Not stated"].astype(float)
    df["electrified_share"] = df["Electricity"].astype(float) / stated
    df["unserved_share"] = df[UNSERVED].astype(float).sum(axis=1) / stated
    df["other_share"] = df[OTHER].astype(float).sum(axis=1) / stated
    conn, notconn = (df[c].astype(float) for c in ("Grid connected Households",
                                                   "Not connected Households"))
    df["grid_connected_share"] = conn / (conn + notconn)
    df["n_households"] = df["Total count"].astype(float)

    df["solar_share"] = np.nan
    for province, idx in df.groupby("province").groups.items():
        if province not in solar_by_province:
            raise ValueError(f"No solar share for province '{province}' in Table 8.12")
        d = df.loc[idx]
        df.loc[idx, "solar_share"] = split_solar(
            d["electrified_share"].to_numpy(), d["grid_connected_share"].to_numpy(),
            d["n_households"].to_numpy(), solar_by_province[province])
    df["grid_share"] = df["electrified_share"] - df["solar_share"]
    df["n_households_sample"] = df["n_households"]   # full census: every household counted

    shares = ["solar_share", "grid_share", "unserved_share", "other_share",
              "electrified_share", "grid_connected_share"]
    by_sector = df[["sector_code", "n_households_sample", "n_households", *shares]].copy()
    by_district = weighted(df, "district_code", shares)

    w = df["n_households"]
    summary = {c: float((df[c] * w).sum() / w.sum()) for c in shares}
    summary.update(
        n_households_sample=int(w.sum()), n_households_weighted=float(w.sum()),
        avg_household_size=hh_size, source=path.name,
        solar_split="electrified - grid-connected per sector, scaled to province solar shares "
                    "(Table 8.12)",
    )
    source = ("Rwanda PHC5 2022 (NISR), published tables C1.3/C1.5/8.12; "
              "solar vs grid split estimated")
    return by_sector, by_district, summary, source
