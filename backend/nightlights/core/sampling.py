"""Nightlight statistics around points, streamed from the remote HDF5 tile."""
import math
from collections import defaultdict

import numpy as np

from ..config import GRID
from .catalog import resolve
from .remote import open_h5

LAYER = "Gap_Filled_DNB_BRDF-Corrected_NTL"
KM_PER_DEG = 111.32


def _scalar(value, default):
    return default if value is None else np.ravel(value)[0]


def _sample(f, b: dict, lat: float, lon: float, radius_km: float, threshold: float) -> dict:
    ds = f[GRID + LAYER]
    rows, cols = ds.shape
    res_y = (b["north"] - b["south"]) / rows
    res_x = (b["east"] - b["west"]) / cols
    fill = _scalar(ds.attrs.get("_FillValue"), None)
    scale = float(_scalar(ds.attrs.get("scale_factor"), 1.0))

    r_c = min(math.floor((b["north"] - lat) / res_y), rows - 1)
    c_c = min(math.floor((lon - b["west"]) / res_x), cols - 1)

    dlat = radius_km / KM_PER_DEG
    dlon = radius_km / (KM_PER_DEG * max(math.cos(math.radians(lat)), 1e-6))
    r0 = math.floor((b["north"] - (lat + dlat)) / res_y)
    r1 = math.floor((b["north"] - (lat - dlat)) / res_y) + 1
    c0 = math.floor((lon - dlon - b["west"]) / res_x)
    c1 = math.floor((lon + dlon - b["west"]) / res_x) + 1

    clipped = r0 < 0 or c0 < 0 or r1 > rows or c1 > cols  # buffer crosses the tile edge
    r0, c0, r1, c1 = max(r0, 0), max(c0, 0), min(r1, rows), min(c1, cols)
    raw = ds[r0:r1, c0:c1]  # only this window (and the chunks under it) crosses the network

    vals = raw.astype(np.float32) * scale
    bad = (raw == fill) if fill is not None else np.zeros(raw.shape, dtype=bool)
    vals[bad | (vals < 0)] = np.nan

    rr, cc = np.mgrid[r0:r1, c0:c1]
    plat = b["north"] - (rr + 0.5) * res_y
    plon = b["west"] + (cc + 0.5) * res_x
    dist = np.hypot((plat - lat) * KM_PER_DEG,
                    (plon - lon) * KM_PER_DEG * math.cos(math.radians(lat)))
    mask = (dist <= radius_km) | ((rr == r_c) & (cc == c_c))  # always include the point's own pixel

    inside = vals[mask]
    valid = inside[np.isfinite(inside)]
    stats = dict(n_pixels=int(inside.size),
                 valid_frac=round(valid.size / inside.size, 3) if inside.size else 0.0,
                 clipped=bool(clipped))
    if valid.size:
        stats.update(mean=round(float(valid.mean()), 3), median=round(float(np.median(valid)), 3),
                     max=round(float(valid.max()), 3),
                     lit_frac=round(float((valid > threshold).mean()), 3))
    else:
        stats.update(mean=None, median=None, max=None, lit_frac=None)
    return stats


def sample_points(item: dict, points: list, radius_km: float = 1.0, threshold: float = 1.0) -> list:
    """Read one remote window and sample every (lat, lon) in `points`."""
    if not points:
        return []
    with open_h5(item["url"]) as f:
        ds = f[GRID + LAYER]
        rows, cols = ds.shape
        bounds = item["bounds"]
        res_y = (bounds["north"] - bounds["south"]) / rows
        res_x = (bounds["east"] - bounds["west"]) / cols
        windows = []
        for lat, lon in points:
            dlat = radius_km / KM_PER_DEG
            dlon = radius_km / (KM_PER_DEG * max(math.cos(math.radians(lat)), 1e-6))
            r0 = math.floor((bounds["north"] - (lat + dlat)) / res_y)
            r1 = math.floor((bounds["north"] - (lat - dlat)) / res_y) + 1
            c0 = math.floor((lon - dlon - bounds["west"]) / res_x)
            c1 = math.floor((lon + dlon - bounds["west"]) / res_x) + 1
            clipped = r0 < 0 or c0 < 0 or r1 > rows or c1 > cols
            r_center = min(math.floor((bounds["north"] - lat) / res_y), rows - 1)
            c_center = min(math.floor((lon - bounds["west"]) / res_x), cols - 1)
            window = (max(r0, 0), min(r1, rows), max(c0, 0), min(c1, cols))
            windows.append((window, r_center, c_center, clipped))

        min_row = min(window[0][0] for window in windows)
        max_row = max(window[0][1] for window in windows)
        min_col = min(window[0][2] for window in windows)
        max_col = max(window[0][3] for window in windows)
        raw = ds[min_row:max_row, min_col:max_col]
        fill = _scalar(ds.attrs.get("_FillValue"), None)
        scale = float(_scalar(ds.attrs.get("scale_factor"), 1.0))
        vals = raw.astype(np.float32) * scale
        bad = (raw == fill) if fill is not None else np.zeros(raw.shape, dtype=bool)
        vals[bad | (vals < 0)] = np.nan
        rr, cc = np.mgrid[min_row:max_row, min_col:max_col]

        results = []
        for (lat, lon), (window, r_center, c_center, clipped) in zip(points, windows):
            r0, r1, c0, c1 = window
            local_vals = vals[r0 - min_row:r1 - min_row, c0 - min_col:c1 - min_col]
            local_rows = rr[r0 - min_row:r1 - min_row, c0 - min_col:c1 - min_col]
            local_cols = cc[r0 - min_row:r1 - min_row, c0 - min_col:c1 - min_col]
            pixel_lats = bounds["north"] - (local_rows + 0.5) * res_y
            pixel_lons = bounds["west"] + (local_cols + 0.5) * res_x
            distances = np.hypot(
                (pixel_lats - lat) * KM_PER_DEG,
                (pixel_lons - lon) * KM_PER_DEG * math.cos(math.radians(lat)),
            )
            mask = (distances <= radius_km) | ((local_rows == r_center) & (local_cols == c_center))
            inside = local_vals[mask]
            valid = inside[np.isfinite(inside)]
            stats = dict(n_pixels=int(inside.size),
                         valid_frac=round(valid.size / inside.size, 3) if inside.size else 0.0,
                         clipped=bool(clipped))
            if valid.size:
                stats.update(mean=round(float(valid.mean()), 3), median=round(float(np.median(valid)), 3),
                             max=round(float(valid.max()), 3),
                             lit_frac=round(float((valid > threshold).mean()), 3))
            else:
                stats.update(mean=None, median=None, max=None, lit_frac=None)
            results.append(stats)
        return results


