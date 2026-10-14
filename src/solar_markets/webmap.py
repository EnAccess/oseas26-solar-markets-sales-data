"""Step 6: interactive Folium map of the layers with sector popups.

Inputs:  outputs/<iso3>_ogs_*.tif, outputs/solar_share_calibrated.tif, outputs/grid_share_pred.tif,
         data/processed/feature_stack.tif, labels.gpkg, train_table.csv,
         reports/shap_values.csv, reports/calibration.json
Outputs: data/processed/sector_summary.gpkg   labels + predictions + top drivers per sector
         reports/top_underserved_sectors.csv  ranked list (field-check shortlist)
         docs/map.html                        the map (GitHub Pages)
Owner:   D (docs, map & pitch); see Part 12 of the team playbook.

    python -m solar_markets.webmap --config config.yml

The map opens on the underserved layer. Source layers can be switched on, and clicking a
sector shows its census and predicted numbers and the three features that moved its
prediction most (SHAP), so every priority zone can be traced back to its inputs.
"""

from __future__ import annotations

import json
from html import escape

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from branca.colormap import LinearColormap
from folium.raster_layers import ImageOverlay

from solar_markets.config import cli_args, get_paths, load_config
from solar_markets.export import layers, unserved_households
from solar_markets.features import Grid, area_zones, zone_means

FEATURE_LABELS = {
    "ntl": "night lights",
    "pop": "population density",
    "travel_min": "travel time to a city",
    "built": "built-up area",
    "rwi": "wealth (RWI)",
    "dist_grid": "distance to the grid",
}
SOURCE_LAYERS = {  # band -> (layer name, colormap, log)
    "ntl": ("Night lights (VIIRS 2022)", "inferno", True),
    "pop": ("Population (WorldPop 2020)", "viridis", True),
    "dist_grid": ("Distance to grid (Gridfinder)", "cividis", False),
    "rwi": ("Relative Wealth Index (Meta)", "RdYlGn", False),
}
TOP_N = 10
BASEMAPS = [  # (name, tile url, attribution); the first is shown by default
    ("Light grey basemap (Esri)",
     ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/"
      "MapServer/tile/{z}/{y}/{x}"),
     "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"),
    ("OpenStreetMap (online only)", "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
     "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors"),
]


# ---------------------------------------------------------------- sector summary

def zone_sums(zones: np.ndarray, n_zones: int, values: np.ndarray) -> np.ndarray:
    ok = (zones >= 0) & np.isfinite(values)
    return np.bincount(zones[ok], weights=values[ok], minlength=n_zones)


def top_drivers(shap: pd.DataFrame, values: pd.DataFrame, features: list[str], n: int = 3
                ) -> pd.Series:
    """Text like "low night lights (+4.1 pp); far ..." from per-area SHAP values.

    "low" / "high" compares the area's feature value with the median over all areas; the
    number is the feature's push on the predicted solar share, in percentage points.
    """
    medians = values[features].median()
    out = {}
    for area_id, row in shap.set_index("area_id")[features].iterrows():
        parts = []
        for f in row.abs().sort_values(ascending=False).index[:n]:
            level = "high" if values.at[area_id, f] >= medians[f] else "low"
            parts.append(f"{level} {FEATURE_LABELS.get(f, f)} ({100 * row[f]:+.1f} pp)")
        out[area_id] = "; ".join(parts)
    return pd.Series(out, name="top_drivers")


