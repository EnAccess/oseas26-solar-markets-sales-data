"""Checks that exported layers meet the EAE requirements. Skipped until layers exist."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
import yaml

from solar_markets.config import PROJECT_ROOT

LAYERS = sorted((PROJECT_ROOT / "outputs").glob("*_ogs_*.tif"))
REQUIRED_META = ["direction", "reference_year", "method", "labels", "features", "limitations"]


@pytest.mark.skipif(not LAYERS, reason="no exported layers yet")
@pytest.mark.parametrize("tif", LAYERS, ids=lambda p: p.name)
def test_layer_is_eae_conformant(tif: Path):
    with rasterio.open(tif) as src:
        assert src.crs.to_epsg() == 4326
        a = src.read(1, masked=True)
    assert np.nanmin(a) >= 0 and np.nanmax(a) <= 1

    meta_file = tif.with_suffix(".yml")
    assert meta_file.exists(), f"missing metadata file {meta_file.name}"
    meta = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
    for key in REQUIRED_META:
        assert meta.get(key), f"'{key}' missing in {meta_file.name}"
