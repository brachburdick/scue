"""Bridge status API — GET /api/bridge/status."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bridge", tags=["bridge"])

# Set by main.py at startup
_bridge_manager = None


def init_bridge_api(bridge_manager) -> None:
    """Store reference to the bridge manager for the status endpoint."""
    global _bridge_manager
    _bridge_manager = bridge_manager


@router.get("/status")
async def bridge_status() -> dict:
    """Return current bridge status, devices, and player info."""
    if _bridge_manager is None:
        return {
            "status": "not_initialized",
            "port": 0,
            "jar_path": "",
            "jar_exists": False,
            "jre_available": False,
            "restart_count": 0,
            "devices": {},
            "players": {},
        }
    return _bridge_manager.to_status_dict()