def sector_summary(labels: gpd.GeoDataFrame, solar: np.ndarray, grid_share: np.ndarray,
                   households: np.ndarray, grid: Grid, drivers: pd.Series) -> gpd.GeoDataFrame:
    labels = labels.to_crs(grid.crs).reset_index(drop=True)
    zones = area_zones(labels, grid)
    unserved = unserved_households(households, grid_share, solar)
    out = labels[["area_id", "sector", "district", "solar_share", "geometry"]].rename(
        columns={"solar_share": "census_solar_share"})
    out["pred_solar_share"] = zone_means(zones, len(labels), solar, households)
    out["pred_grid_share"] = zone_means(zones, len(labels), grid_share, households)
    out["households"] = zone_sums(zones, len(labels), households)
    out["unserved_hh"] = zone_sums(zones, len(labels), unserved)
    out["top_drivers"] = out["area_id"].map(drivers).fillna("n/a")
    out["rank_unserved"] = out["unserved_hh"].rank(ascending=False, method="first").astype(int)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=grid.crs)


# ---------------------------------------------------------------- map

def colour_overlay(a: np.ndarray, bounds, name: str, cmap: str, show: bool,
                   log: bool = False, vmin: float | None = None, vmax: float | None = None
                   ) -> ImageOverlay:
    """RGBA overlay of a raster, transparent where NaN, stretched between 2nd-98th pct."""
    from matplotlib import colormaps

    a = np.log1p(np.clip(a, 0, None)) if log else a
    lo = np.nanpercentile(a, 2) if vmin is None else vmin
    hi = np.nanpercentile(a, 98) if vmax is None else vmax
    scaled = np.clip((a - lo) / (hi - lo if hi > lo else 1), 0, 1)
    rgba = (colormaps[cmap](np.nan_to_num(scaled)) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.isnan(a), 0, 210)
    return ImageOverlay(rgba, bounds=[[bounds.bottom, bounds.left], [bounds.top, bounds.right]],
                        name=name, show=show, mercator_project=True)


def ranked_panel(top: gpd.GeoDataFrame) -> str:
    rows = "".join(
        f"<li><b>{escape(str(r.sector))}</b> ({escape(str(r.district))}): "
        f"{r.unserved_hh:,.0f} households</li>" for r in top.itertuples())
    return (
        '<div style="position:fixed;bottom:24px;left:12px;z-index:9999;max-width:290px;'
        'background:rgba(255,255,255,.93);padding:8px 12px;border-radius:6px;'
        'font:12px/1.35 sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.3)">'
        f"<b>Top {len(top)} underserved sectors</b><br>"
        "<span style='color:#555'>households with neither grid nor solar (model estimate)</span>"
        f'<ol style="margin:4px 0 0 18px;padding:0">{rows}</ol></div>'
    )


