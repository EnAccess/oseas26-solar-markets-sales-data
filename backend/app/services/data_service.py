"""Loads (and lazily builds) per-country artefacts and caches them in memory."""
from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache

import pandas as pd

from ..config import Settings, get_settings
from ..pipeline.spatial_processing import GridSpec

logger = logging.getLogger(__name__)


class DataNotReadyError(RuntimeError):
    pass


class DataService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _cells_path(self, code: str):
        """Canonical cell-features file written by pipeline/build.py."""
        return self.settings.processed_path(code) / "cells_features.csv"

    def _meta_path(self, code: str):
        return self.settings.processed_path(code) / "meta.json"

    def is_ready(self, code: str) -> bool:
        """Ready if the canonical cells CSV + meta exist.

        We intentionally do NOT require models/metrics.json here. The API can
        serve real feature data (population, wealth, etc.) without a trained
        model; the model-dependent layers will simply report as unavailable.
        """
        return self._cells_path(code).exists() and self._meta_path(code).exists()

    def ensure(self, code: str) -> None:
        """Build the dataset if it is missing.

        This runs the data pipeline only, never model training. Training is a
        separate, explicit step (python -m app.ml.train) that must be triggered
        by whoever owns the model pipeline.
        """
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
        self._cache.pop(code, None)

    @staticmethod
    def _optional_json(path):
        return json.loads(path.read_text()) if path.exists() else None

    def _load(self, code: str) -> dict:
        code = code.upper()
        if code not in self._cache:
            self.ensure(code)
            pdir = self.settings.processed_path(code)
            mdir = self.settings.models_path(code)
            meta = json.loads((pdir / "meta.json").read_text())
            self._cache[code] = {
                "cells": pd.read_csv(self._cells_path(code)),
                "meta": meta,
                "spec": GridSpec(**meta["grid_spec"]),
                # Optional artefacts: present only after an explicit training run.
                "metrics": self._optional_json(mdir / "metrics.json"),
                "importance": self._optional_json(mdir / "feature_importance.json"),
                "infrastructure": self._optional_json(pdir / "infrastructure.geojson"),
                "gogla": pd.read_csv(pdir / "gogla.csv") if (pdir / "gogla.csv").exists() else None,
            }
        return self._cache[code]

    def cells(self, code: str) -> pd.DataFrame:
        return self._load(code)["cells"]

    def meta(self, code: str) -> dict:
        return self._load(code)["meta"]

    def spec(self, code: str) -> GridSpec:
        return self._load(code)["spec"]

    def metrics(self, code: str) -> dict | None:
        return self._load(code)["metrics"]

    def importance(self, code: str) -> dict | None:
        return self._load(code)["importance"]

    def infrastructure(self, code: str) -> dict | None:
        return self._load(code)["infrastructure"]

    def gogla(self, code: str) -> pd.DataFrame | None:
        return self._load(code)["gogla"]


@lru_cache
def get_data_service() -> DataService:
    return DataService(get_settings())