def sample_radiance(points: list[tuple[float, float]], date: str | None = None,
                    radius_km: float = 1.0, threshold: float = 1.0) -> np.ndarray:
    """Return NASA radiance means for (latitude, longitude) points in input order."""
    groups = defaultdict(list)
    values = [None] * len(points)
    for index, (latitude, longitude) in enumerate(points):
        item = resolve(latitude, longitude, date)
        if item is None:
            raise RuntimeError(f"NASA has no nightlight file for ({latitude}, {longitude})")
        groups[item["file"]].append((index, item, latitude, longitude))

    for entries in groups.values():
        item = entries[0][1]
        coords = [(latitude, longitude) for _, _, latitude, longitude in entries]
        stats_rows = sample_points(item, coords, radius_km, threshold)
        for (index, _, latitude, longitude), stats in zip(entries, stats_rows):
            mean = stats.get("mean")
            if mean is None:
                raise RuntimeError(f"NASA nightlight pixels are unusable at ({latitude}, {longitude})")
            values[index] = mean
    return np.asarray(values, dtype=float)


# ============================================================================
# CHANGE: added below this line to satisfy `from core.sampling import sample_area`
# in api/main.py. Nothing above this line has been modified.
# ============================================================================


def _area(f, b: dict, west: float, south: float, east: float, north: float,
          max_pixels: int) -> dict:
    ds = f[GRID + LAYER]
    rows, cols = ds.shape
    res_y = (b["north"] - b["south"]) / rows
    res_x = (b["east"] - b["west"]) / cols
    fill = _scalar(ds.attrs.get("_FillValue"), None)
    scale = float(_scalar(ds.attrs.get("scale_factor"), 1.0))

    r0 = max(math.floor((b["north"] - north) / res_y), 0)
    r1 = min(math.ceil((b["north"] - south) / res_y), rows)
    c0 = max(math.floor((west - b["west"]) / res_x), 0)
    c1 = min(math.ceil((east - b["west"]) / res_x), cols)
    if r1 <= r0 or c1 <= c0:
        raise ValueError("Area is outside this tile")

    step = max(1, math.ceil(math.sqrt(((r1 - r0) * (c1 - c0)) / max_pixels)))
    raw = ds[r0:r1:step, c0:c1:step]

    vals = raw.astype(np.float32) * scale
    bad = (raw == fill) if fill is not None else np.zeros(raw.shape, dtype=bool)
    vals[bad | (vals < 0)] = np.nan

    n_rows, n_cols = vals.shape
    return dict(
        pixel_size_deg=round(res_x * step, 6),
        step=step,
        shape=[n_rows, n_cols],
        lats=[round(b["north"] - (r0 + i * step + 0.5) * res_y, 5) for i in range(n_rows)],
        lons=[round(b["west"] + (c0 + j * step + 0.5) * res_x, 5) for j in range(n_cols)],
        values=[
            [round(float(x), 2) if math.isfinite(x) else None for x in row]
            for row in vals
        ],
    )


def sample_area(item: dict, west: float, south: float, east: float,
                north: float, max_pixels: int = 2500) -> dict:
    """Open the remote file once and return a downsampled pixel grid for the box."""
    with open_h5(item["url"]) as f:
        return _area(f, item["bounds"], west, south, east, north, max_pixels)