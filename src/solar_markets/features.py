"""Step 2: build the 1 km feature stack and the training table.

Inputs:  Earth Engine datasets (night lights, population, travel time, land cover),
         Meta RWI CSV (data/raw/rwi), Gridfinder lines (data/raw/grid),
         district boundaries (country mask), data/processed/labels.gpkg
Outputs: data/processed/feature_stack.tif  one named band per feature, NaN outside the country
         data/processed/train_table.csv    one row per label area, one column per feature
         reports/feature_bands.png         quick-look of every band
Owner:   B (features); see Part 8 of the team playbook.

    python -m solar_markets.features --config config.yml

The stack keeps raw values; log transforms (`log_features` in config.yml) are applied by the
model stage. Training features are population-weighted means over each label area, so they
describe where people live inside the area (playbook 9.7, change of support).
"""

from __future__ import annotations

import math
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import rasterize

from solar_markets.config import (
    PROJECT_ROOT,
    cli_args,
    get_paths,
    load_config,
    use_system_certificates,
)

EE_BANDS = ("ntl", "pop", "travel_min", "built")
LOCAL_BANDS = ("rwi", "dist_grid")
KM_PER_DEG = 111.32


# ---------------------------------------------------------------- analysis grid

@dataclass(frozen=True)
class Grid:
    """The 1 km analysis grid: the country bbox snapped outward to whole pixels."""

    transform: Affine
    width: int
    height: int
    crs: str

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def res(self) -> float:
        return self.transform.a

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Longitude and latitude of every pixel centre, each shaped like the grid."""
        cols = self.transform.c + (np.arange(self.width) + 0.5) * self.transform.a
        rows = self.transform.f + (np.arange(self.height) + 0.5) * self.transform.e
        return np.meshgrid(cols, rows)

    def profile(self, count: int) -> dict:
        return {"driver": "GTiff", "width": self.width, "height": self.height, "count": count,
                "dtype": "float32", "crs": self.crs, "transform": self.transform,
                "nodata": np.nan, "compress": "deflate", "tiled": True,
                "blockxsize": 256, "blockysize": 256}


def make_grid(cfg: dict) -> Grid:
    res = cfg["grid"]["resolution_deg"]
    lon_min, lat_min, lon_max, lat_max = cfg["country"]["bbox"]
    # Snap to whole pixels; the small epsilon keeps exact multiples from shifting a pixel.
    x0, y0 = math.floor(lon_min / res + 1e-6), math.floor(lat_min / res + 1e-6)
    x1, y1 = math.ceil(lon_max / res - 1e-6), math.ceil(lat_max / res - 1e-6)
    transform = Affine(res, 0, x0 * res, 0, -res, y1 * res)
    return Grid(transform, width=x1 - x0, height=y1 - y0, crs=cfg["grid"]["crs"])


def country_mask(boundary_file: Path, grid: Grid) -> np.ndarray:
    """True for pixels whose centre lies inside the country (union of district polygons)."""
    shapes = gpd.read_file(boundary_file).to_crs(grid.crs).geometry
    return rasterize(((g, 1) for g in shapes), out_shape=grid.shape, transform=grid.transform,
                     fill=0, dtype="uint8").astype(bool)


# ---------------------------------------------------------------- Earth Engine bands

def init_ee():
    import ee
    from dotenv import load_dotenv

    use_system_certificates()
    load_dotenv(PROJECT_ROOT / ".env")
    project = os.getenv("GEE_PROJECT")
    if not project:
        raise RuntimeError("GEE_PROJECT not set. Copy .env.example to .env and fill it in.")
    try:
        ee.Initialize(project=project)
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine is not authenticated. Run: python -m solar_markets.check_setup --gee"
        ) from exc
    return ee


def ee_image(ee, fd: dict, iso3: str, grid: Grid):
    """Earth Engine bands aggregated onto the analysis grid (population as counts, everything else as means)."""
    proj = ee.Projection(grid.crs, list(grid.transform)[:6])

    def to_grid(img, reducer):
        return img.reduceResolution(reducer, maxPixels=65535).reproject(proj)

    y = fd["ntl"]["year"]
    ntl = (ee.ImageCollection(fd["ntl"]["collection"])
           .filterDate(f"{y}-01-01", f"{y + 1}-01-01").first().select(fd["ntl"]["band"]))
    pop = (ee.ImageCollection(fd["pop"]["collection"])
           .filter(ee.Filter.eq("country", iso3)).filter(ee.Filter.eq("year", fd["pop"]["year"]))
           .first().select(fd["pop"]["band"]))
    travel = ee.Image(fd["travel_min"]["image"]).select(fd["travel_min"]["band"])
    built = (ee.ImageCollection(fd["built"]["collection"]).first()
             .select(fd["built"]["band"]).eq(fd["built"]["class"]))

    # Population counts: average the density (people per m2) and multiply by the output pixel
    # area. A weighted Reducer.sum() returns a mean here, and an unweighted one double-counts
    # 100 m cells that straddle two output pixels.
    density = pop.divide(ee.Image.pixelArea())
    pop_count = to_grid(density, ee.Reducer.mean()).multiply(ee.Image.pixelArea().reproject(proj))

    bands = [to_grid(ntl, ee.Reducer.mean()), pop_count,
             to_grid(travel, ee.Reducer.mean()), to_grid(built, ee.Reducer.mean())]
    return ee.Image.cat(bands).rename(list(EE_BANDS)).toFloat().unmask(-9999)


def download_ee_stack(cfg: dict, grid: Grid, out: Path) -> None:
    ee = init_ee()
    image = ee_image(ee, cfg["feature_data"], cfg["country"]["iso3"], grid)
    url = image.getDownloadURL({
        "format": "GEO_TIFF",
        "crs": grid.crs,
        "crs_transform": list(grid.transform)[:6],
        "dimensions": f"{grid.width}x{grid.height}",
    })
    print(f"Downloading Earth Engine bands to {out.name} ...")
    urllib.request.urlretrieve(url, out)


def read_ee_stack(path: Path, grid: Grid) -> dict[str, np.ndarray]:
    with rasterio.open(path) as src:
        if (src.height, src.width) != grid.shape or not src.transform.almost_equals(grid.transform):
            raise ValueError(f"{path.name} is not on the analysis grid; delete it and re-run")
        a = src.read().astype("float32")
    a[a <= -9999] = np.nan
    return dict(zip(EE_BANDS, a))


# ---------------------------------------------------------------- local bands

def rwi_band(rwi: pd.DataFrame, grid: Grid) -> np.ndarray:
    """Relative Wealth Index of the nearest RWI point (~2.4 km apart) for every pixel."""
    from sklearn.neighbors import BallTree

    tree = BallTree(np.radians(rwi[["latitude", "longitude"]].values), metric="haversine")
    lon, lat = grid.centres()
    _, idx = tree.query(np.radians(np.c_[lat.ravel(), lon.ravel()]), k=1)
    return rwi["rwi"].to_numpy()[idx[:, 0]].reshape(grid.shape).astype("float32")


def load_grid_lines(fd: dict, raw: Path, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Gridfinder lines inside `bbox`; the country clip is cached so the global file is read once."""
    clipped = raw / fd["grid_clipped"]
    if clipped.exists():
        return gpd.read_file(clipped)
    source = raw / fd["grid"]
    if not source.exists():
        raise FileNotFoundError(f"{source} not found; see data/README.md (Gridfinder)")
    print(f"Clipping {source.name} to the country (once) ...")
    lines = gpd.read_file(source, bbox=bbox)
    lines.to_file(clipped, driver="GPKG")
    return lines


