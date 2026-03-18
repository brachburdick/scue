"""WebSocket endpoint for real-time bridge state streaming to the frontend.

Message types pushed to frontend:
- bridge_status: full bridge state on every change
- pioneer_status: liveness watchdog (is_receiving, last_message_age_ms)
"""

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .ws_manager import WSManager

from ..config.loader import WatchdogConfig

logger = logging.getLogger(__name__)

router = APIRouter()

# Singleton — set up by main.py
_ws_manager: WSManager | None = None
_bridge_manager = None  # type: ignore  # Set by init_ws()
_watchdog_config = WatchdogConfig()  # defaults until init_ws() is called


def init_ws(
    ws_manager: WSManager,
    bridge_manager: object,
    watchdog_config: WatchdogConfig | None = None,
) -> None:
    """Store references for the WebSocket endpoint."""
    global _ws_manager, _bridge_manager, _watchdog_config
    _ws_manager = ws_manager
    _bridge_manager = bridge_manager
    if watchdog_config is not None:
        _watchdog_config = watchdog_config


def _build_bridge_status() -> dict:
    """Build a bridge_status message from the current bridge manager state."""
    if _bridge_manager is None:
        return {
            "type": "bridge_status",
            "payload": {"status": "not_initialized"},
        }
    return {
        "type": "bridge_status",
        "payload": _bridge_manager.to_status_dict(),
    }


def _build_pioneer_status() -> dict:
    """Build a pioneer_status liveness message.

    Uses two separate timestamps to distinguish bridge process liveness
    from actual Pioneer hardware traffic:
    - bridge_connected: bridge subprocess is alive and sending messages
    - is_receiving: Pioneer hardware (device/player/beat) data arriving
    """
    if _bridge_manager is None:
        return {
            "type": "pioneer_status",
            "payload": {
                "is_receiving": False,
                "bridge_connected": False,
                "last_message_age_ms": -1,
            },
        }

    now = time.time()

    # Bridge liveness: any message from the bridge WebSocket (including heartbeats)
    threshold_ms = _watchdog_config.is_receiving_threshold_ms
    bridge_time = getattr(_bridge_manager, "_last_message_time", 0.0)
    bridge_connected = bridge_time > 0 and (now - bridge_time) < threshold_ms / 1000

    # Pioneer traffic: only device_found, player_status, beat, etc.
    # (NOT bridge_status heartbeats)
    pioneer_time = getattr(_bridge_manager, "_last_pioneer_message_time", 0.0)
    if pioneer_time > 0:
        age_ms = int((now - pioneer_time) * 1000)
        is_receiving = age_ms < threshold_ms
    else:
        age_ms = -1
        is_receiving = False

    return {
        "type": "pioneer_status",
        "payload": {
            "is_receiving": is_receiving,
            "bridge_connected": bridge_connected,
            "last_message_age_ms": age_ms,
        },
    }


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time bridge state updates.

    On connect, immediately sends current bridge_status.
    Then streams updates whenever the bridge state changes.
    Also sends periodic pioneer_status every 2 seconds.
    """
    if _ws_manager is None:
        await ws.close(code=1011, reason="WebSocket manager not initialized")
        return

    await _ws_manager.connect(ws)

    try:
        # Send initial state
        await ws.send_json(_build_bridge_status())

        # Keep connection alive, handle client messages (ping/pong)
        while True:
            try:
                # Wait for client messages (ping/pong/close)
                # Timeout every poll_interval to send pioneer_status
                data = await asyncio.wait_for(
                    ws.receive_text(),
                    timeout=_watchdog_config.poll_interval_s,
                )
            except asyncio.TimeoutError:
                # Send periodic pioneer status
                try:
                    await ws.send_json(_build_pioneer_status())
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        _ws_manager.disconnect(ws)
