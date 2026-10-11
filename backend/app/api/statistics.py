from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..config import Settings
from ..schemas.schemas import Statistics
from ..services import prediction_service
from ..services.data_service import DataService
from .deps import country_code, service_dep, settings_dep

router = APIRouter(tags=["statistics"])


@router.get("/statistics", response_model=Statistics)
def statistics(code: str = Depends(country_code), threshold: float | None = Query(None, ge=0, le=1),
               svc: DataService = Depends(service_dep), settings: Settings = Depends(settings_dep)) -> Statistics:
    t = settings.underserved_threshold if threshold is None else threshold
    return prediction_service.statistics(svc.cells(code, include_nightlights=False), svc.metrics(code), settings, code,
                                         svc.meta(code)["is_demo"], t)
