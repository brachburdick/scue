"""Network API — interface enumeration, route status, and route fix endpoints."""

import logging
import platform
from dataclasses import asdict
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..network.route import (
    check_launchd_installed,
    check_route,
    check_sudoers_installed,
    enumerate_interfaces,
    fix_route,
    get_current_route,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/network", tags=["network"])

BRIDGE_CONFIG_PATH = Path("config/bridge.yaml")


def _get_configured_interface() -> str | None:
    """Read the configured network_interface from bridge.yaml."""
    if not BRIDGE_CONFIG_PATH.exists():
        return None
    try:
        with open(BRIDGE_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        return data.get("bridge", {}).get("network_interface")
    except Exception:
        return None


@router.get("/interfaces")
async def list_interfaces() -> dict:
    """List available network interfaces with Pro DJ Link suitability scoring.

    Works even when the bridge is not running. Uses Python-side enumeration
    with the same scoring algorithm as the Java bridge.
    """
    interfaces = enumerate_interfaces()
    configured = _get_configured_interface()

    # Recommended = highest-scoring interface
    recommended = interfaces[0].name if interfaces else None

    return {
        "interfaces": [asdict(iface) for iface in interfaces],
        "configured_interface": configured,
        "recommended_interface": recommended,
    }


@router.get("/route")
async def route_status() -> dict:
    """Return current macOS broadcast route state for 169.254.255.255.

    On Linux, route_applicable is False (link-local routing works automatically).
    """
    is_mac = platform.system() == "Darwin"
    configured = _get_configured_interface()

    if not is_mac:
        return {
            "platform": platform.system().lower(),
            "route_applicable": False,
            "current_interface": None,
            "expected_interface": configured,
            "correct": True,
            "fix_available": False,
            "sudoers_installed": False,
        }

    if not configured:
        return {
            "platform": "darwin",
            "route_applicable": True,
            "current_interface": get_current_route().interface,
            "expected_interface": None,
            "correct": False,
            "fix_available": False,
            "sudoers_installed": check_sudoers_installed(),
        }

    result = check_route(configured)
    return {
        "platform": "darwin",
        "route_applicable": True,
        "current_interface": result.current_interface,
        "expected_interface": result.expected_interface,
        "correct": result.correct,
        "fix_available": result.fix_available,
        "sudoers_installed": check_sudoers_installed(),
    }


class RouteFixRequest(BaseModel):
    """Request body for POST /api/network/route/fix."""
    interface: str


@router.post("/route/fix")
async def fix_route_endpoint(body: RouteFixRequest) -> dict:
    """Trigger a route fix for the given interface.

    Requires the sudoers entry to be installed via tools/install-route-fix.sh.
    """
    result = fix_route(body.interface)

    if not result.success:
        # Wrap raw kernel errors with a user-friendly message.
        # "route: bad address: <iface>" means the interface doesn't exist
        # (adapter unplugged / hardware off). Mirrors manager.py:296–308.
        if result.error and (
            "bad address" in result.error
            or "no such interface" in result.error.lower()
        ):
            friendly = (
                f"Network interface '{body.interface}' is not available. "
                f"Make sure your USB-Ethernet adapter is connected and the "
                f"interface is up before fixing the route. "
                f"(kernel error: {result.error})"
            )
            result = type(result)(
                success=False,
                error=friendly,
                previous_interface=result.previous_interface,
                new_interface=result.new_interface,
            )
        logger.warning("Route fix failed for %s: %s", body.interface, result.error)
        raise HTTPException(
            status_code=500,
            detail=asdict(result),
        )

    return asdict(result)


@router.get("/route/setup-status")
async def route_setup_status() -> dict:
    """Check whether the launchd agent and sudoers entry are installed."""
    return {
        "sudoers_installed": check_sudoers_installed(),
        "launchd_installed": check_launchd_installed(),
        "setup_command": "sudo ./tools/install-route-fix.sh",
    }
