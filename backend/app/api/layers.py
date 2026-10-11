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
        selected_model=metrics.get("selected_model", "not_trained"),
        features=metrics.get("features", []),
        underserved_threshold=settings.underserved_threshold,
        disclaimer=DISCLAIMER,
        training_labels=m.get("training_labels"),
    )


@router.get("/layers", response_model=list[LayerInfo], tags=["map"])
def layers(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> list[dict]:
    return map_service.layer_catalog(svc.cells(code))


@router.get("/map/layer/{layer_name}", tags=["map"], summary="GeoJSON choropleth for a layer")
def map_layer(layer_name: str, code: str = Depends(country_code),
              svc: DataService = Depends(service_dep)) -> dict:
    if layer_name not in map_service.LAYERS:
        raise HTTPException(404, f"Unknown layer '{layer_name}'. Available: {', '.join(map_service.LAYERS)}")
    try:
        return map_service.build_layer(
            svc.cells(code), svc.spec(code).deg, layer_name, svc.meta(code)["is_demo"]
        )
    except map_service.LayerUnavailableError as exc:
        raise HTTPException(503, str(exc))
    cells = svc.cells(code, include_nightlights=layer_name == "night_lights")
    return map_service.build_layer(cells, svc.spec(code).deg, layer_name, svc.meta(code)["is_demo"])


@router.get("/map/infrastructure", tags=["map"], summary="Grid lines and minigrids (GeoJSON)")
def infrastructure(code: str = Depends(country_code), svc: DataService = Depends(service_dep)) -> dict:
    return svc.infrastructure(code) or {"type": "FeatureCollection", "features": []}


@router.get("/raster/metadata", tags=["raster"])
def raster_metadata(code: str = Depends(country_code), svc: DataService = Depends(service_dep),
                    settings: Settings = Depends(settings_dep)) -> dict:
    svc.ensure(code)
    path = settings.outputs_path(code) / "solar_penetration.tif"
    if not path.exists():
        raise HTTPException(
            503,
            "Solar penetration raster is not available. The model has not been "
            "trained on the current dataset.",
        )
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
    svc.ensure(code)
    path = settings.outputs_path(code) / "solar_penetration.tif"
    if not path.exists():
        raise HTTPException(
            503,
            "Solar penetration raster is not available. The model has not been "
            "trained on the current dataset.",
        )
    return FileResponse(path, media_type="image/tiff", filename=f"solar_penetration_{code}.tif")


@router.get("/data-sources", response_model=list[DataSource], tags=["docs"])
def data_sources() -> list[dict]:
    return DATA_SOURCES


@router.get("/limitations", response_model=list[str], tags=["docs"])
def limitations() -> list[str]:
    return LIMITATIONS