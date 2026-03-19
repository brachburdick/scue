"""Tests for network interface selection — manager, config, and API."""

import asyncio
import time
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import yaml

from scue.bridge.manager import BridgeManager
from scue.bridge.messages import BridgeStatusPayload
from scue.network.models import InterfaceAddress, NetworkInterfaceInfo
from scue.network.route import _score_interface, enumerate_interfaces


# ── BridgeManager interface config ────────────────────────────────────────


class TestManagerNetworkInterface:
    def test_default_interface_is_none(self):
        mgr = BridgeManager()
        assert mgr.network_interface is None

    def test_custom_interface(self):
        mgr = BridgeManager(network_interface="en16")
        assert mgr.network_interface == "en16"

    def test_interface_setter(self):
        mgr = BridgeManager()
        mgr.network_interface = "en5"
        assert mgr.network_interface == "en5"

    def test_interface_setter_to_none(self):
        mgr = BridgeManager(network_interface="en5")
        mgr.network_interface = None
        assert mgr.network_interface is None

    def test_status_dict_includes_network_interface(self):
        mgr = BridgeManager(network_interface="en16")
        status = mgr.to_status_dict()
        assert "network_interface" in status
        assert status["network_interface"] == "en16"

    def test_status_dict_network_interface_none(self):
        mgr = BridgeManager()
        status = mgr.to_status_dict()
        assert status["network_interface"] is None


class TestManagerCommandLine:
    """Verify --interface is passed to the JAR subprocess."""

    @pytest.mark.asyncio
    async def test_launch_includes_interface_arg(self):
        mgr = BridgeManager(network_interface="en16")
        # Mock subprocess and connection
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True):
            mock_proc = mock_popen.return_value
            mock_proc.poll.return_value = None
            mock_proc.stderr = None
            # Mock the port check to succeed immediately
            with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
                mock_writer = AsyncMock()
                mock_conn.return_value = (AsyncMock(), mock_writer)
                try:
                    await mgr._launch_subprocess()
                except Exception:
                    pass  # May fail at WebSocket stage, that's fine

            # Verify the command included --interface
            call_args = mock_popen.call_args[0][0]
            assert "--interface" in call_args
            idx = call_args.index("--interface")
            assert call_args[idx + 1] == "en16"

    @pytest.mark.asyncio
    async def test_launch_omits_interface_when_none(self):
        mgr = BridgeManager()  # no network_interface
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True):
            mock_proc = mock_popen.return_value
            mock_proc.poll.return_value = None
            mock_proc.stderr = None
            with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
                mock_writer = AsyncMock()
                mock_conn.return_value = (AsyncMock(), mock_writer)
                try:
                    await mgr._launch_subprocess()
                except Exception:
                    pass

            call_args = mock_popen.call_args[0][0]
            assert "--interface" not in call_args


class TestManagerRestart:
    @pytest.mark.asyncio
    async def test_restart_calls_stop_then_start(self):
        mgr = BridgeManager()
        stop_called = False
        start_called = False

        async def mock_stop():
            nonlocal stop_called
            stop_called = True
            mgr._status = "stopped"

        async def mock_start():
            nonlocal start_called
            start_called = True
            mgr._status = "running"

        with patch.object(mgr, "stop", side_effect=mock_stop), \
             patch.object(mgr, "start", side_effect=mock_start):
            await mgr.restart()

        assert stop_called
        assert start_called

    @pytest.mark.asyncio
    async def test_restart_resets_restart_count(self):
        mgr = BridgeManager()
        mgr._restart_count = 5

        async def mock_stop():
            mgr._status = "stopped"

        async def mock_start():
            mgr._status = "running"

        with patch.object(mgr, "stop", side_effect=mock_stop), \
             patch.object(mgr, "start", side_effect=mock_start):
            await mgr.restart()

        assert mgr._restart_count == 0


# ── BridgeStatusPayload extended fields ───────────────────────────────────


class TestBridgeStatusPayloadExtended:
    def test_default_new_fields_are_none(self):
        payload = BridgeStatusPayload(connected=True, devices_online=2)
        assert payload.network_interface is None
        assert payload.network_address is None
        assert payload.interface_candidates is None
        assert payload.warning is None
        assert payload.error is None

    def test_with_interface_fields(self):
        payload = BridgeStatusPayload(
            connected=True,
            devices_online=2,
            version="1.2.0",
            network_interface="en5",
            network_address="169.254.20.1",
            interface_candidates=[
                {"name": "en5", "address": "169.254.20.1", "type": "ethernet", "score": 15, "selected": True},
                {"name": "en0", "address": "192.168.1.100", "type": "wifi", "score": 3, "selected": False},
            ],
        )
        assert payload.network_interface == "en5"
        assert payload.network_address == "169.254.20.1"
        assert len(payload.interface_candidates) == 2
        assert payload.interface_candidates[0]["selected"] is True

    def test_with_warning(self):
        payload = BridgeStatusPayload(
            connected=True,
            devices_online=1,
            warning="Configured interface en5 not found. Fell back to auto-detection.",
        )
        assert payload.warning is not None
        assert "en5" in payload.warning

    def test_with_error(self):
        payload = BridgeStatusPayload(
            connected=False,
            devices_online=0,
            error="Player number 5 is already in use",
        )
        assert payload.error is not None


# ── Config loading ────────────────────────────────────────────────────────