def dist_grid_band(lines: gpd.GeoDataFrame, grid: Grid, pad_km: float) -> np.ndarray:
    """Kilometres from each pixel centre to the nearest grid-line pixel.

    The raster is padded by `pad_km` so lines just across the border count, then cropped.
    """
    from scipy.ndimage import distance_transform_edt

    pad = math.ceil(pad_km / (grid.res * KM_PER_DEG))
    t = grid.transform
    padded = Affine(t.a, 0, t.c - pad * t.a, 0, t.e, t.f - pad * t.e)
    shape = (grid.height + 2 * pad, grid.width + 2 * pad)
    lines = lines.to_crs(grid.crs)
    burn = rasterize(((g, 1) for g in lines.geometry if g is not None and not g.is_empty),
                     out_shape=shape, transform=padded, fill=0, all_touched=True, dtype="uint8")
    if not burn.any():
        raise ValueError("No grid lines fall inside the padded country extent")

    _, lat = grid.centres()
    km_y = grid.res * KM_PER_DEG
    km_x = km_y * math.cos(math.radians(float(lat.mean())))
    dist = distance_transform_edt(burn == 0, sampling=(km_y, km_x))
    return dist[pad:pad + grid.height, pad:pad + grid.width].astype("float32")


# ---------------------------------------------------------------- stack and training table

def write_stack(bands: dict[str, np.ndarray], names: list[str], grid: Grid, out: Path) -> None:
    with rasterio.open(out, "w", **grid.profile(len(names))) as dst:
        for i, name in enumerate(names, start=1):
            dst.write(bands[name].astype("float32"), i)
            dst.set_band_description(i, name)


def check_bands(bands: dict[str, np.ndarray], names: list[str]) -> None:
    for name in names:
        a = bands[name]
        if np.isnan(a).all() or np.nanmax(np.abs(a)) == 0:
            raise ValueError(f"Band '{name}' is empty (all NaN or all zero)")
        print(f"  {name:11s} min {np.nanmin(a):10.3f}  median {np.nanmedian(a):10.3f}  "
              f"max {np.nanmax(a):10.3f}")


