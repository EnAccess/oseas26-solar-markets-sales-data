"""Writers: GeoTIFF, GeoJSON and cell->polygon helpers shared with the API."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from .spatial_processing import GridSpec

NODATA = -9999.0


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v) if isinstance(v, (float, int, np.floating, np.integer)) else v


def cells_to_geojson(cells: pd.DataFrame, deg: float, properties: dict[str, str]) -> dict:
    """Build a FeatureCollection of square cells. `properties` maps output name -> column."""
    h = deg / 2
    feats = []
    cols = {out: cells[col].tolist() for out, col in properties.items()}
    for i, (lon, lat) in enumerate(zip(cells["lon"].to_numpy(), cells["lat"].to_numpy())):
        ring = [
            [round(lon - h, 5), round(lat - h, 5)], [round(lon + h, 5), round(lat - h, 5)],
            [round(lon + h, 5), round(lat + h, 5)], [round(lon - h, 5), round(lat + h, 5)],
            [round(lon - h, 5), round(lat - h, 5)],
        ]
        feats.append(
            {
                "type": "Feature",
                "properties": {k: _clean(v[i]) for k, v in cols.items()},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def write_geojson(cells: pd.DataFrame, spec: GridSpec, path: Path, columns: list[str]) -> None:
    fc = cells_to_geojson(cells, spec.deg, {c: c for c in columns})
    path.write_text(json.dumps(fc))


def write_raster(cells: pd.DataFrame, spec: GridSpec, column: str, path: Path) -> None:
    arr = np.full((spec.n_rows, spec.n_cols), NODATA, dtype="float32")
    arr[cells["row"].to_numpy(), cells["col"].to_numpy()] = cells[column].to_numpy(dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=spec.n_rows, width=spec.n_cols, count=1,
        dtype="float32", crs="EPSG:4326", transform=spec.transform, nodata=NODATA, compress="deflate",
    ) as dst:
        dst.write(arr, 1)
        dst.update_tags(1, name=column)