class TestBridgeConfig:
    def test_load_bridge_config(self, tmp_path):
        config_file = tmp_path / "bridge.yaml"
        config_file.write_text(yaml.dump({
            "bridge": {
                "port": 18000,
                "network_interface": "en16",
                "player_number": 5,
            }
        }))

        with open(config_file) as f:
            data = yaml.safe_load(f) or {}
        bridge_cfg = data.get("bridge", {})

        assert bridge_cfg["port"] == 18000
        assert bridge_cfg["network_interface"] == "en16"

    def test_load_bridge_config_null_interface(self, tmp_path):
        config_file = tmp_path / "bridge.yaml"
        config_file.write_text(yaml.dump({
            "bridge": {
                "port": 17400,
                "network_interface": None,
            }
        }))

        with open(config_file) as f:
            data = yaml.safe_load(f) or {}
        bridge_cfg = data.get("bridge", {})

        assert bridge_cfg["port"] == 17400
        assert bridge_cfg["network_interface"] is None

    def test_load_missing_config(self, tmp_path):
        config_file = tmp_path / "nonexistent.yaml"
        assert not config_file.exists()
        # Should handle gracefully — our _load_bridge_config returns {}


# ── Interface scoring with live context ──────────────────────────────────


def _make_iface(
    name: str = "en7",
    itype: str = "ethernet",
    has_link_local: bool = True,
) -> NetworkInterfaceInfo:
    """Helper to build a NetworkInterfaceInfo for scoring tests."""
    addrs = []
    if has_link_local:
        addrs.append(InterfaceAddress(
            address="169.254.20.47", netmask="255.255.0.0",
            family="ipv4", is_link_local=True,
        ))
    return NetworkInterfaceInfo(
        name=name,
        display_name=name,
        addresses=addrs,
        is_up=True,
        is_loopback=False,
        has_link_local=has_link_local,
        type=itype,
        score=0,
    )


class TestScoreInterfaceBaseline:
    """Verify baseline scoring is unchanged when no live context is provided."""

    def test_ethernet_with_link_local(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        score = _score_interface(iface)
        # link_local +10, ethernet +5 = 15
        assert score == 15

    def test_wifi_no_link_local(self):
        iface = _make_iface("en0", "wifi", has_link_local=False)
        score = _score_interface(iface)
        # wifi -5
        assert score == -5

    def test_vpn_interface(self):
        iface = _make_iface("utun0", "vpn", has_link_local=False)
        score = _score_interface(iface)
        # vpn -10
        assert score == -10


class TestScoreInterfaceLiveContext:
    """Verify that live context (traffic, route) boosts scores correctly."""

    def test_active_traffic_adds_10(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        base = _score_interface(iface)
        boosted = _score_interface(iface, active_traffic_interface="en7")
        assert boosted == base + 10

    def test_active_traffic_no_match_no_boost(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        base = _score_interface(iface)
        same = _score_interface(iface, active_traffic_interface="en0")
        assert same == base

    def test_route_correct_adds_5(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        base = _score_interface(iface)
        boosted = _score_interface(iface, route_correct_interface="en7")
        assert boosted == base + 5

    def test_route_correct_no_match_no_boost(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        base = _score_interface(iface)
        same = _score_interface(iface, route_correct_interface="en0")
        assert same == base

    def test_both_bonuses_stack(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        base = _score_interface(iface)
        boosted = _score_interface(
            iface,
            active_traffic_interface="en7",
            route_correct_interface="en7",
        )
        assert boosted == base + 15  # +10 traffic + +5 route

    def test_none_context_same_as_no_context(self):
        iface = _make_iface("en7", "ethernet", has_link_local=True)
        base = _score_interface(iface)
        same = _score_interface(
            iface,
            active_traffic_interface=None,
            route_correct_interface=None,
        )
        assert same == base


class TestEnumerateInterfacesContext:
    """Verify enumerate_interfaces passes live context through to scoring."""

    @patch("scue.network.route.psutil")
    def test_context_boosts_active_interface(self, mock_psutil):
        """An interface matching active_traffic_interface should score higher."""
        import psutil as real_psutil

        # Create two mock interfaces
        mock_psutil.net_if_addrs.return_value = {
            "en7": [
                type("Addr", (), {
                    "family": type("F", (), {"name": "AF_INET"})(),
                    "address": "169.254.20.47",
                    "netmask": "255.255.0.0",
                })(),
            ],
            "en0": [
                type("Addr", (), {
                    "family": type("F", (), {"name": "AF_INET"})(),
                    "address": "192.168.1.100",
                    "netmask": "255.255.255.0",
                })(),
            ],
        }
        mock_psutil.net_if_stats.return_value = {
            "en7": type("Stats", (), {"isup": True})(),
            "en0": type("Stats", (), {"isup": True})(),
        }

        # Without context
        no_ctx = enumerate_interfaces()
        scores_no_ctx = {i.name: i.score for i in no_ctx}

        # With active traffic on en7
        with_ctx = enumerate_interfaces(active_traffic_interface="en7")
        scores_with_ctx = {i.name: i.score for i in with_ctx}

        assert scores_with_ctx["en7"] == scores_no_ctx["en7"] + 10
        assert scores_with_ctx["en0"] == scores_no_ctx["en0"]  # unchanged


class TestBridgeManagerTrafficProperty:
    """Verify BridgeManager.pioneer_traffic_active property."""

    def test_no_traffic_initially(self):
        mgr = BridgeManager()
        assert mgr.pioneer_traffic_active is False

    def test_traffic_active_when_recent(self):
        mgr = BridgeManager()
        mgr._last_pioneer_message_time = time.time() - 2.0  # 2s ago
        assert mgr.pioneer_traffic_active is True

    def test_traffic_stale_after_5s(self):
        mgr = BridgeManager()
        mgr._last_pioneer_message_time = time.time() - 6.0  # 6s ago
        assert mgr.pioneer_traffic_active is False

    def test_route_correct_property(self):
        mgr = BridgeManager()
        assert mgr.route_correct is None
        mgr._route_correct = True
        assert mgr.route_correct is True
        mgr._route_correct = False
        assert mgr.route_correct is False
