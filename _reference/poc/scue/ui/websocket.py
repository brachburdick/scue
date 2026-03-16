"""WebSocket handlers and broadcast helpers for the SCUE browser UI.

Manages connected browser clients and pushes Pioneer status updates in real time.
"""

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

# Shared set of connected WebSocket clients (managed by scue/main.py)
ws_clients: set[WebSocket] = set()


async def broadcast(msg: str) -> None:
    """Send a JSON string to all connected browser clients."""
    dead: set[WebSocket] = set()
    for ws in ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    ws_clients -= dead


async def broadcast_json(data: dict) -> None:
    """Serialize and broadcast a dict to all connected browser clients."""
    await broadcast(json.dumps(data))
