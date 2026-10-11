"""Solar Market Reality API.  Run:  uvicorn app.main:app --reload"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .api import cells, layers, models, statistics
from .config import get_settings
from .services.data_service import DataNotReadyError, get_data_service
from nightlights.api.main import app as nasa_nightlights_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("solar_market_reality")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        get_data_service().ensure(settings.default_country)
        logger.info("Artefacts ready (DEMO_MODE=%s)", settings.demo_mode)
    except DataNotReadyError:
        logger.exception("Could not prepare data at startup. /api/health still works; fix the error and restart.")
    yield


app = FastAPI(
    title="Solar Market Reality API",
    version="0.1.0",
    description="Off-grid solar penetration estimates and potential market-gap indicators. "
                "Independent service designed to be embedded in Energy Access Explorer later.",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(DataNotReadyError)
async def not_ready_handler(_: Request, exc: DataNotReadyError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": f"Data is not ready: {exc}"})


for module in (layers, cells, models, statistics):
    app.include_router(module.router, prefix="/api")

app.mount("/", nasa_nightlights_app)
