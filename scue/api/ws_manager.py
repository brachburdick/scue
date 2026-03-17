"""WebSocket broadcast manager for real-time bridge state updates."""

import json
import logging
from collections.abc import Callable

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    """Manages WebSocket connections and broadcasts typed JSON messages.

    Components never touch WebSocket directly. The manager dispatches
    bridge state changes to all connected frontend clients.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await ws.accept()
        self._clients.add(ws)
        logger.info("WebSocket client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        self._clients.discard(ws)
        logger.info("WebSocket client disconnected (%d total)", len(self._clients))

    async def broadcast(self, message: dict) -> None:
        """Send a typed JSON message to all connected clients."""
        if not self._clients:
            return

        data = json.dumps(message)
        dead: list[WebSocket] = []

        for client in self._clients:
            try:
                await client.send_text(data)
            except Exception:
                dead.append(client)

        for client in dead:
            self._clients.discard(client)

    @property
    def client_count(self) -> int:
        return len(self._clients)
