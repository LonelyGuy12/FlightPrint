"""FlightPrint Backend — FastAPI Main Application."""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import upload, pipeline, viewer

# Ensure pipeline package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

app = FastAPI(
    title="FlightPrint API",
    description="AI-powered 3D reconstruction from drone video",
    version="0.1.0",
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(upload.router)
app.include_router(pipeline.router)
app.include_router(viewer.router)

# Ensure directories exist
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    return {
        "name": "FlightPrint API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
