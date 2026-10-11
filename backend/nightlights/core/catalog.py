"""Finds which NASA file covers a point. NASA is the source of truth; nothing is stored locally."""
import time
from datetime import date, datetime

from ..config import COLLECTION, LAADS, PRODUCT
from . import nasa
from .remote import get_token
from .tiles import tile_bounds, tile_for

_TTL = 3600  # seconds to remember a successful lookup
_cache: dict = {}


def resolve(lat: float, lon: float, on: str = None, days_back: int = 14):
    """Return info about the file covering (lat, lon), or None.
    on = 'YYYY-MM-DD' for an exact day, or None for the newest available."""
    h, v = tile_for(lat, lon)
    key = (h, v, on)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]

    if on:
        day, back = datetime.strptime(on, "%Y-%m-%d").date(), 0
    else:
        day, back = date.today(), days_back
    files, found, _ = nasa.find_latest(get_token(), h, v, day, back)
    if not files:
        return None

    f = files[0]
    doy = found.timetuple().tm_yday
    url = f.get("downloadsLink") or f"{LAADS}/archive/allData/{COLLECTION}/{PRODUCT}/{found.year}/{doy:03d}/{f['name']}"
    west, east, south, north = tile_bounds(f["name"])
    item = dict(
        file=f["name"], url=url, date=found.isoformat(), tile=f"h{h:02d}v{v:02d}",
        product=PRODUCT, size_mb=round(f.get("size", 0) / 1e6, 1),
        bounds=dict(west=west, east=east, south=south, north=north),
    )
    _cache[key] = (time.time(), item)
    return item