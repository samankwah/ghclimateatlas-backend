"""
Ghana Climate Atlas - FastAPI Backend
Serves climate projection data for Ghana districts
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.caching import DataETagMiddleware
from app.routers import climate, districts, news, requests
from app.services.gmet_news import start_refresh_loop, stop_refresh_loop
from app.services.real_climate import (
    load_districts_geojson,
    load_period_values,
    _period_values_index,
)


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload data at startup so first requests are fast
    load_period_values()
    _period_values_index()  # pre-build the lookup index
    load_districts_geojson()
    # Keep the GMet update feed warm in the background. Deliberately not awaited:
    # boot must never block on an external host.
    start_refresh_loop()
    try:
        yield
    finally:
        await stop_refresh_loop()


app = FastAPI(
    title="Ghana Climate Atlas API",
    description="API for Ghana climate projections based on GhKAPy data",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
# CORS_ORIGINS adds extra frontend URL(s) in production, comma-separated.
# The first-party deployments below are always allowed on top of whatever it
# lists: a server whose CORS_ORIGINS predates a frontend host would otherwise
# drop Access-Control-Allow-Origin and silently break that site.
first_party_origins = [
    "https://atlas.meteo.gov.gh",
    "https://ghclimateatlas.netlify.app",
]

default_cors_origins = first_party_origins + [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]


def _parse_cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS")
    if configured_origins is None:
        return default_cors_origins

    # Browsers send Origin with no trailing slash, so normalise before matching.
    parsed_origins = [
        origin.strip().rstrip("/")
        for origin in configured_origins.split(",")
        if origin.strip().startswith(("http://", "https://"))
    ]
    if not parsed_origins:
        return default_cors_origins

    merged = list(first_party_origins)
    for origin in parsed_origins:
        if origin not in merged:
            merged.append(origin)
    return merged


# Added before GZip so it sits inside it and hashes the uncompressed body.
app.add_middleware(DataETagMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)

cors_origins = _parse_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(districts.router, prefix="/api/districts", tags=["districts"])
app.include_router(climate.router, prefix="/api/climate", tags=["climate"])
app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(news.router, prefix="/api/news", tags=["news"])


@app.get("/")
async def root():
    return {
        "name": "Ghana Climate Atlas API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
