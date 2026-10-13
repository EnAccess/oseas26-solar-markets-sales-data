from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings
from ..countries import COUNTRIES
from ..schemas.schemas import CellDetails
from ..services import prediction_service
from ..services.data_service import DataService
from .deps import service_dep, settings_dep

router = APIRouter(tags=["cells"])


def country_of(cell_id: str) -> str:
    code = cell_id.split("_")[0].upper()
    if code not in COUNTRIES:
        raise HTTPException(404, f"Cell '{cell_id}' does not belong to a known country.")
    return code


@router.get("/cells/{cell_id}", response_model=CellDetails)
def get_cell(cell_id: str, threshold: float | None = Query(None, ge=0, le=1),
             svc: DataService = Depends(service_dep), settings: Settings = Depends(settings_dep)) -> CellDetails:
    code = country_of(cell_id)
    cells = svc.cells(code)
    match = cells.index[cells["cell_id"] == cell_id]
    if match.empty:
        raise HTTPException(404, f"Cell '{cell_id}' not found.")
    return prediction_service.cell_details(
        cells.loc[match[0]], cells, code, svc.meta(code), svc.model_info(code),
        settings.underserved_threshold if threshold is None else threshold,
    )
