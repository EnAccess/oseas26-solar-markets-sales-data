"""Read a VNP46A2 HDF5 file into a ready-to-plot Dataset."""
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import streamlit as st

from ..config import GRID, GRID_GROUP, QUALITY_LAYER
from .tiles import tile_bounds


@dataclass
class Dataset:
    path: str
    layer: str
    step: int
    light: np.ndarray          # 2-D float32, NaN where invalid
    lons: np.ndarray
    lats: np.ndarray
    georef: bool               # False if tile id couldn't be parsed
    available: list            # layer names present in the file
    grid_attrs: dict
    meta: dict                 # scale, fill, native shape

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def valid(self) -> np.ndarray:
        return self.light[np.isfinite(self.light)]


def _scalar(value, default):
    return default if value is None else np.ravel(value)[0]


@st.cache_data(show_spinner="Reading HDF5 file…")
def _read(path: str, mtime: float, layer: str, step: int, mask_quality: bool):
    with h5py.File(path, "r") as f:
        group = f[GRID]
        if layer not in group:
            raise KeyError(f"Layer `{layer}` isn't in this file. Available: {', '.join(group.keys())}")

        ds = group[layer]
        raw = ds[::step, ::step]
        fill = _scalar(ds.attrs.get("_FillValue"), None)
        scale = float(_scalar(ds.attrs.get("scale_factor"), 1.0))
        offset = float(_scalar(ds.attrs.get("add_offset"), 0.0))

        data = raw.astype(np.float32) * scale + offset
        invalid = (raw == fill) if fill is not None else np.zeros(raw.shape, dtype=bool)
        data[invalid | (data < 0)] = np.nan

        if mask_quality and QUALITY_LAYER in group:
            data[group[QUALITY_LAYER][::step, ::step] != 0] = np.nan

        available = list(group.keys())
        attrs = {k: str(v) for k, v in f[GRID_GROUP].attrs.items()}
        meta = dict(scale=scale, fill=fill, shape=ds.shape)
    return data, available, attrs, meta


def _coords(path: str, shape, step: int):
    bounds = tile_bounds(Path(path).name)
    rows, cols = shape
    if bounds is None:
        return np.arange(cols), np.arange(rows), False
    west, east, south, north = bounds
    res_x = (east - west) / (cols * step)
    res_y = (north - south) / (rows * step)
    lons = west + (np.arange(cols) * step + 0.5) * res_x
    lats = north - (np.arange(rows) * step + 0.5) * res_y
    return lons, lats, True


def load_dataset(path: str, layer: str, step: int, mask_quality: bool) -> Dataset:
    data, available, attrs, meta = _read(path, Path(path).stat().st_mtime, layer, step, mask_quality)
    lons, lats, georef = _coords(path, data.shape, step)
    return Dataset(path, layer, step, data, lons, lats, georef, available, attrs, meta)
