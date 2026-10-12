from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings
from ..schemas.schemas import FeatureImportanceResponse, GoglaComparison, ModelPerformance
from ..services import prediction_service
from ..services.data_service import DataService
from .deps import country_code, service_dep, settings_dep

router = APIRouter(tags=["model"])


def _require_metrics(code: str, svc: DataService) -> dict:
    metrics = svc.metrics(code)
    if not metrics:
        raise HTTPException(404, "No trained model is available. See the README section on training.")
    return metrics


@router.get("/model/performance", response_model=ModelPerformance)
def performance(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    m = _require_metrics(code, svc)
    status = svc.model_info(code)
    if m["is_demo"]:
        note = "Metrics were calculated on SYNTHETIC DEMO DATA and say nothing about real-world accuracy."
    else:
        note = ("Spatial CV holds out whole geographic blocks and is the more honest estimate "
                "for unsurveyed areas.")
    if not status["usable"]:
        note += " " + status["reason"]
    return {**m, "note": note, "usable": status["usable"]}


@router.get("/model/features", response_model=FeatureImportanceResponse)
def features(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    _require_metrics(code, svc)
    fi = svc.importance(code)
    if not fi:
        raise HTTPException(404, "Feature importance is not available.")
    return {**fi, "warning": "Feature importance indicates which variables contributed to model predictions. "
                             "It does not establish causality."}


@router.get("/gogla/comparison", response_model=GoglaComparison)
def gogla(code: str = Depends(country_code), svc: DataService = Depends(service_dep),
          settings: Settings = Depends(settings_dep)) -> GoglaComparison:
    return prediction_service.gogla_comparison(svc.cells(code), svc.gogla(code), svc.model_info(code),
                                               settings, svc.meta(code)["is_demo"])
