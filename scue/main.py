"""SCUE FastAPI application entry point."""

import logging
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.bridge import init_bridge_api, router as bridge_router
from .api.filesystem import router as filesystem_router
from .api.network import router as network_router
from .api.tracks import init_tracks_api, router as tracks_router
from .api.usb import init_usb_api, router as usb_router
from .api.ws import init_ws, router as ws_router
from .api.ws_manager import WSManager
from .bridge import BridgeAdapter, BridgeManager
from .bridge.manager import DEFAULT_PORT
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
app.include_router(usb_router)
app.include_router(network_router)
app.include_router(ws_router)

# Default project paths (can be overridden via env or config)
DEFAULT_TRACKS_DIR = Path("tracks")
DEFAULT_CACHE_PATH = Path("cache/scue.db")
BRIDGE_CONFIG_PATH = Path("config/bridge.yaml")


def _load_bridge_config() -> dict:
    """Load bridge configuration from config/bridge.yaml."""
    if not BRIDGE_CONFIG_PATH.exists():
        return {}
    try:
        with open(BRIDGE_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        return data.get("bridge", {})
    except Exception as e:
        logger.warning("Failed to load bridge config: %s", e)
        return {}


_bridge_manager: BridgeManager | None = None
_tracker: PlaybackTracker | None = None
_ws_manager: WSManager | None = None


@app.on_event("startup")
async def startup() -> None:
    """Initialize storage, bridge, and playback tracker on app startup."""
    global _bridge_manager, _tracker, _ws_manager
    init_tracks_api(DEFAULT_TRACKS_DIR, DEFAULT_CACHE_PATH)

    # Initialize Layer 1B: playback tracker
    store = TrackStore(DEFAULT_TRACKS_DIR)
    cache = TrackCache(DEFAULT_CACHE_PATH)
    _tracker = PlaybackTracker(store, cache)

    # Initialize bridge manager (graceful — won't crash if JAR/JRE missing)
    bridge_cfg = _load_bridge_config()
    route_cfg = bridge_cfg.get("route", {}) if isinstance(bridge_cfg.get("route"), dict) else {}
    _bridge_manager = BridgeManager(
        port=bridge_cfg.get("port", DEFAULT_PORT) or DEFAULT_PORT,
        network_interface=bridge_cfg.get("network_interface"),
        auto_fix_route=route_cfg.get("auto_fix", True),
    )
    init_bridge_api(_bridge_manager)
    init_usb_api(store, cache)

    # Initialize WebSocket manager and wire to bridge state changes
    _ws_manager = WSManager()
    init_ws(_ws_manager, _bridge_manager)

    async def _on_bridge_state_change() -> None:
        """Broadcast bridge state to all WebSocket clients."""
        if _ws_manager and _bridge_manager:
            await _ws_manager.broadcast({
                "type": "bridge_status",
                "payload": _bridge_manager.to_status_dict(),
            })

    import asyncio

    def _sync_state_change() -> None:
        """Synchronous wrapper that schedules the async broadcast."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_on_bridge_state_change())
        except RuntimeError:
            pass

    _bridge_manager.on_state_change = _sync_state_change

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
