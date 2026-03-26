"""SCUE FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api.audio import init_audio_api, router as audio_router
from .api.bridge import init_bridge_api, router as bridge_router
from .api.filesystem import init_filesystem_api, router as filesystem_router
from .api.ground_truth import init_ground_truth_api, router as ground_truth_router
from .api.network import init_network_api, router as network_router
from .api.scanner import init_scanner_api, router as scanner_router
from .api.strata import init_strata_api, router as strata_router
from .api.tracks import init_tracks_api, resume_incomplete_jobs, router as tracks_router
from .api.waveform_presets import init_waveform_presets_api, router as waveform_presets_router
from .api.usb import init_usb_api, router as usb_router
from .api.local_library import init_local_library_api, router as local_library_router
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
app.include_router(local_library_router)
app.include_router(network_router)
app.include_router(ws_router)
app.include_router(ground_truth_router)
app.include_router(audio_router)
app.include_router(scanner_router)
app.include_router(strata_router)
app.include_router(waveform_presets_router)


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
        strata_dir=Path("strata"),
    )
    init_filesystem_api(audio_extensions=set(config.server.audio_extensions))

    # Initialize waveform presets API
    init_waveform_presets_api(Path("config/waveform-presets.yaml"))

    # Initialize ground truth + audio APIs
    gt_dir = Path("ground_truth")
    init_ground_truth_api(gt_dir, tracks_dir)
    init_audio_api(tracks_dir)

    # Initialize Strata (arrangement analysis) API
    from .layer1.strata.storage import StrataStore
    strata_dir = Path("strata")
    strata_store = StrataStore(strata_dir)
    init_strata_api(strata_store, tracks_dir=tracks_dir, cache_path=cache_path)

    from .api.strata import set_strata_tracker

    # Initialize Layer 1B: playback tracker
    store = TrackStore(tracks_dir)
    cache = TrackCache(cache_path)
    _tracker = PlaybackTracker(store, cache)
    set_strata_tracker(_tracker)

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
    init_local_library_api(store, cache)

    # Initialize WebSocket manager and wire to bridge state changes
    _ws_manager = WSManager()
    init_ws(_ws_manager, _bridge_manager, watchdog_config=config.bridge.watchdog)

    # Initialize scanner API (bridge command channel for track scanning)
    init_scanner_api(_bridge_manager, cache, _ws_manager)

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

    # Wire beat events to update playback position.
    # on_beat signature: (player_number, beat_within_bar, bpm).
    # Derive position_ms from adapter's computed playback_position_ms.
    def _on_beat(player_number: int, beat_within_bar: int, bpm: float) -> None:
        player = adapter.get_player(player_number)
        if player is not None and player.playback_position_ms is not None:
            _tracker.update_position(player_number, player.playback_position_ms)
    adapter.on_beat = _on_beat

    # Wire live strata broadcast
    from .layer1.strata.models import ArrangementFormula, formula_to_dict

    def _on_live_strata(player_number: int, formula: ArrangementFormula) -> None:
        """Broadcast live strata formula to all WebSocket clients."""
        if not _ws_manager:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_ws_manager.broadcast({
                "type": "strata_live",
                "payload": {
                    "player_number": player_number,
                    "formula": formula_to_dict(formula),
                },
            }))
        except RuntimeError:
            pass

    _tracker.on_live_strata = _on_live_strata

    await _bridge_manager.start()
    logger.info("Bridge status: %s", _bridge_manager.status)

    # Resume any incomplete analysis jobs from a previous session
    await resume_incomplete_jobs()

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
