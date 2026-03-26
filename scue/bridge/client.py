"""WebSocket client for connecting to the beat-link bridge subprocess.

Handles connection, reconnection, message deserialization, and command sending.
Separate from the manager so it can be tested independently
and used with mock bridge servers.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from .commands import Command, CommandResponse, parse_command_response, serialize_command
from .messages import COMMAND_RESPONSE, BridgeMessage, parse_message

logger = logging.getLogger(__name__)

DEFAULT_BRIDGE_URL = "ws://localhost:17400"


class BridgeWebSocket:
    """WebSocket client that connects to the bridge and yields BridgeMessages.

    Also supports sending commands and waiting for correlated responses
    via send_command().
    """

    def __init__(self, url: str = DEFAULT_BRIDGE_URL):
        self._url = url
        self._ws: ClientConnection | None = None
        self._connected = False
        # Pending command responses: request_id → Future[CommandResponse]
        self._pending_commands: dict[str, asyncio.Future[CommandResponse]] = {}

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
            self._ws = await asyncio.wait_for(
                websockets.connect(self._url),
                timeout=10.0,
            )
            self._connected = True
            logger.info("Connected to bridge at %s", self._url)
        except asyncio.TimeoutError:
            self._connected = False
            raise ConnectionError(f"Bridge WebSocket connect to {self._url} timed out after 10s")
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

        Command responses (type=command_response) are intercepted and routed
        to pending send_command() callers — they are NOT yielded to the caller.
        """
        if self._ws is None:
            raise ConnectionError("Not connected to bridge")

        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    msg = parse_message(raw)
                except ValueError as e:
                    logger.warning("Skipping malformed bridge message: %s", e)
                    continue

                # Intercept command responses and resolve pending futures
                if msg.type == COMMAND_RESPONSE:
                    self._resolve_command_response(msg.payload)
                    continue

                yield msg
        except websockets.exceptions.ConnectionClosed as e:
            logger.info("Bridge WebSocket closed: %s", e)
            self._connected = False
            self._cancel_pending_commands("WebSocket closed")
        except Exception as e:
            logger.error("Bridge WebSocket error: %s", e)
            self._connected = False
            self._cancel_pending_commands(str(e))
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

    # ── Command channel ──────────────────────────────────────────────────

    async def send_command(self, cmd: Command, timeout: float = 10.0) -> CommandResponse:
        """Send a command to the bridge and wait for the correlated response.

        The listen() loop must be running concurrently for responses to be
        routed back. If listen() is not running, this will time out.

        Args:
            cmd: A typed command dataclass (LoadTrackCommand, BrowseAllTracksCommand, etc.)
            timeout: Max seconds to wait for the response.

        Returns:
            CommandResponse with status, data, and optional error_message.

        Raises:
            ConnectionError: If not connected.
            asyncio.TimeoutError: If no response within timeout.
        """
        if self._ws is None or not self._connected:
            raise ConnectionError("Not connected to bridge")

        request_id, json_str = serialize_command(cmd)

        # Create a future for this request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[CommandResponse] = loop.create_future()
        self._pending_commands[request_id] = future

        try:
            await self._ws.send(json_str)
            logger.debug("Sent command: %s (request_id=%s)", cmd.__class__.__name__, request_id)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_commands.pop(request_id, None)
            raise
        except Exception:
            self._pending_commands.pop(request_id, None)
            raise

    def _resolve_command_response(self, payload: dict) -> None:
        """Match a command_response payload to a pending future and resolve it."""
        response = parse_command_response(payload)
        future = self._pending_commands.pop(response.request_id, None)
        if future is not None and not future.done():
            future.set_result(response)
        else:
            logger.warning("Received command_response for unknown request_id: %s", response.request_id)

    def _cancel_pending_commands(self, reason: str) -> None:
        """Cancel all pending command futures (e.g. on disconnect)."""
        for request_id, future in self._pending_commands.items():
            if not future.done():
                future.set_exception(ConnectionError(f"Bridge disconnected: {reason}"))
        self._pending_commands.clear()
