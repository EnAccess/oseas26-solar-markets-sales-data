from __future__ import annotations

from fastapi import HTTPException, Query

from ..config import Settings, get_settings
from ..countries import COUNTRIES
from ..services.data_service import DataService, get_data_service


def settings_dep() -> Settings:
    return get_settings()


def service_dep() -> DataService:
    return get_data_service()


def country_code(country: str | None = Query(None, description="Country code, e.g. RW")) -> str:
    code = (country or get_settings().default_country).upper()
    if code not in COUNTRIES:
        raise HTTPException(404, f"Unknown country '{code}'. Available: {', '.join(COUNTRIES)}")
    return code
