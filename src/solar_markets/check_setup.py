"""Check that a teammate's environment is ready.

    python -m solar_markets.check_setup          # libraries, config, folders
    python -m solar_markets.check_setup --gee    # also connect to Earth Engine
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys

from solar_markets.config import DEFAULT_CONFIG, PROJECT_ROOT, get_paths, load_config

REQUIRED = [
    "numpy", "pandas", "yaml", "geopandas", "shapely", "pyproj", "rasterio", "rasterstats",
    "scipy", "sklearn", "lightgbm", "shap", "matplotlib", "folium", "pyreadstat", "ee", "dotenv",
]


def check_imports() -> bool:
    ok = True
    for name in REQUIRED:
        try:
            mod = importlib.import_module(name)
            print(f"  [ok]   {name} {getattr(mod, '__version__', '')}")
        except Exception as exc:  # noqa: BLE001 - report any import failure
            print(f"  [FAIL] {name}: {exc}")
            ok = False
    return ok


def check_gee() -> bool:
    import ee
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    project = os.getenv("GEE_PROJECT")
    if not project:
        print("  [FAIL] GEE_PROJECT not set. Copy .env.example to .env and fill it in.")
        return False
    try:
        ee.Initialize(project=project)
    except Exception:  # noqa: BLE001 - not authenticated yet
        print("  First run: opening a browser to authenticate with Earth Engine...")
        ee.Authenticate()
        ee.Initialize(project=project)
    band = ee.Image("USGS/SRTMGL1_003").bandNames().getInfo()[0]
    print(f"  [ok]   Earth Engine connected (project {project}, test band '{band}')")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gee", action="store_true", help="also test the Earth Engine connection")
    args = parser.parse_args()

    print(f"Python {sys.version.split()[0]}")
    print("Libraries:")
    ok = check_imports()

    print("Config and folders:")
    cfg = load_config(DEFAULT_CONFIG)
    paths = get_paths(cfg)
    paths.ensure()
    print(f"  [ok]   {DEFAULT_CONFIG.name}: {cfg['country']['name']}, year {cfg['reference_year']}")
    print(f"  [ok]   data folders under {PROJECT_ROOT}")

    if args.gee:
        print("Earth Engine:")
        ok = check_gee() and ok

    print("\nAll checks passed." if ok else "\nSome checks failed; see above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
