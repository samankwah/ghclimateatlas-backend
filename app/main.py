"""
Ghana Climate Atlas - FastAPI Backend
Serves climate projection data for Ghana districts
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import climate, districts

app = FastAPI(
    title="Ghana Climate Atlas API",
    description="API for Ghana climate projections based on KAPy/CORDEX-Africa data",
    version="1.0.0",
)

# CORS middleware for frontend
# In production, CORS_ORIGINS can override this allowlist with explicit
# frontend URL(s), comma-separated. If the env var is blank or only contains
# invalid values, fall back to the defaults rather than disabling CORS.
default_cors_origins = [
    "https://ghclimateatlas.netlify.app",
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

    parsed_origins = [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip().startswith(("http://", "https://"))
    ]
    return parsed_origins or default_cors_origins


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
