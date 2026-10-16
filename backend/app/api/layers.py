"""Health, countries, layers, map data, infrastructure, raster metadata, documentation content."""
from __future__ import annotations

import rasterio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..config import Settings
from ..countries import COUNTRIES
from ..data_sources import DATA_SOURCES, LIMITATIONS
from ..schemas.schemas import AppMeta, CountryInfo, DataSource, HealthResponse, LayerInfo
from ..services import map_service
from ..services.indicators import source_date
from ..services.market_gap import METHOD
from ..services.data_service import DataService
from .deps import country_code, service_dep, settings_dep

router = APIRouter()

DISCLAIMER = ("Model estimates indicate potentially underserved areas that require further investigation. "
              "They do not prove commercial viability.")


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/countries", response_model=list[CountryInfo], tags=["system"])
def countries(svc: DataService = Depends(service_dep)) -> list[CountryInfo]:
    return [CountryInfo(code=c.code, name=c.name, center=c.center, zoom=c.zoom, bbox=c.bbox,
                        ready=svc.is_ready(c.code)) for c in COUNTRIES.values()]


@router.get("/meta", response_model=AppMeta, tags=["system"])
def meta(code: str = Depends(country_code), svc: DataService = Depends(service_dep),
         settings: Settings = Depends(settings_dep)) -> AppMeta:
    m = svc.meta(code)
    metrics = svc.metrics(code) or {}
    return AppMeta(
        country=code,
        country_name=m["country_name"],
        is_demo=m["is_demo"],
        grid_resolution_km=m["grid_spec"]["res_km"],
        n_cells=m["n_cells"],
        n_labelled_cells=m["n_labelled_cells"],
        bounds=m["bounds"],
        selected_model=(metrics.get("selected_model", "not_trained") if svc.model_info(code)["usable"]
                        else "not_available"),
        features=metrics.get("features", []),
        underserved_threshold=settings.underserved_threshold,
        disclaimer=DISCLAIMER,
        training_labels=m.get("training_labels"),
        built_at=m.get("built_at"),
        sources=m.get("sources", {}),
        assumptions=m.get("assumptions", {}),
        model_status=svc.model_info(code),
        method=METHOD,
    )


@router.get("/layers", response_model=list[LayerInfo], tags=["map"])
def layers(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> list[dict]:
    return map_service.layer_catalog(svc.cells(code), svc.meta(code).get("sources", {}))


@router.get("/map/layer/{layer_name}", tags=["map"], summary="GeoJSON choropleth for a layer")
def map_layer(layer_name: str, code: str = Depends(country_code),
              svc: DataService = Depends(service_dep)) -> dict:
    if layer_name not in map_service.LAYERS:
        raise HTTPException(404, f"Unknown layer '{layer_name}'. Available: {', '.join(map_service.LAYERS)}")
    cells = svc.cells(code)
    if layer_name not in map_service.available_layers(cells):
        raise HTTPException(404, f"Layer '{layer_name}' has no data for {code}.")
    try:
        return map_service.cached_layer(svc, code, layer_name)
    except map_service.LayerUnavailableError as exc:
        raise HTTPException(503, str(exc))


@router.get("/map/infrastructure", tags=["map"], summary="Mapped electricity infrastructure (GeoJSON)")
def infrastructure(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    data = svc.infrastructure(code) or {"type": "FeatureCollection", "features": []}
    sources = svc.meta(code).get("sources", {})
    kinds: dict[str, int] = {}
    for feature in data.get("features", []):
        kind = feature.get("properties", {}).get("kind", "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return {**data, "metadata": {
        "counts": kinds,
        "grid_source": sources.get("grid", {}),
        "minigrid_source": sources.get("minigrids", {}),
        "caveat": "Mapped infrastructure from OpenStreetMap is incomplete, and a mapped line does not "
                  "mean nearby households are connected.",
    }}


def _usable_raster(code: str, svc: DataService, settings: Settings):
    """The model raster is served only when the model is usable for this dataset."""
    status = svc.model_info(code)
    path = settings.outputs_path(code) / "solar_penetration.tif"
    if not status["usable"] or not path.exists():
        raise HTTPException(503, f"Solar penetration raster is not available. {status['reason']}")
    return path


@router.get("/raster/metadata", tags=["raster"])
def raster_metadata(code: str = Depends(country_code), svc: DataService = Depends(service_dep),
                    settings: Settings = Depends(settings_dep)) -> dict:
    path = _usable_raster(code, svc, settings)
    with rasterio.open(path) as src:
        return {
            "file": path.name, "crs": str(src.crs), "width": src.width, "height": src.height,
            "bounds": list(src.bounds), "resolution_deg": src.res[0],
            "resolution_km": svc.spec(code).res_km,
            "nodata": src.nodata, "dtype": src.dtypes[0], "value_range": [0.0, 1.0],
            "download_url": f"/api/raster/solar_penetration.tif?country={code}",
            "is_demo": svc.meta(code)["is_demo"],
        }


@router.get("/raster/solar_penetration.tif", tags=["raster"])
def raster_download(code: str = Depends(country_code), svc: DataService = Depends(service_dep),
                    settings: Settings = Depends(settings_dep)) -> FileResponse:
    path = _usable_raster(code, svc, settings)
    return FileResponse(path, media_type="image/tiff", filename=f"solar_penetration_{code}.tif")


@router.get("/data-sources", response_model=list[DataSource], tags=["docs"])
def data_sources(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> list[dict]:
    meta = svc.meta(code)
    loaded = meta.get("sources", {})
    out = []
    for doc in DATA_SOURCES:
        info = loaded.get(doc["meta_key"], {})
        status = "synthetic" if meta.get("is_demo") else info.get("status", "missing")
        out.append({**doc, "status": status, "date": source_date(info), "licence": info.get("licence"),
                    "file": info.get("file"), "retrieved_at": info.get("retrieved_at"),
                    "note": info.get("note")})
    return out


@router.get("/limitations", response_model=list[str], tags=["docs"])
def limitations() -> list[str]:
    return LIMITATIONS
