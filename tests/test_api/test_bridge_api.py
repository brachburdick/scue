"""Tests for bridge API endpoints — status, settings, restart, and WebSocket broadcasting."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

from scue.api.bridge import router, init_bridge_api, BRIDGE_CONFIG_PATH, BridgeSettingsUpdate
from scue.api.ws import router as ws_router, init_ws
from scue.api.ws_manager import WSManager


@pytest.fixture
def mock_manager():
    """Create a mock BridgeManager."""
    mgr = MagicMock()
    mgr.status = "running"
    mgr.port = 17400
    mgr.network_interface = None
    mgr.to_status_dict.return_value = {
        "status": "running",
        "port": 17400,
        "network_interface": None,
        "jar_path": "lib/beat-link-bridge.jar",
        "jar_exists": True,
        "jre_available": True,
        "restart_count": 0,
        "devices": {},
        "players": {},
    }
    mgr.restart = AsyncMock()
    return mgr


@pytest.fixture
def client(mock_manager):
    """Create a test client with the bridge router."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    init_bridge_api(mock_manager)
    return TestClient(app)


class TestBridgeStatusEndpoint:
    def test_status_returns_dict(self, client, mock_manager):
        resp = client.get("/api/bridge/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["network_interface"] is None

    def test_status_not_initialized(self, client):
        init_bridge_api(None)
        resp = client.get("/api/bridge/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_initialized"
        assert data["network_interface"] is None


class TestBridgeSettingsEndpoint:
    def test_update_network_interface(self, client, mock_manager, tmp_path):
        config_file = tmp_path / "bridge.yaml"
        config_file.write_text(yaml.dump({"bridge": {"port": 17400, "network_interface": None}}))

        with patch("scue.api.bridge.BRIDGE_CONFIG_PATH", config_file):
            resp = client.put("/api/bridge/settings", json={"network_interface": "en16"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["bridge"]["network_interface"] == "en16"

        # Verify config was persisted
        with open(config_file) as f:
            saved = yaml.safe_load(f)
        assert saved["bridge"]["network_interface"] == "en16"

        # Verify manager was updated
        assert mock_manager.network_interface == "en16"

    def test_update_empty_string_resets_to_none(self, client, mock_manager, tmp_path):
        config_file = tmp_path / "bridge.yaml"
        config_file.write_text(yaml.dump({"bridge": {"network_interface": "en5"}}))

        with patch("scue.api.bridge.BRIDGE_CONFIG_PATH", config_file):
            resp = client.put("/api/bridge/settings", json={"network_interface": ""})

        assert resp.status_code == 200
        assert mock_manager.network_interface is None

    def test_update_port(self, client, mock_manager, tmp_path):
        config_file = tmp_path / "bridge.yaml"
        config_file.write_text(yaml.dump({"bridge": {"port": 17400}}))

        with patch("scue.api.bridge.BRIDGE_CONFIG_PATH", config_file):
            resp = client.put("/api/bridge/settings", json={"port": 18000})

        assert resp.status_code == 200
        data = resp.json()
        assert data["bridge"]["port"] == 18000

    def test_invalid_port_rejected(self, client, tmp_path):
        config_file = tmp_path / "bridge.yaml"
        config_file.write_text(yaml.dump({"bridge": {}}))

        with patch("scue.api.bridge.BRIDGE_CONFIG_PATH", config_file):
            resp = client.put("/api/bridge/settings", json={"port": 80})

        assert resp.status_code == 400

    def test_update_creates_config_if_missing(self, client, mock_manager, tmp_path):
        config_file = tmp_path / "config" / "bridge.yaml"
        # Parent dir doesn't exist yet

        with patch("scue.api.bridge.BRIDGE_CONFIG_PATH", config_file):
            resp = client.put("/api/bridge/settings", json={"network_interface": "en5"})

        assert resp.status_code == 200
        assert config_file.exists()


class TestBridgeRestartEndpoint:
    def test_restart(self, client, mock_manager):
        mock_manager.to_status_dict.return_value["status"] = "running"
        resp = client.post("/api/bridge/restart")
        assert resp.status_code == 200
        mock_manager.restart.assert_called_once()

    def test_restart_not_initialized(self, client):
        init_bridge_api(None)
        resp = client.post("/api/bridge/restart")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# WebSocket Broadcasting Pipeline
# ---------------------------------------------------------------------------


def _make_ws_app(mock_manager: MagicMock) -> tuple:
    """Create a FastAPI app with bridge + WebSocket routers, returning (app, ws_manager)."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    app.include_router(ws_router)
    ws_manager = WSManager()
    init_bridge_api(mock_manager)
    init_ws(ws_manager, mock_manager)
    return app, ws_manager


class TestWebSocketBroadcasting:
    """Tests for the WebSocket broadcasting pipeline.

    Uses TestClient (synchronous) for connect/initial-message tests,
    and a dedicated WSManager unit test for the broadcast path.

    Covers:
    - Connect → receive initial bridge_status message
    - Broadcast → all connected clients receive the message (WSManager unit test)
    - Disconnect → client removed from broadcast set, next broadcast is safe
    """

    def test_connect_receives_initial_bridge_status(self, mock_manager: MagicMock) -> None:
        """On connect, client receives an immediate bridge_status message."""
        app, _ws_manager = _make_ws_app(mock_manager)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            msg_text = ws.receive_text()
            msg = json.loads(msg_text)

        assert msg["type"] == "bridge_status"
        assert "payload" in msg
        assert msg["payload"]["status"] == "running"

    async def test_broadcast_delivers_to_connected_clients(self) -> None:
        """WSManager.broadcast() sends a message to all connected clients.

        Uses async WSManager directly — tests the broadcast primitive itself,
        which is the core of the bridge-state-change → client pipeline.
        """
        # Simulate a connected WebSocket client
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()

        ws_manager = WSManager()
        # Bypass accept() by injecting directly
        ws_manager._clients.add(mock_ws)

        payload = {"type": "bridge_status", "payload": {"status": "restarting"}}
        await ws_manager.broadcast(payload)

        mock_ws.send_text.assert_called_once()
        sent_data = mock_ws.send_text.call_args[0][0]
        assert json.loads(sent_data) == payload

    async def test_disconnect_removes_client_no_error_on_broadcast(self) -> None:
        """After disconnect, broadcast completes without errors and set is empty."""
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock(side_effect=Exception("connection closed"))

        ws_manager = WSManager()
        ws_manager._clients.add(mock_ws)
        assert ws_manager.client_count == 1

        # Broadcast to a client that raises on send — it should be removed silently
        await ws_manager.broadcast({"type": "bridge_status", "payload": {}})

        # Dead client pruned
        assert ws_manager.client_count == 0

        # Second broadcast to empty set is safe
        await ws_manager.broadcast({"type": "bridge_status", "payload": {}})


# ---------------------------------------------------------------------------
# Route Fix — Friendly Error Wrapping (SC-007)
# ---------------------------------------------------------------------------


class TestRouteFixFriendlyError:
    """Regression: POST /api/network/route/fix must return user-friendly errors
    when the interface doesn't exist, not raw kernel output like
    'route: bad address: en16'.
    """

    @pytest.fixture
    def network_client(self):
        from fastapi import FastAPI
        from scue.api.network import router as network_router
        app = FastAPI()
        app.include_router(network_router)
        return TestClient(app)

    @patch("scue.api.network.fix_route")
    def test_bad_address_returns_friendly_message(self, mock_fix, network_client):
        """A 'bad address' kernel error is wrapped with a user-readable message."""
        from scue.network.models import RouteFixResult
        mock_fix.return_value = RouteFixResult(
            success=False,
            error="route: bad address: en16",
            previous_interface="en0",
            new_interface="en16",
        )

        resp = network_client.post("/api/network/route/fix", json={"interface": "en16"})

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert detail["success"] is False
        assert "not available" in detail["error"]
        assert "USB-Ethernet" in detail["error"]
        # Raw kernel output preserved in parenthetical
        assert "route: bad address: en16" in detail["error"]

    @patch("scue.api.network.fix_route")
    def test_no_such_interface_returns_friendly_message(self, mock_fix, network_client):
        """A 'no such interface' kernel error is also wrapped."""
        from scue.network.models import RouteFixResult
        mock_fix.return_value = RouteFixResult(
            success=False,
            error="No such interface: en99",
            previous_interface=None,
            new_interface="en99",
        )

        resp = network_client.post("/api/network/route/fix", json={"interface": "en99"})

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "not available" in detail["error"]

    @patch("scue.api.network.fix_route")
    def test_successful_fix_unchanged(self, mock_fix, network_client):
        """A successful route fix still returns normally (no regression)."""
        from scue.network.models import RouteFixResult
        mock_fix.return_value = RouteFixResult(
            success=True,
            error=None,
            previous_interface="en0",
            new_interface="en5",
        )

        resp = network_client.post("/api/network/route/fix", json={"interface": "en5"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["new_interface"] == "en5"
