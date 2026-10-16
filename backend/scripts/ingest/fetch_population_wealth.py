"""Download the real population and relative-wealth inputs for Rwanda into data/raw/RW/.

  population.tif        WorldPop 2020, 1 km, unconstrained "people per pixel" (CC BY 4.0)
  relative_wealth.csv   Meta Relative Wealth Index via HDX (CC BY-NC 4.0)

Each download is recorded in data/raw/RW/<file>.meta.json (URL, licence, retrieval time, bytes).
Run from backend/:  python scripts/ingest/fetch_population_wealth.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "RW"

SOURCES = {
    "population.tif": {
        "url": "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/RWA/rwa_ppp_2020_1km_Aggregated.tif",
        "dataset": "WorldPop Global 2000-2020, 1 km aggregated, unconstrained (ppp)",
        "year": "2020",
        "unit": "people per pixel (~1 km)",
        "licence": "CC BY 4.0",
        "citation": "WorldPop (www.worldpop.org), University of Southampton. doi:10.5258/SOTON/WP00647",
    },
    "relative_wealth.csv": {
        "url": "https://data.humdata.org/dataset/76f2a2ea-ba50-40f5-b79c-db95d668b843/resource/"
               "254e5daf-1ab0-47db-b40d-4abc2476e4ab/download/rwa_relative_wealth_index.csv",
        "dataset": "Meta Relative Wealth Index - Rwanda (Humanitarian Data Exchange)",
        "year": "2021 (HDX dataset date range 2021-04-01 to 2023-02-17)",
        "unit": "RWI (relative, unitless; 0 = national mean)",
        "licence": "CC BY-NC 4.0",
        "citation": "Chi et al. (2022) Microestimates of wealth for all low- and middle-income countries. PNAS.",
    },
}


def download(name: str, info: dict) -> None:
    response = requests.get(info["url"], timeout=300, headers={"User-Agent": "OSEAS-solar-market-reality/1.0"})
    response.raise_for_status()
    (RAW / name).write_bytes(response.content)
    meta = {**info, "retrieved_at": datetime.now(timezone.utc).isoformat(), "bytes": len(response.content)}
    (RAW / f"{name}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{name}: {len(response.content):,} bytes")


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, info in SOURCES.items():
        download(name, info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
