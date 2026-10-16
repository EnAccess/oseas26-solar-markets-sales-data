"""Country configuration. Add a new country by adding one entry to COUNTRIES."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Country:
    code: str                                   # ISO-style short code, used in cell IDs
    name: str
    bbox: tuple[float, float, float, float]     # min_lon, min_lat, max_lon, max_lat
    utm_epsg: int                               # metric CRS used for distance calculations
    center: tuple[float, float]                 # lat, lon for the initial map view
    zoom: int = 8
    # Simplified outline used ONLY in demo mode. Real runs read data/raw/<code>/boundary.geojson.
    boundary: tuple[tuple[float, float], ...] | None = None
    # (name, lon, lat, weight) - used by the demo generator to place settlements and grid lines.
    cities: tuple[tuple[str, float, float, float], ...] = field(default_factory=tuple)


COUNTRIES: dict[str, Country] = {
    "RW": Country(
        code="RW",
        name="Rwanda",
        bbox=(28.80, -2.90, 30.95, -1.00),
        utm_epsg=32735,
        center=(-1.95, 29.87),
        zoom=8,
        boundary=(
            (28.86, -2.83), (28.87, -2.40), (29.00, -2.05), (29.10, -1.80), (29.25, -1.66),
            (29.35, -1.50), (29.60, -1.39), (29.92, -1.45), (30.15, -1.13), (30.47, -1.05),
            (30.80, -1.35), (30.89, -1.75), (30.85, -2.20), (30.65, -2.41), (30.35, -2.40),
            (30.10, -2.62), (29.85, -2.77), (29.55, -2.80), (29.20, -2.83),
        ),
        cities=(
            ("Kigali", 30.062, -1.944, 1.00),
            ("Huye", 29.739, -2.597, 0.45),
            ("Musanze", 29.635, -1.500, 0.50),
            ("Rubavu", 29.260, -1.678, 0.45),
            ("Rwamagana", 30.435, -1.949, 0.35),
            ("Muhanga", 29.739, -2.085, 0.35),
            ("Nyagatare", 30.328, -1.298, 0.30),
            ("Rusizi", 28.908, -2.485, 0.35),
        ),
    ),
}


def get_country(code: str) -> Country:
    try:
        return COUNTRIES[code.upper()]
    except KeyError as exc:
        raise KeyError(f"Unknown country '{code}'. Available: {', '.join(COUNTRIES)}") from exc
