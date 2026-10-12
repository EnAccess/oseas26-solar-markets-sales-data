"""Fetch dated, real NASA VNP46A2 snapshots for Rwanda cells."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import h5py
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nightlights.config import LAADS
from nightlights.core import nasa
from nightlights.core.remote import get_token
from nightlights.core.sampling import _sample
from nightlights.core.tiles import tile_for

LOG = logging.getLogger("fetch_nightlights")
TIMEOUT_SECONDS = 120
RAW_COLUMNS = ["cell_id", "lat", "lon", "date", "h", "v", "granule_name", "nighttime_radiance"]


def fetch(start: date, end: date, root: Path = ROOT) -> tuple[Path, Path, Path]:
    if end < start:
        raise ValueError("end date must be on or after start date")
    raw_dir = root / "data" / "raw"
    cells_path = root / "data" / "processed" / "RW" / "cells_features.csv"
    if not cells_path.exists():
        raise FileNotFoundError(f"RW cells table not found: {cells_path}")
    cells = pd.read_csv(cells_path)
    required = {"cell_id", "lat", "lon"}
    if not required.issubset(cells.columns):
        raise ValueError(f"{cells_path} missing {sorted(required - set(cells.columns))}")
    cells["h"], cells["v"] = zip(*(tile_for(float(lat), float(lon)) for lat, lon in zip(cells.lat, cells.lon)))
    tiles = {(int(h), int(v)): group for (h, v), group in cells.groupby(["h", "v"], sort=True)}

    token = get_token()
    records: list[dict] = []
    day_status: dict[str, dict] = {}
    lookup_log: list[dict] = []
    source_urls: set[str] = set()
    sampled_granules: set[str] = set()
    failures: list[str] = []
    day = start
    while day <= end:
        day_key = day.isoformat()
        tile_status: dict[str, dict] = {}
        for (h, v), points_df in tiles.items():
            tile_key = f"h{h:02d}v{v:02d}"
            try:
                files, found, log = _find_latest_with_retries(token, h, v, day, days_back=30)
                lookup_log.append({"date": day_key, "tile": tile_key, "entries": log})
                if not files:
                    tile_status[tile_key] = {"status": "no_data"}
                    for row in points_df.itertuples(index=False):
                        records.append(_empty_row(row, day_key, h, v))
                    continue
                granule = files[0]
                name = granule["name"]
                doy = found.timetuple().tm_yday
                url = granule.get("downloadsLink") or (
                    f"{LAADS}/archive/allData/5200/VNP46A2/{found.year}/{doy:03d}/{name}"
                )
                source_urls.add(url)
                if name in sampled_granules:
                    tile_status[tile_key] = {
                        "status": "success", "granule_date": found.isoformat(), "granule_name": name,
                    }
                    continue
                response = _get_with_retries(
                    url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_SECONDS
                )
                if response.status_code in (401, 403):
                    raise PermissionError(f"NASA rejected the token (HTTP {response.status_code})")
                response.raise_for_status()
                with tempfile.TemporaryDirectory() as temp_dir:
                    h5_path = Path(temp_dir) / name
                    h5_path.write_bytes(response.content)
                    bounds = dict(west=-180 + h * 10, east=-170 + h * 10,
                                  south=80 - v * 10, north=90 - v * 10)
                    with h5py.File(h5_path, "r") as h5:
                        for row in points_df.itertuples(index=False):
                            stats = _sample(h5, bounds, float(row.lat), float(row.lon), 1.0, 1.0)
                            value = stats["mean"]
                            if value is None:
                                raise ValueError(f"Granule {name} has no valid radiance pixels for cell {row.cell_id}")
                            records.append({"cell_id": row.cell_id, "lat": row.lat, "lon": row.lon,
                                            "date": found.isoformat(), "h": h, "v": v, "granule_name": name,
                                            "nighttime_radiance": value})
                sampled_granules.add(name)
                tile_status[tile_key] = {
                    "status": "success", "granule_date": found.isoformat(), "granule_name": name,
                }
            except Exception as exc:
                if isinstance(exc, PermissionError):
                    raise
                message = f"{day_key} {tile_key}: {type(exc).__name__}: {exc}"
                LOG.exception("Skipping failed NASA tile/day %s %s", day_key, tile_key)
                failures.append(message)
                tile_status[tile_key] = {"status": "error", "message": str(exc)}
        statuses = {value["status"] for value in tile_status.values()}
        day_status[day_key] = {"status": "error" if "error" in statuses else
                               ("success" if "success" in statuses else "no_data"),
                               "tiles": tile_status}
        day += timedelta(days=1)

    if failures:
        raise RuntimeError("NASA ingest failed; snapshot was not replaced: " + "; ".join(failures))

    snapshot_date = end.isoformat()
    raw_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = raw_dir / f"nightlights_RW_{snapshot_date}.parquet"
    csv_path = raw_dir / f"nightlights_RW_{snapshot_date}.csv"
    meta_path = raw_dir / f"nightlights_RW_{snapshot_date}.meta.json"
    frame = pd.DataFrame(records, columns=RAW_COLUMNS)
    meta = {"country": "RW", "product": "VNP46A2", "collection": "5200",
            "requested_start": start.isoformat(), "requested_end": end.isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(), "row_count": len(frame),
            "source_urls": sorted(source_urls),
            "granules": sorted(frame["granule_name"].dropna().unique().tolist()),
            "per_day_status": day_status, "find_latest_log": lookup_log}
    _atomic_parquet(frame, parquet_path)
    _atomic_csv(frame, csv_path)
    _atomic_json(meta, meta_path)
    return parquet_path, csv_path, meta_path


def _empty_row(row, day: str, h: int, v: int) -> dict:
    return {"cell_id": row.cell_id, "lat": row.lat, "lon": row.lon, "date": day,
            "h": h, "v": v, "granule_name": None, "nighttime_radiance": float("nan")}


def _find_latest_with_retries(token: str, h: int, v: int, day: date, days_back: int):
    for attempt in range(3):
        try:
            return nasa.find_latest(token, h, v, day, days_back, timeout_seconds=TIMEOUT_SECONDS)
        except requests.RequestException:
            if attempt == 2:
                raise
            LOG.warning("Retrying LAADS listing for %s h%02dv%02d (attempt %d/3)",
                        day, h, v, attempt + 2)
            time.sleep(attempt + 1)


def _get_with_retries(url: str, **kwargs):
    for attempt in range(3):
        try:
            return requests.get(url, **kwargs)
        except requests.RequestException:
            if attempt == 2:
                raise
            LOG.warning("Retrying LAADS download (attempt %d/3)", attempt + 2)
            time.sleep(attempt + 1)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(tmp, index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_json(value: dict, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date.today())
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        parquet, csv_path, meta = fetch(args.start, args.end, ROOT)
    except Exception:
        LOG.exception("Nightlights ingest failed")
        return 1
    LOG.info("Wrote %s, %s, and %s", parquet, csv_path, meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
