"""SCUE FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.tracks import init_tracks_api, router as tracks_router

logger = logging.getLogger(__name__)

app = FastAPI(title="SCUE", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(tracks_router)

# Default project paths (can be overridden via env or config)
DEFAULT_TRACKS_DIR = Path("tracks")
DEFAULT_CACHE_PATH = Path("cache/scue.db")


@app.on_event("startup")
async def startup() -> None:
    """Initialize storage on app startup."""
    init_tracks_api(DEFAULT_TRACKS_DIR, DEFAULT_CACHE_PATH)
    logger.info("SCUE started")


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
