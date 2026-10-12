"""Selected-location reports (JSON / CSV / PDF) and location lookup."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import Settings
from ..services import location_service, report_service
from ..services.data_service import DataService
from .deps import country_code, service_dep, settings_dep

router = APIRouter(tags=["reports"])


class ReportRequest(BaseModel):
    cell_ids: list[str] = Field(..., description="Grid cell IDs to include, e.g. ['RW_0412']")
    threshold: float | None = Field(None, ge=0, le=1, description="Priority cut-off on the 0-1 score")
    title: str | None = Field(None, max_length=120)


def _report(req: ReportRequest, code: str, svc: DataService, settings: Settings) -> dict:
    threshold = settings.underserved_threshold if req.threshold is None else req.threshold
    try:
        return report_service.build_report(svc, code, req.cell_ids, threshold, req.title)
    except report_service.ReportError as exc:
        raise HTTPException(422, str(exc))


@router.post("/reports/summary", summary="Report data for selected cells (JSON)")
def report_summary(req: ReportRequest, code: str = Depends(country_code),
                   svc: DataService = Depends(service_dep), settings: Settings = Depends(settings_dep)) -> dict:
    return _report(req, code, svc, settings)


@router.post("/reports/csv", summary="Per-cell indicators for selected cells (CSV)")
def report_csv(req: ReportRequest, code: str = Depends(country_code),
               svc: DataService = Depends(service_dep), settings: Settings = Depends(settings_dep)) -> Response:
    report = _report(req, code, svc, settings)
    return Response(report_service.report_csv(report), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="solar-market-report.csv"'})


@router.post("/reports/pdf", summary="Selected-location report (PDF)")
def report_pdf(req: ReportRequest, code: str = Depends(country_code),
               svc: DataService = Depends(service_dep), settings: Settings = Depends(settings_dep)) -> Response:
    from ..services.report_pdf import report_pdf as render  # heavy imports (matplotlib) only when needed

    report = _report(req, code, svc, settings)
    return Response(render(report), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="solar-market-report.pdf"'})


@router.get("/locations/search", summary="Resolve a cell ID, coordinates, district or province")
def location_search(q: str = Query(..., min_length=1, max_length=120), code: str = Depends(country_code),
                    svc: DataService = Depends(service_dep)) -> dict:
    return location_service.resolve(q, svc.cells(code), svc.spec(code))


@router.get("/locations/areas", summary="District and province names available for lookup")
def location_areas(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    return location_service.list_areas(svc.cells(code))
