"""Tests for bridge manager — state machine, graceful degradation."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from scue.bridge.manager import BridgeManager


class TestManagerStateTransitions:
    """Test manager state machine without real subprocess/WebSocket."""

    @pytest.mark.asyncio
    async def test_initial_state_is_stopped(self):
        mgr = BridgeManager()
        assert mgr.status == "stopped"

    @pytest.mark.asyncio
    async def test_no_jre_state(self):
        mgr = BridgeManager()
        with patch.object(mgr, "_check_jre", return_value=False):
            await mgr.start()
        assert mgr.status == "no_jre"

    @pytest.mark.asyncio
    async def test_no_jar_state(self):
        mgr = BridgeManager(jar_path=Path("/nonexistent/bridge.jar"))
        # JRE exists but JAR doesn't
        with patch.object(mgr, "_check_jre", return_value=True):
            await mgr.start()
        assert mgr.status == "no_jar"

    @pytest.mark.asyncio
    async def test_stop_from_no_jre(self):
        mgr = BridgeManager()
        with patch.object(mgr, "_check_jre", return_value=False):
            await mgr.start()
        assert mgr.status == "no_jre"
        await mgr.stop()
        assert mgr.status == "stopped"

    @pytest.mark.asyncio
    async def test_stop_from_no_jar(self):
        mgr = BridgeManager(jar_path=Path("/nonexistent/bridge.jar"))
        with patch.object(mgr, "_check_jre", return_value=True):
            await mgr.start()
        assert mgr.status == "no_jar"
        await mgr.stop()
        assert mgr.status == "stopped"

    @pytest.mark.asyncio
    async def test_double_start_is_noop_when_running(self):
        """Starting when already running should be a no-op."""
        mgr = BridgeManager()
        # Force running state
        mgr._status = "running"
        await mgr.start()  # should return immediately
        assert mgr.status == "running"


class TestManagerStatusDict:
    def test_status_dict_structure(self):
        mgr = BridgeManager(jar_path=Path("lib/bridge.jar"), port=17400)
        status = mgr.to_status_dict()

        assert "status" in status
        assert "port" in status
        assert "jar_path" in status
        assert "jar_exists" in status
        assert "jre_available" in status
        assert "devices" in status
        assert "players" in status
        assert status["port"] == 17400

    def test_status_dict_with_adapter_data(self):
        mgr = BridgeManager()
        # Simulate adapter having data
        from scue.bridge.adapter import DeviceInfo, PlayerState
        mgr.adapter._devices["169.254.20.101"] = DeviceInfo(
            device_name="XDJ-AZ",
            device_number=1,
            device_type="cdj",
            ip_address="169.254.20.101",
        )
        mgr.adapter._players[1] = PlayerState(
            player_number=1,
            title="Strobe",
            artist="deadmau5",
            bpm=128.0,
            playback_state="playing",
            is_on_air=True,
        )

        status = mgr.to_status_dict()
        assert "169.254.20.101" in status["devices"]
        assert status["devices"]["169.254.20.101"]["device_name"] == "XDJ-AZ"
        assert "1" in status["players"]
        assert status["players"]["1"]["title"] == "Strobe"


class TestManagerPort:
    def test_default_port(self):
        mgr = BridgeManager()
        assert mgr.port == 17400

    def test_custom_port(self):
        mgr = BridgeManager(port=18000)
        assert mgr.port == 18000
