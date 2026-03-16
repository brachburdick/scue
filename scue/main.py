"""SCUE FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.bridge import init_bridge_api, router as bridge_router
from .api.filesystem import router as filesystem_router
from .api.tracks import init_tracks_api, router as tracks_router
from .bridge import BridgeAdapter, BridgeManager
from .layer1 import PlaybackTracker, TrackCache, TrackStore

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
app.include_router(filesystem_router)
app.include_router(bridge_router)

# Default project paths (can be overridden via env or config)
DEFAULT_TRACKS_DIR = Path("tracks")
DEFAULT_CACHE_PATH = Path("cache/scue.db")


_bridge_manager: BridgeManager | None = None
_tracker: PlaybackTracker | None = None


@app.on_event("startup")
async def startup() -> None:
    """Initialize storage, bridge, and playback tracker on app startup."""
    global _bridge_manager, _tracker
    init_tracks_api(DEFAULT_TRACKS_DIR, DEFAULT_CACHE_PATH)

    # Initialize Layer 1B: playback tracker
    store = TrackStore(DEFAULT_TRACKS_DIR)
    cache = TrackCache(DEFAULT_CACHE_PATH)
    _tracker = PlaybackTracker(store, cache)

    # Initialize bridge manager (graceful — won't crash if JAR/JRE missing)
    _bridge_manager = BridgeManager()
    init_bridge_api(_bridge_manager)

    # Wire bridge adapter → playback tracker
    adapter = _bridge_manager.adapter
    adapter.on_player_update = _tracker.on_player_update
    adapter.on_track_loaded = _tracker.on_track_loaded

    await _bridge_manager.start()
    logger.info("Bridge status: %s", _bridge_manager.status)

    logger.info("SCUE started")


@app.on_event("shutdown")
async def shutdown() -> None:
    """Clean up bridge on app shutdown."""
    if _bridge_manager is not None:
        await _bridge_manager.stop()
    logger.info("SCUE stopped")


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
