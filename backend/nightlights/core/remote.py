"""Open a NASA HDF5 file over HTTPS without downloading it (reads only the bytes needed)."""
import os
from contextlib import contextmanager

import fsspec
import h5py
from aiohttp import ClientTimeout

from ..config import TOKEN_ENV
from .env import load_env


def get_token() -> str:
    load_env()
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise RuntimeError(f"{TOKEN_ENV} is not set (put it in backend/.env)")
    return token


@contextmanager
def open_h5(url: str):
    fs = fsspec.filesystem(
        "https",
        headers={"Authorization": f"Bearer {get_token()}"},
        client_kwargs={"timeout": ClientTimeout(total=30, connect=5, sock_read=20)},
    )
    raw = fs.open(url, "rb", block_size=2 * 1024 * 1024,
                  cache_type="blockcache", cache_options={"maxblocks": 64})
    try:
        with h5py.File(raw, "r") as f:
            yield f
    finally:
        raw.close()