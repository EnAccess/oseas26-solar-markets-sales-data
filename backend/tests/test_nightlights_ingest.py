import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest
import requests

from scripts.ingest import fetch_nightlights
from app.services.data_service import DataService


def _root(tmp_path: Path) -> Path:
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "data/processed/RW").mkdir(parents=True)
    pd.DataFrame([{"cell_id": "cell-1", "lat": -1.9, "lon": 29.9}]).to_csv(
        tmp_path / "data/processed/RW/cells_features.csv", index=False
    )
    return tmp_path


def _response(status: int, body=None, content=b""):
    response = Mock()
    response.status_code = status
    response.content = content
    response.json.return_value = body or {"content": []}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    else:
        response.raise_for_status.return_value = None
    return response


@patch.object(fetch_nightlights, "get_token", return_value="token")
@patch.object(fetch_nightlights.requests, "get")
def test_401_is_permission_error_and_writes_no_snapshot(mock_get, _token, tmp_path):
    mock_get.return_value = _response(401)
    root = _root(tmp_path)
    with pytest.raises(PermissionError):
        fetch_nightlights.fetch(date(2026, 1, 1), date(2026, 1, 1), root)
    assert not list((root / "data/raw").glob("nightlights_RW_*.parquet"))
    assert not list((root / "data/raw").glob("nightlights_RW_*.csv"))
    assert any(isinstance(call[1].get("headers", {}).get("Authorization"), str)
               for call in mock_get.call_args_list)


@patch.object(fetch_nightlights, "get_token", return_value="token")
@patch.object(fetch_nightlights.requests, "get")
def test_all_404_is_logged_no_data_without_fabricating_values(mock_get, _token, tmp_path):
    mock_get.return_value = _response(404)
    root = _root(tmp_path)
    parquet_path, csv_path, meta_path = fetch_nightlights.fetch(date(2026, 1, 1), date(2026, 1, 1), root)
    frame = pd.read_parquet(parquet_path)
    csv_frame = pd.read_csv(csv_path)
    meta = json.loads(meta_path.read_text())
    assert meta["per_day_status"]["2026-01-01"]["status"] == "no_data"
    assert frame["nighttime_radiance"].isna().all()
    assert frame["granule_name"].isna().all()
    assert csv_frame["nighttime_radiance"].isna().all()


@patch.object(fetch_nightlights, "get_token", return_value="token")
@patch.object(fetch_nightlights.requests, "get", side_effect=requests.Timeout("network timeout"))
def test_timeout_returns_nonzero_and_preserves_prior_snapshot(mock_get, _token, tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(fetch_nightlights, "ROOT", root)
    old = root / "data/raw/nightlights_RW_2026-01-01.parquet"
    old.write_bytes(b"previous snapshot")
    old_csv = root / "data/raw/nightlights_RW_2026-01-01.csv"
    old_csv.write_text("previous snapshot")
    assert fetch_nightlights.main(["--start", "2026-01-01", "--end", "2026-01-01"]) == 1
    assert old.read_bytes() == b"previous snapshot"
    assert old_csv.read_text() == "previous snapshot"
    assert mock_get.called


def test_data_service_cells_makes_zero_http_calls(tmp_path):
    processed = tmp_path / "processed/RW"
    processed.mkdir(parents=True)
    pd.DataFrame([{"cell_id": "cell-1", "lat": -1.9, "lon": 29.9,
                   "nighttime_radiance": np.nan}]).to_csv(processed / "cells_features.csv", index=False)
    (processed / "meta.json").write_text(json.dumps({
        "grid_spec": {"min_lon": 29.0, "max_lat": -1.0, "deg": 0.1,
                      "n_rows": 1, "n_cols": 1, "res_km": 5.0},
        "is_demo": True,
    }))
    settings = SimpleNamespace(
        processed_path=lambda _code: processed,
        models_path=lambda _code: tmp_path / "models/RW",
        outputs_path=lambda _code: tmp_path / "outputs/RW",
        need_w_population=0.4, need_w_grid_distance=0.4, need_w_darkness=0.2,
    )
    service = DataService(settings)
    with patch("requests.get") as mock_get:
        cells = service.cells("RW", include_nightlights=True)
    # The API reads only processed files: no NASA call, and missing radiance stays missing.
    assert cells["nighttime_radiance"].isna().all()
    assert cells["market_gap_score"].isna().all()
    mock_get.assert_not_called()
