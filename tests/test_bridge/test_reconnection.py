"""WebSocket client reconnection and connection lifecycle tests.

Tests the BridgeWebSocket client's behavior when the server connects,
disconnects, and reconnects. Uses a real WebSocket server on localhost
to validate the full network path.
"""

import asyncio
import json

import pytest
import websockets
from websockets.asyncio.server import ServerConnection

from scue.bridge.client import BridgeWebSocket


# --- Helpers ---

async def _start_server(port: int, handler=None):
    """Start a minimal WebSocket server that optionally sends messages."""
    async def default_handler(ws: ServerConnection) -> None:
        try:
            async for msg in ws:
                pass  # echo nothing, just keep connection alive
        except websockets.exceptions.ConnectionClosed:
            pass

    server = await websockets.serve(
        handler or default_handler,
        "localhost",
        port,
    )
    return server


def _make_bridge_status_json(connected: bool = True) -> str:
    return json.dumps({
        "type": "bridge_status",
        "timestamp": 1710600000.0,
        "player_number": None,
        "payload": {
            "connected": connected,
            "devices_online": 0,
            "version": "1.0.0",
        },
    })


def _make_player_status_json(bpm: float = 128.0) -> str:
    return json.dumps({
        "type": "player_status",
        "timestamp": 1710600020.0,
        "player_number": 1,
        "payload": {
            "bpm": bpm,
            "pitch": 0.0,
            "beat_within_bar": 1,
            "beat_number": 0,
            "playback_state": "playing",
            "is_on_air": True,
            "track_source_player": 1,
            "track_source_slot": "usb",
            "track_type": "rekordbox",
        },
    })


# --- Tests ---

@pytest.mark.asyncio
class TestConnection:
    async def test_connect_and_disconnect(self):
        """Client connects, reports connected, disconnects cleanly."""
        server = await _start_server(17450)
        try:
            client = BridgeWebSocket("ws://localhost:17450")
            assert client.connected is False

            await client.connect()
            assert client.connected is True

            await client.disconnect()
            assert client.connected is False
        finally:
            server.close()
            await server.wait_closed()

    async def test_connect_to_dead_server_raises(self):
        """Connecting to a port with no server raises ConnectionError."""
        client = BridgeWebSocket("ws://localhost:17451")
        with pytest.raises(ConnectionError):
            await client.connect()
        assert client.connected is False

    async def test_connect_timeout(self):
        """Connection to a non-routable address should timeout."""
        # Use a port that's not listening — ConnectionError wraps the timeout/refusal
        client = BridgeWebSocket("ws://localhost:17452")
        with pytest.raises(ConnectionError):
            await client.connect()


@pytest.mark.asyncio
class TestServerDisconnect:
    async def test_listen_exits_on_server_shutdown(self):
        """When the server closes cleanly, listen() should exit its loop."""
        server = await _start_server(17453)
        client = BridgeWebSocket("ws://localhost:17453")

        await client.connect()
        assert client.connected is True

        # Close the server — client should detect disconnect
        server.close()
        await server.wait_closed()

        # listen() should exit (not hang forever)
        messages = []
        async for msg in client.listen():
            messages.append(msg)

        # Clean close exits the iterator without error; no messages received
        assert len(messages) == 0

    async def test_recv_one_after_server_close_returns_none(self):
        """recv_one() returns None when the server has closed."""
        server = await _start_server(17454)
        client = BridgeWebSocket("ws://localhost:17454")

        await client.connect()

        server.close()
        await server.wait_closed()
        # Give the close frame time to propagate
        await asyncio.sleep(0.1)

        result = await client.recv_one()
        assert result is None
        assert client.connected is False


@pytest.mark.asyncio
class TestReconnection:
    async def test_reconnect_after_server_restart(self):
        """Client can reconnect after the server goes down and comes back up."""
        port = 17455

        # Phase 1: connect
        server = await _start_server(port)
        client = BridgeWebSocket(f"ws://localhost:{port}")
        await client.connect()
        assert client.connected is True

        # Phase 2: server dies
        server.close()
        await server.wait_closed()

        await client.disconnect()
        assert client.connected is False

        # Phase 3: server comes back
        server2 = await _start_server(port)
        try:
            await client.connect()
            assert client.connected is True
        finally:
            await client.disconnect()
            server2.close()
            await server2.wait_closed()

    async def test_messages_work_after_reconnect(self):
        """After reconnecting, messages from the new server are parsed correctly."""
        port = 17456

        async def send_status(ws: ServerConnection) -> None:
            try:
                await ws.send(_make_player_status_json(bpm=140.0))
                async for _ in ws:
                    pass
            except websockets.exceptions.ConnectionClosed:
                pass

        # Phase 1: connect and disconnect
        server1 = await _start_server(port)
        client = BridgeWebSocket(f"ws://localhost:{port}")
        await client.connect()
        server1.close()
        await server1.wait_closed()
        await client.disconnect()

        # Phase 2: reconnect to new server that sends a message
        server2 = await _start_server(port, handler=send_status)
        try:
            await client.connect()
            assert client.connected is True

            msg = await client.recv_one()
            assert msg is not None
            assert msg.type == "player_status"
            assert msg.payload["bpm"] == 140.0
        finally:
            await client.disconnect()
            server2.close()
            await server2.wait_closed()


@pytest.mark.asyncio
class TestMessageReceiving:
    async def test_listen_yields_parsed_messages(self):
        """listen() yields properly parsed BridgeMessage objects."""
        port = 17457

        async def send_two(ws: ServerConnection) -> None:
            await ws.send(_make_bridge_status_json())
            await ws.send(_make_player_status_json(bpm=126.0))
            await ws.close()

        server = await _start_server(port, handler=send_two)
        client = BridgeWebSocket(f"ws://localhost:{port}")

        try:
            await client.connect()
            messages = []
            async for msg in client.listen():
                messages.append(msg)

            assert len(messages) == 2
            assert messages[0].type == "bridge_status"
            assert messages[1].type == "player_status"
            assert messages[1].payload["bpm"] == 126.0
        finally:
            server.close()
            await server.wait_closed()

    async def test_malformed_messages_skipped(self):
        """Malformed JSON messages are skipped, valid ones still yielded."""
        port = 17458

        async def send_mixed(ws: ServerConnection) -> None:
            await ws.send("not valid json {{{")
            await ws.send(_make_bridge_status_json())
            await ws.close()

        server = await _start_server(port, handler=send_mixed)
        client = BridgeWebSocket(f"ws://localhost:{port}")

        try:
            await client.connect()
            messages = []
            async for msg in client.listen():
                messages.append(msg)

            # Only the valid message should come through
            assert len(messages) == 1
            assert messages[0].type == "bridge_status"
        finally:
            server.close()
            await server.wait_closed()
