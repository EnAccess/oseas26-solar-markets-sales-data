"""Tile-grid geometry for VNP46 (10° x 10° geographic tiles)."""
import re

from ..config import TILE_DEG


def tile_for(lat: float, lon: float) -> tuple:
    """Return the (h, v) tile that contains a coordinate."""
    return int((lon + 180) // TILE_DEG), int((90 - lat) // TILE_DEG)


def tile_bounds(filename: str):
    """Return (west, east, south, north) parsed from an h##v## filename, or None."""
    m = re.search(r"\.h(\d{2})v(\d{2})\.", filename)
    if not m:
        return None
    h, v = int(m.group(1)), int(m.group(2))
    west, north = -180 + h * TILE_DEG, 90 - v * TILE_DEG
    return west, west + TILE_DEG, north - TILE_DEG, north