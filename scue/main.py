"""SCUE FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api.bridge import init_bridge_api, router as bridge_router
from .api.filesystem import init_filesystem_api, router as filesystem_router
from .api.network import init_network_api, router as network_router
from .api.tracks import init_tracks_api, router as tracks_router
from .api.usb import init_usb_api, router as usb_router
from .api.ws import init_ws, router as ws_router
from .api.ws_manager import WSManager
from .bridge import BridgeAdapter, BridgeManager
from .config import load_config
from .layer1 import PlaybackTracker, TrackCache, TrackStore

logger = logging.getLogger(__name__)

config = load_config()

app = FastAPI(title="SCUE", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
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


_bridge_manager: BridgeManager | None = None
_tracker: PlaybackTracker | None = None
_ws_manager: WSManager | None = None


@app.on_event("startup")
async def startup() -> None:
    """Initialize storage, bridge, and playback tracker on app startup."""
    global _bridge_manager, _tracker, _ws_manager

    tracks_dir = Path(config.server.tracks_dir)
    cache_path = Path(config.server.cache_path)

    init_tracks_api(
        tracks_dir, cache_path,
        audio_extensions=set(config.server.audio_extensions),
    )
    init_filesystem_api(audio_extensions=set(config.server.audio_extensions))

    # Initialize Layer 1B: playback tracker
    store = TrackStore(tracks_dir)
    cache = TrackCache(cache_path)
    _tracker = PlaybackTracker(store, cache)

    # Initialize bridge manager (graceful — won't crash if JAR/JRE missing)
    _bridge_manager = BridgeManager(
        port=config.bridge.port,
        network_interface=config.bridge.network_interface,
        auto_fix_route=config.bridge.route.auto_fix,
        health_check_interval=config.bridge.health.check_interval_s,
        restart_base_delay=config.bridge.restart.base_delay_s,
        restart_max_delay=config.bridge.restart.max_delay_s,
        max_crash_before_fallback=config.bridge.restart.max_crash_before_fallback,
    )
    init_bridge_api(_bridge_manager)
    init_network_api(_bridge_manager)
    init_usb_api(store, cache, usb_config=config.usb)

    # Initialize WebSocket manager and wire to bridge state changes
    _ws_manager = WSManager()
    init_ws(_ws_manager, _bridge_manager, watchdog_config=config.bridge.watchdog)

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


@app.get("/tools/recorder")
async def serve_recorder() -> FileResponse:
    """Serve the bridge recorder dev tool."""
    recorder_path = Path(__file__).parent.parent / "tools" / "recorder.html"
    return FileResponse(recorder_path, media_type="text/html")
