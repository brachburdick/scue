"""Bridge API — status, settings, and restart endpoints."""

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bridge", tags=["bridge"])

BRIDGE_CONFIG_PATH = Path("config/bridge.yaml")

# Set by main.py at startup
_bridge_manager = None


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
