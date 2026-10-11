from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings
from ..countries import COUNTRIES
from ..schemas.schemas import CellDetails
from ..services import prediction_service
from ..services.data_service import DataService
from .deps import service_dep, settings_dep

router = APIRouter(tags=["cells"])


@router.get("/cells/{cell_id}", response_model=CellDetails)
def get_cell(cell_id: str, threshold: float | None = None, svc: DataService = Depends(service_dep),
             settings: Settings = Depends(settings_dep)) -> CellDetails:
    code = cell_id.split("_")[0].upper()
    if code not in COUNTRIES:
        raise HTTPException(404, f"Cell '{cell_id}' does not belong to a known country.")
    cells = svc.cells(code, include_nightlights=True)
    match = cells[cells["cell_id"] == cell_id]
    if match.empty:
        raise HTTPException(404, f"Cell '{cell_id}' not found.")
    return prediction_service.cell_details(
        match.iloc[0], code, svc.meta(code)["is_demo"],
        settings.underserved_threshold if threshold is None else threshold,
    )