def zone_means(zones: np.ndarray, n_zones: int, values: np.ndarray,
               weights: np.ndarray) -> np.ndarray:
    """Weighted mean of `values` per zone id (0..n_zones-1); -1 marks pixels in no zone.

    Zones whose pixels all have zero weight fall back to the plain mean.
    """
    ok = (zones >= 0) & ~np.isnan(values)
    z, v, w = zones[ok], values[ok], np.nan_to_num(weights[ok])
    wsum = np.bincount(z, weights=w, minlength=n_zones)
    wmean = np.bincount(z, weights=w * v, minlength=n_zones) / np.where(wsum > 0, wsum, 1)
    count = np.bincount(z, minlength=n_zones)
    mean = np.bincount(z, weights=v, minlength=n_zones) / np.where(count > 0, count, 1)
    out = np.where(wsum > 0, wmean, mean)
    return np.where(count > 0, out, np.nan)


def area_zones(labels: gpd.GeoDataFrame, grid: Grid) -> np.ndarray:
    """Zone id (row number in `labels`) for each pixel, by pixel centre.

    Areas too small to contain a pixel centre get the pixel under their representative point.
    """
    shapes = ((g, i) for i, g in enumerate(labels.geometry))
    zones = rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=-1,
                      dtype="int32")
    present = np.zeros(len(labels), dtype=bool)
    present[np.unique(zones[zones >= 0])] = True
    for i in np.flatnonzero(~present):
        pt = labels.geometry.iloc[i].representative_point()
        r, c = rasterio.transform.rowcol(grid.transform, pt.x, pt.y)
        if 0 <= r < grid.height and 0 <= c < grid.width:
            zones[r, c] = i
    return zones


def training_table(labels: gpd.GeoDataFrame, bands: dict[str, np.ndarray], names: list[str],
                   grid: Grid) -> pd.DataFrame:
    labels = labels.to_crs(grid.crs).reset_index(drop=True)
    zones = area_zones(labels, grid)
    pop = bands["pop"]
    table = pd.DataFrame({"area_id": labels["area_id"]})
    for name in names:
        # Population itself is a plain mean (people per pixel); everything else is weighted
        # by population so it describes where people live.
        w = np.ones_like(pop) if name == "pop" else pop
        table[name] = zone_means(zones, len(labels), bands[name], w)
    table["n_pixels"] = np.bincount(zones[zones >= 0], minlength=len(labels))
    return table.merge(pd.DataFrame(labels.drop(columns="geometry")), on="area_id")


def save_quicklook(bands: dict[str, np.ndarray], names: list[str], log_features: list[str],
                   out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ncols = 3
    nrows = math.ceil(len(names) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.6 * nrows))
    for ax, name in zip(np.ravel(axes), names):
        a = bands[name]
        if name in log_features:
            a, name = np.log1p(np.clip(a, 0, None)), f"log1p({name})"
        im = ax.imshow(a, cmap="viridis")
        fig.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title(name)
    for ax in np.ravel(axes):
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------- pipeline stage

def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    fd = cfg["feature_data"]
    names = list(cfg["features"])
    unknown = set(names) - set(EE_BANDS) - set(LOCAL_BANDS)
    if unknown:
        raise ValueError(f"No builder for features {sorted(unknown)}")

    grid = make_grid(cfg)
    print(f"Analysis grid: {grid.width} x {grid.height} pixels of {grid.res:.6f} deg")
    mask = country_mask(paths.raw / cfg["labels"]["boundaries"]["district"], grid)

    ee_path = paths.interim / fd["ee_stack"]
    if not ee_path.exists():
        download_ee_stack(cfg, grid, ee_path)
    else:
        print(f"Using cached {ee_path.name} (delete it to re-download)")
    bands = read_ee_stack(ee_path, grid)

    bands["rwi"] = rwi_band(pd.read_csv(paths.raw / fd["rwi"]), grid)
    pad = fd["grid_pad_km"] / KM_PER_DEG
    lon_min, lat_min, lon_max, lat_max = cfg["country"]["bbox"]
    lines = load_grid_lines(fd, paths.raw, (lon_min - pad, lat_min - pad, lon_max + pad,
                                            lat_max + pad))
    bands["dist_grid"] = dist_grid_band(lines, grid, fd["grid_pad_km"])

    for name in bands:
        bands[name] = np.where(mask, bands[name], np.nan).astype("float32")
    print("Bands inside the country:")
    check_bands(bands, names)

    stack_path = paths.processed / "feature_stack.tif"
    write_stack(bands, names, grid, stack_path)
    save_quicklook(bands, names, cfg.get("log_features", []), paths.reports / "feature_bands.png")
    print(f"Wrote {stack_path} ({len(names)} bands)")

    labels_path = paths.processed / "labels.gpkg"
    if not labels_path.exists():
        print(f"{labels_path.name} not found; run solar_markets.labels for the training table")
        return
    table = training_table(gpd.read_file(labels_path), bands, names, grid)
    missing = table[names].isna().any(axis=1).sum()
    if missing:
        print(f"  warning: {missing} areas have a missing feature value")
    table.to_csv(paths.processed / "train_table.csv", index=False)
    print(f"Wrote {paths.processed / 'train_table.csv'} ({len(table)} areas)")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
