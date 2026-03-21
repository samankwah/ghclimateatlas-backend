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
# In production, set CORS_ORIGINS to explicit frontend URL(s), comma-separated.
# During local development, allow common localhost hosts and Vite ports.
default_cors_origins = ",".join(
    [
        "https://ghclimateatlas.netlify.app",
        "https://ghclimatealtas.netlify.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
)
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", default_cors_origins).split(",")
    if origin.strip()
]
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
