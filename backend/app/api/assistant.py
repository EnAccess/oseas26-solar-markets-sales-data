"""AI assistant endpoint. Model calls stay on the backend; the API key is read from the environment."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..config import Settings
from ..services import assistant_service
from ..services.data_service import DataService
from .deps import country_code, service_dep, settings_dep

router = APIRouter(tags=["assistant"])


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class FocusedArea(BaseModel):
    name: str = Field(..., max_length=120)
    level: str = Field(..., max_length=20)
    cell_ids: list[str] = Field(default_factory=list, max_length=assistant_service.MAX_CELLS)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    selected_cell_ids: list[str] = Field(default_factory=list, max_length=assistant_service.MAX_CELLS)
    focused_cell_id: str | None = Field(None, max_length=16)
    focused_area: FocusedArea | None = None
    threshold: float | None = Field(None, ge=0, le=1)


@router.get("/assistant/status")
def status(settings: Settings = Depends(settings_dep)) -> dict:
    return {"configured": bool(settings.anthropic_api_key), "model": settings.assistant_model,
            "max_cells": assistant_service.MAX_CELLS}


@router.post("/assistant/ask")
def ask(req: AskRequest, code: str = Depends(country_code), svc: DataService = Depends(service_dep),
        settings: Settings = Depends(settings_dep)) -> dict:
    threshold = settings.underserved_threshold if req.threshold is None else req.threshold
    known = [c for c in req.selected_cell_ids if c not in svc.unknown_ids(code, req.selected_cell_ids)]
    focused = req.focused_cell_id if req.focused_cell_id and not svc.unknown_ids(code, [req.focused_cell_id]) else None
    area = None
    if req.focused_area:
        area_ids = [c for c in req.focused_area.cell_ids if c not in svc.unknown_ids(code, req.focused_area.cell_ids)]
        area = {"name": req.focused_area.name, "level": req.focused_area.level, "cell_ids": area_ids}
    return assistant_service.answer(
        svc, settings, code, req.question.strip(), [t.model_dump() for t in req.history], known, focused, threshold,
        focused_area=area,
    )
