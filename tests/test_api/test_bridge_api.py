"""Tests for bridge API endpoints — status, settings, restart."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

from scue.api.bridge import router, init_bridge_api, BRIDGE_CONFIG_PATH, BridgeSettingsUpdate


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
