"""Loads (and lazily builds) per-country artefacts and caches them in memory.

The processed CSV is parsed once and reused until one of its source files changes on disk
(e.g. after a night-lights ingest or a grid refresh), so requests never re-read CSVs.
"""
from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..config import Settings, get_settings
from ..pipeline.spatial_processing import GridSpec
from .market_gap import add_market_scores

logger = logging.getLogger(__name__)
MODEL_COLUMNS = ("predicted_solar_penetration", "observed_solar_penetration")


class DataNotReadyError(RuntimeError):
    pass


class DataService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[str, dict] = {}
        self._lock = threading.RLock()

    # ---- paths ----------------------------------------------------------------------
    def _cells_path(self, code: str) -> Path:
        return self.settings.processed_path(code) / "cells_features.csv"

    def _meta_path(self, code: str) -> Path:
        return self.settings.processed_path(code) / "meta.json"

    def _watched(self, code: str) -> list[Path]:
        return [
            self._cells_path(code), self._meta_path(code),
            self.settings.processed_path(code) / "infrastructure.geojson",
            self.settings.outputs_path(code) / "cells.csv",
            self.settings.models_path(code) / "metrics.json",
        ]

    def _signature(self, code: str) -> tuple:
        return tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in self._watched(code))

    def is_ready(self, code: str) -> bool:
        """Ready once the processed cells CSV and meta exist. A trained model is optional."""
        return self._cells_path(code).exists() and self._meta_path(code).exists()

    def ensure(self, code: str) -> None:
        """Build the processed dataset if missing. Never trains a model."""
        if self.is_ready(code):
            return
        with self._lock:
            if self.is_ready(code):
                return
            from ..pipeline.build import build_dataset

            logger.info("No dataset for %s - running build pipeline", code)
            try:
                build_dataset(self.settings, code)
            except Exception as exc:
                raise DataNotReadyError(str(exc)) from exc

    def reload(self, code: str) -> None:
        self._cache.pop(code.upper(), None)

    @staticmethod
    def _optional_json(path: Path):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # ---- model outputs ----------------------------------------------------------------
    @staticmethod
    def model_status(meta: dict, metrics: dict | None) -> dict:
        """Whether stored model predictions may be used with this dataset, and why."""
        if not metrics:
            return {"usable": False, "reason": "No trained model is available for this dataset."}
        if bool(metrics.get("is_demo")) != bool(meta.get("is_demo")):
            return {"usable": False, "reason": (
                "The stored model was trained on synthetic demo labels and does not describe this "
                "real dataset. Train on georeferenced survey labels (DHS/MICS/MTF clusters with GPS) "
                "to enable predicted penetration.")}
        if not meta.get("is_demo") and metrics.get("training_labels") != "real":
            return {"usable": False, "reason": "The stored model is not documented as trained on real labels."}
        return {"usable": True, "reason": "Model trained on labels from the same dataset.",
                "selected_model": metrics.get("selected_model"), "trained_at": metrics.get("trained_at")}

    def _merge_model_outputs(self, cells: pd.DataFrame, code: str, status: dict) -> pd.DataFrame:
        path = self.settings.outputs_path(code) / "cells.csv"
        if not status["usable"] or not path.exists():
            return cells
        model_cells = pd.read_csv(path)
        columns = [c for c in MODEL_COLUMNS if c in model_cells.columns]
        if not columns or set(model_cells["cell_id"]) != set(cells["cell_id"]):
            logger.warning("Ignoring model outputs for %s: cell IDs do not match the dataset", code)
            status.update(usable=False, reason="Model outputs do not match the current grid cells.")
            return cells
        return cells.merge(model_cells[["cell_id", *columns]], on="cell_id", how="left", validate="one_to_one")

    # ---- loading ---------------------------------------------------------------------
    def _load(self, code: str) -> dict:
        code = code.upper()
        cached = self._cache.get(code)
        if cached and cached["signature"] == self._signature(code):
            return cached
        with self._lock:
            self.ensure(code)
            signature = self._signature(code)
            pdir, mdir = self.settings.processed_path(code), self.settings.models_path(code)
            meta = json.loads(self._meta_path(code).read_text(encoding="utf-8"))
            metrics = self._optional_json(mdir / "metrics.json")
            status = self.model_status(meta, metrics)
            cells = pd.read_csv(self._cells_path(code))
            cells = self._merge_model_outputs(cells, code, status)
            cells = add_market_scores(cells, self.settings, model_trusted=status["usable"])
            self._cache[code] = {
                "signature": signature,
                "cells": cells,
                "index": cells.set_index("cell_id", drop=False),
                "meta": meta,
                "spec": GridSpec(**meta["grid_spec"]),
                "metrics": metrics,
                "model_status": status,
                "importance": self._optional_json(mdir / "feature_importance.json"),
                "infrastructure": self._optional_json(pdir / "infrastructure.geojson"),
                "gogla": pd.read_csv(pdir / "gogla.csv") if (pdir / "gogla.csv").exists() else None,
                "layers": {},  # GeoJSON cache, filled by map_service
            }
            return self._cache[code]

    def cells(self, code: str, include_nightlights: bool = True) -> pd.DataFrame:
        """All cells with features, survey fields and scores. (Argument kept for compatibility.)"""
        return self._load(code)["cells"]

    def cells_by_id(self, code: str, cell_ids: list[str]) -> pd.DataFrame:
        """Rows for the given IDs, in request order. Unknown IDs are skipped (see unknown_ids)."""
        index = self._load(code)["index"]
        known = [cid for cid in dict.fromkeys(cell_ids) if cid in index.index]
        return index.loc[known].reset_index(drop=True)

    def unknown_ids(self, code: str, cell_ids: list[str]) -> list[str]:
        index = self._load(code)["index"]
        return [cid for cid in dict.fromkeys(cell_ids) if cid not in index.index]

    def version(self, code: str) -> tuple:
        """Changes whenever a watched source file changes; used to key derived caches."""
        return self._load(code)["signature"]

    def meta(self, code: str) -> dict:
        return self._load(code)["meta"]

    def spec(self, code: str) -> GridSpec:
        return self._load(code)["spec"]

    def metrics(self, code: str) -> dict | None:
        return self._load(code)["metrics"]

    def model_info(self, code: str) -> dict:
        return self._load(code)["model_status"]

    def importance(self, code: str) -> dict | None:
        return self._load(code)["importance"]

    def infrastructure(self, code: str) -> dict | None:
        return self._load(code)["infrastructure"]

    def gogla(self, code: str) -> pd.DataFrame | None:
        return self._load(code)["gogla"]

    def layer_cache(self, code: str) -> dict:
        return self._load(code)["layers"]


@lru_cache
def get_data_service() -> DataService:
    return DataService(get_settings())
