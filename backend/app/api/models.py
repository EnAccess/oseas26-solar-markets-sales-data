from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings
from ..schemas.schemas import FeatureImportanceResponse, GoglaComparison, ModelPerformance
from ..services import prediction_service
from ..services.data_service import DataService
from .deps import country_code, service_dep, settings_dep

router = APIRouter(tags=["model"])


@router.get("/model/performance", response_model=ModelPerformance)
def performance(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    m = svc.metrics(code)
    note = ("Metrics were calculated on SYNTHETIC DEMO DATA and say nothing about real-world accuracy."
            if m["is_demo"] else
            "Spatial CV holds out whole geographic blocks and is the more honest estimate for unsurveyed areas.")
    return {**m, "note": note}


@router.get("/model/features", response_model=FeatureImportanceResponse)
def features(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    fi = svc.importance(code)
    return {**fi, "warning": "Feature importance indicates which variables contributed to model predictions. "
                             "It does not establish causality."}


@router.get("/gogla/comparison", response_model=GoglaComparison)
def gogla(code: str = Depends(country_code), svc: DataService = Depends(service_dep),
          settings: Settings = Depends(settings_dep)) -> GoglaComparison:
    return prediction_service.gogla_comparison(svc.cells(code, include_nightlights=False), svc.gogla(code), settings, svc.meta(code)["is_demo"])
