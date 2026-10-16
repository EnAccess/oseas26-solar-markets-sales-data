"""NASA LAADS file listing. Nothing is downloaded here."""
from datetime import date, timedelta
from time import monotonic

import requests

from ..config import COLLECTION, LAADS, PRODUCT

CONNECT_TIMEOUT_SECONDS = 3.05
READ_TIMEOUT_SECONDS = 8.0
LOOKUP_TIMEOUT_SECONDS = 30.0


def _day_path(year: int, doy: int) -> str:
    return f"allData/{COLLECTION}/{PRODUCT}/{year}/{doy:03d}"


def list_files(token: str, year: int, doy: int, h: int, v: int,
               timeout: tuple[float, float] = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)):
    """Return (file dicts for one tile on one day, short diagnostic string)."""
    # The folder must be part of the URL; a ?path= query is ignored and returns the root.
    r = requests.get(f"{LAADS}/api/v2/content/details/{_day_path(year, doy)}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    if r.status_code in (401, 403):
        raise PermissionError(f"NASA rejected the token (HTTP {r.status_code}). Generate a new one.")
    if r.status_code == 404:
        return [], "HTTP 404 (no folder for this day yet)"
    r.raise_for_status()

    body = r.json()
    items = body.get("content", []) if isinstance(body, dict) else body
    items = [i for i in items if isinstance(i, dict)]
    tile = f".h{h:02d}v{v:02d}."
    files = [i for i in items if tile in i.get("name", "") and i.get("name", "").endswith(".h5")]
    return files, f"{len(items)} entries listed, {len(files)} match tile h{h:02d}v{v:02d}"


def find_latest(token: str, h: int, v: int, day: date, days_back: int,
                timeout_seconds: float = LOOKUP_TIMEOUT_SECONDS):
    """Try `day`, then earlier days, until the tile is listed.
    Returns (files, date, log); files is [] if nothing was found."""
    log = []
    deadline = monotonic() + timeout_seconds
    for i in range(days_back + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(f"NASA file lookup exceeded {timeout_seconds:g} seconds")
        d = day - timedelta(days=i)
        doy = d.timetuple().tm_yday
        timeout = (min(CONNECT_TIMEOUT_SECONDS, remaining), min(READ_TIMEOUT_SECONDS, remaining))
        files, note = list_files(token, d.year, doy, h, v, timeout)
        log.append(f"{d} (day {doy:03d}): {note}")
        if files:
            return files, d, log
    return [], None, log