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
# In production, set CORS_ORIGINS env var to your frontend URL(s), comma-separated
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins.split(",")],
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
