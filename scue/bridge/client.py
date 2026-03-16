"""WebSocket client for connecting to the beat-link bridge subprocess.

Handles connection, reconnection, and message deserialization.
Separate from the manager so it can be tested independently
and used with mock bridge servers.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from .messages import BridgeMessage, parse_message

logger = logging.getLogger(__name__)

DEFAULT_BRIDGE_URL = "ws://localhost:17400"


class BridgeWebSocket:
    """WebSocket client that connects to the bridge and yields BridgeMessages."""

    def __init__(self, url: str = DEFAULT_BRIDGE_URL):
        self._url = url
        self._ws: ClientConnection | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def url(self) -> str:
        return self._url

    async def connect(self) -> None:
        """Connect to the bridge WebSocket server.

        Raises ConnectionError if the connection fails.
        """
        try:
            self._ws = await websockets.connect(self._url)
            self._connected = True
            logger.info("Connected to bridge at %s", self._url)
        except (OSError, websockets.exceptions.WebSocketException) as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to bridge at {self._url}: {e}") from e

    async def disconnect(self) -> None:
        """Cleanly close the WebSocket connection."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            finally:
                self._ws = None
                self._connected = False
                logger.info("Disconnected from bridge")

    async def listen(self) -> AsyncIterator[BridgeMessage]:
        """Async generator yielding BridgeMessage objects from the bridge.

        Yields messages until the connection is closed or an error occurs.
        Raises ConnectionError if not connected.
        """
        if self._ws is None:
            raise ConnectionError("Not connected to bridge")

        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    yield parse_message(raw)
                except ValueError as e:
                    logger.warning("Skipping malformed bridge message: %s", e)
        except websockets.exceptions.ConnectionClosed as e:
            logger.info("Bridge WebSocket closed: %s", e)
            self._connected = False
        except Exception as e:
            logger.error("Bridge WebSocket error: %s", e)
            self._connected = False
            raise

    async def recv_one(self) -> BridgeMessage | None:
        """Receive a single message. Returns None on error or disconnect."""
        if self._ws is None:
            return None
        try:
            raw = await self._ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return parse_message(raw)
        except (websockets.exceptions.ConnectionClosed, ValueError) as e:
            logger.warning("recv_one failed: %s", e)
            self._connected = False
            return None
