"""Bridge API — status, settings, restart, and recording endpoints."""

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..bridge.recorder import MessageRecorder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bridge", tags=["bridge"])

BRIDGE_CONFIG_PATH = Path("config/bridge.yaml")

# Set by main.py at startup
_bridge_manager = None
_recorder = MessageRecorder()


def init_bridge_api(bridge_manager) -> None:
    """Store reference to the bridge manager for the status endpoint."""
    global _bridge_manager
    _bridge_manager = bridge_manager


class BridgeSettingsUpdate(BaseModel):
    """Request body for PUT /api/bridge/settings."""
    network_interface: str | None = None
    port: int | None = None


@router.get("/status")
async def bridge_status() -> dict:
    """Return current bridge status, devices, and player info."""
    if _bridge_manager is None:
        return {
            "status": "not_initialized",
            "port": 0,
            "network_interface": None,
            "jar_path": "",
            "jar_exists": False,
            "jre_available": False,
            "restart_count": 0,
            "devices": {},
            "players": {},
        }
    return _bridge_manager.to_status_dict()


@router.put("/settings")
async def update_bridge_settings(body: BridgeSettingsUpdate) -> dict:
    """Update bridge settings in config/bridge.yaml.

    Does NOT restart the bridge — call POST /api/bridge/restart after.
    """
    # Load current config
    config: dict = {}
    if BRIDGE_CONFIG_PATH.exists():
        try:
            with open(BRIDGE_CONFIG_PATH) as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Failed to read bridge config: %s", e)

    bridge_cfg = config.get("bridge", {})
    if not isinstance(bridge_cfg, dict):
        bridge_cfg = {}

    # Apply updates (only provided fields)
    if body.network_interface is not None:
        # Empty string means "reset to auto-detect"
        bridge_cfg["network_interface"] = body.network_interface or None
    if body.port is not None:
        if body.port < 1024 or body.port > 65535:
            raise HTTPException(status_code=400, detail="Port must be between 1024 and 65535")
        bridge_cfg["port"] = body.port

    config["bridge"] = bridge_cfg

    # Write back
    BRIDGE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BRIDGE_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    # Update the manager's in-memory state
    if _bridge_manager is not None:
        if body.network_interface is not None:
            _bridge_manager.network_interface = body.network_interface or None

    logger.info("Bridge settings updated: %s", bridge_cfg)
    return {"status": "saved", "bridge": bridge_cfg}


@router.post("/restart")
async def restart_bridge() -> dict:
    """Stop and restart the bridge subprocess.

    Picks up any config changes (e.g. network_interface) saved via PUT /settings.
    """
    if _bridge_manager is None:
        raise HTTPException(status_code=503, detail="Bridge manager not initialized")

    await _bridge_manager.restart()
    return _bridge_manager.to_status_dict()


# ---------------------------------------------------------------------------
# Bridge Message Recording
# ---------------------------------------------------------------------------


class RecordRequest(BaseModel):
    name: str | None = None


@router.post("/record/start")
async def start_recording(body: RecordRequest | None = None) -> dict:
    """Start recording bridge messages to a fixture file."""
    if _recorder.is_recording:
        raise HTTPException(400, "Already recording")
    if _bridge_manager is None:
        raise HTTPException(503, "Bridge manager not initialized")

    name = body.name if body else None
    path = _recorder.start(name)

    # Wire the recorder into the bridge manager's external callback
    _prev_callback = _bridge_manager._external_on_message

    def _recording_callback(msg):
        _recorder.record(msg)
        if _prev_callback is not None:
            _prev_callback(msg)

    _bridge_manager._external_on_message = _recording_callback

    return {"status": "recording", "path": path}


@router.post("/record/stop")
async def stop_recording() -> dict:
    """Stop recording and return summary."""
    if not _recorder.is_recording:
        raise HTTPException(400, "Not recording")

    summary = _recorder.stop()

    # Restore the original callback
    if _bridge_manager is not None:
        _bridge_manager._external_on_message = None

    return summary


@router.get("/record/status")
async def record_status() -> dict:
    """Check recording status."""
    return {
        "is_recording": _recorder.is_recording,
        "messages": _recorder.message_count,
        "elapsed_seconds": round(_recorder.elapsed_seconds, 1),
        "path": _recorder.recording_path,
    }
