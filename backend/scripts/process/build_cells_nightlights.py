"""Join the latest valid ingested NASA radiance samples to RW cells."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def build(root: Path = ROOT) -> Path:
    raw_dir = root / "data" / "raw"
    processed_dir = root / "data" / "processed" / "RW"
    snapshots = sorted(raw_dir.glob("nightlights_RW_*.parquet"))
    if not snapshots:
        raise FileNotFoundError(f"No ingested nightlights snapshots found in {raw_dir}")
    cells_path = processed_dir / "cells_features.csv"
    if not cells_path.exists():
        raise FileNotFoundError(f"RW cells table not found: {cells_path}")
    required = {"cell_id", "date", "h", "v", "nighttime_radiance"}
    snapshots_data = []
    for raw_path in snapshots:
        meta_path = raw_path.with_name(raw_path.stem + ".meta.json")
        if not meta_path.exists():
            raise FileNotFoundError(f"Snapshot metadata missing: {meta_path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        statuses = meta.get("per_day_status", {})
        if not statuses or any(item.get("status") == "error" for item in statuses.values()):
            raise ValueError(f"Snapshot has missing per-day status or contains failed days: {raw_path}")
        raw = pd.read_parquet(raw_path)
        if not required.issubset(raw.columns):
            raise ValueError(f"{raw_path} missing columns: {sorted(required - set(raw.columns))}")
        raw["nighttime_radiance"] = pd.to_numeric(raw["nighttime_radiance"], errors="coerce")
        for row in raw.itertuples(index=False):
            tile_key = f"h{int(row.h):02d}v{int(row.v):02d}"
            if pd.isna(row.nighttime_radiance):
                day_status = statuses.get(str(row.date), {})
                tile_status = day_status.get("tiles", {}).get(tile_key, {})
                tile_status = tile_status.get("status") if isinstance(tile_status, dict) else tile_status
                if tile_status != "no_data":
                    raise ValueError(f"NaN radiance on {row.date} {tile_key} without no_data status")
            else:
                found = any(
                    details.get("tiles", {}).get(tile_key, {}).get("status") == "success"
                    and details["tiles"][tile_key].get("granule_date") == str(row.date)
                    and details["tiles"][tile_key].get("granule_name") == row.granule_name
                    for details in statuses.values()
                )
                if not found:
                    raise ValueError(f"No successful NASA metadata entry matches {row.granule_name} on {row.date}")
        snapshots_data.append(raw)

    raw = pd.concat(snapshots_data, ignore_index=True)

    valid = raw.dropna(subset=["nighttime_radiance"]).sort_values("date")
    latest = valid.drop_duplicates("cell_id", keep="last")[["cell_id", "nighttime_radiance"]]
    cells = pd.read_csv(cells_path)
    joined = cells.drop(columns=["nighttime_radiance"], errors="ignore").merge(
        latest, on="cell_id", how="left", validate="one_to_one"
    )
    # Missing values can only arise when every ingested day for that cell is no_data.
    output = processed_dir / "cells_with_nightlights.parquet"
    cache_csv = processed_dir / "cells_with_nightlights.csv"
    tmp = output.with_name(output.name + ".tmp")
    csv_tmp = cache_csv.with_name(cache_csv.name + ".tmp")
    try:
        joined.to_parquet(tmp, index=False)
        os.replace(tmp, output)
        joined.to_csv(csv_tmp, index=False)
        os.replace(csv_tmp, cache_csv)
    finally:
        tmp.unlink(missing_ok=True)
        csv_tmp.unlink(missing_ok=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(build())
    except Exception as exc:
        print(f"Nightlights processing failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