def build_map(summary: gpd.GeoDataFrame, rasters: dict[str, tuple[np.ndarray, object]],
              sources: dict[str, np.ndarray], bounds, title: str) -> folium.Map:
    centre = [(bounds.bottom + bounds.top) / 2, (bounds.left + bounds.right) / 2]
    m = folium.Map(location=centre, zoom_start=9, tiles=None, control_scale=True)
    # Esri's light grey basemap also loads when map.html is opened as a local file;
    # OpenStreetMap's servers refuse requests without a website address (HTTP 403).
    # Only the first is switched on; Leaflet would otherwise show the last one added.
    for i, (name, url, attr) in enumerate(BASEMAPS):
        folium.TileLayer(url, name=name, attr=attr, max_zoom=16, show=i == 0).add_to(m)

    under, pen = rasters["underserved"], rasters["penetration"]
    colour_overlay(under, bounds, "Underserved solar market (0-1)", "magma_r", True,
                   vmin=0, vmax=1).add_to(m)
    colour_overlay(pen, bounds, "Off-grid solar penetration (0-1)", "viridis", False,
                   vmin=0, vmax=1).add_to(m)
    for band, (name, cmap, log) in SOURCE_LAYERS.items():
        if band in sources:
            colour_overlay(sources[band], bounds, f"Source: {name}", cmap, False, log).add_to(m)

    popup_fields = ["sector", "district", "census_solar_share", "pred_solar_share",
                    "pred_grid_share", "unserved_hh", "rank_unserved", "top_drivers"]
    aliases = ["Sector", "District", "Census solar share (2022)", "Predicted solar share",
               "Predicted grid share", "Households unserved", "Rank (most unserved = 1)",
               "Top drivers (push on solar share)"]
    shown = summary.copy()
    for c in ("census_solar_share", "pred_solar_share", "pred_grid_share"):
        shown[c] = shown[c].map(lambda v: "n/a" if pd.isna(v) else f"{v:.1%}")
    shown["unserved_hh"] = shown["unserved_hh"].map(lambda v: f"{v:,.0f}")
    shown["geometry"] = shown.geometry.simplify(0.001, preserve_topology=True)
    folium.GeoJson(
        shown[[*popup_fields, "geometry"]], name="Sectors (click for details)",
        style_function=lambda f: {"fillOpacity": 0, "color": "#444", "weight": 0.4},
        highlight_function=lambda f: {"weight": 2, "color": "#000"},
        popup=folium.GeoJsonPopup(fields=popup_fields, aliases=aliases, max_width=360),
    ).add_to(m)

    top = summary.nsmallest(TOP_N, "rank_unserved")
    markers = folium.FeatureGroup(name=f"Top {TOP_N} underserved sectors")
    for r in top.itertuples():
        pt = r.geometry.representative_point()
        folium.Marker([pt.y, pt.x], icon=folium.Icon(color="red", icon="info-sign"),
                      tooltip=f"#{r.rank_unserved} {r.sector} ({r.district}): "
                              f"{r.unserved_hh:,.0f} unserved households").add_to(markers)
    markers.add_to(m)

    LinearColormap(["#fcfdbf", "#fc8961", "#b73779", "#51127c", "#000004"], vmin=0, vmax=1,
                   caption="Underserved solar market (1 = most households with neither grid "
                           "nor solar)").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    root = m.get_root()
    root.html.add_child(folium.Element(ranked_panel(top)))
    root.header.add_child(folium.Element(f"<title>{escape(title)}</title>"))
    return m


# ---------------------------------------------------------------- pipeline stage

def run(cfg: dict) -> None:
    paths = get_paths(cfg)
    features = list(cfg["features"])
    cal = json.loads((paths.reports / "calibration.json").read_text())

    def read(path):
        with rasterio.open(path) as src:
            a = src.read(1, masked=True).astype("float32")
            return a.filled(np.nan), src.bounds

    with rasterio.open(paths.processed / "feature_stack.tif") as src:
        stack = dict(zip(src.descriptions, src.read()))
        grid = Grid(src.transform, src.width, src.height, str(src.crs))
    solar, bounds = read(paths.outputs / "solar_share_calibrated.tif")
    grid_share, _ = read(paths.outputs / "grid_share_pred.tif")
    rasters = {layer["key"]: read(paths.outputs / layer["file"])[0] for layer in layers(cfg)}
    households = stack["pop"] / cal["avg_household_size"]

    shap = pd.read_csv(paths.reports / "shap_values.csv")
    shap = shap[shap["target"] == cfg["model"]["targets"][0]]
    train = pd.read_csv(paths.processed / "train_table.csv").set_index("area_id")
    drivers = top_drivers(shap, train, features)

    summary = sector_summary(gpd.read_file(paths.processed / "labels.gpkg"), solar, grid_share,
                             households, grid, drivers)
    summary.to_file(paths.processed / "sector_summary.gpkg", driver="GPKG")
    ranked = summary.sort_values("rank_unserved").drop(columns="geometry")
    ranked.to_csv(paths.reports / "top_underserved_sectors.csv", index=False)

    title = f"Underserved solar markets, {cfg['country']['name']} {cfg['reference_year']}"
    m = build_map(summary, rasters, stack, bounds, title)
    out = paths.docs / "map.html"
    m.save(str(out))
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print("Top underserved sectors:")
    print(ranked.head(TOP_N)[["rank_unserved", "sector", "district", "unserved_hh",
                              "top_drivers"]].to_string(index=False))


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
