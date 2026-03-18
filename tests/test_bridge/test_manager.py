"""Tests for bridge manager — state machine, graceful degradation."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scue.bridge.manager import BridgeManager
from scue.bridge.messages import BridgeMessage

# Default config values — match BridgeManager constructor defaults
RESTART_BASE_DELAY = 2.0
RESTART_MAX_DELAY = 30.0
MAX_CRASH_BEFORE_FALLBACK = 3


class TestManagerStateTransitions:
    """Test manager state machine without real subprocess/WebSocket."""

    @pytest.mark.asyncio
    async def test_initial_state_is_stopped(self):
        mgr = BridgeManager()
        assert mgr.status == "stopped"

    @pytest.mark.asyncio
    async def test_no_jre_transitions_to_fallback(self):
        mgr = BridgeManager()
        with patch.object(mgr, "_check_jre", return_value=False), \
             patch.object(mgr, "_start_fallback", new_callable=AsyncMock) as mock_fb:
            await mgr.start()
        mock_fb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_jar_transitions_to_fallback(self):
        mgr = BridgeManager(jar_path=Path("/nonexistent/bridge.jar"))
        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_start_fallback", new_callable=AsyncMock) as mock_fb:
            await mgr.start()
        mock_fb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_from_fallback(self):
        mgr = BridgeManager()
        mgr._status = "fallback"
        mgr._fallback_parser = MagicMock()
        await mgr.stop()
        mgr._fallback_parser = None  # cleaned up by _stop_fallback
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
            uses_dlp=True,
        )
        mgr.adapter._players[1] = PlayerState(
            player_number=1,
            bpm=128.0,
            playback_state="playing",
            is_on_air=True,
            rekordbox_id=42,
        )

        status = mgr.to_status_dict()
        assert "169.254.20.101" in status["devices"]
        assert status["devices"]["169.254.20.101"]["device_name"] == "XDJ-AZ"
        assert status["devices"]["169.254.20.101"]["uses_dlp"] is True
        assert "1" in status["players"]
        assert status["players"]["1"]["bpm"] == 128.0
        assert status["players"]["1"]["playback_state"] == "playing"
        assert status["players"]["1"]["rekordbox_id"] == 42


class TestManagerPort:
    def test_default_port(self):
        mgr = BridgeManager()
        assert mgr.port == 17400

    def test_custom_port(self):
        mgr = BridgeManager(port=18000)
        assert mgr.port == 18000


class TestPioneerMessageTracking:
    """Verify that _last_pioneer_message_time is only updated by
    Pioneer-originated messages (device_found, player_status, beat, etc.),
    NOT by bridge_status heartbeats."""

    def _make_msg(self, msg_type: str, player_number: int | None = None) -> BridgeMessage:
        return BridgeMessage(
            type=msg_type,
            timestamp=time.time(),
            player_number=player_number,
            payload={},
        )

    def test_initial_pioneer_time_is_zero(self):
        mgr = BridgeManager()
        assert mgr._last_pioneer_message_time == 0.0

    def test_bridge_status_does_not_update_pioneer_time(self):
        """bridge_status messages must NOT update _last_pioneer_message_time."""
        mgr = BridgeManager()
        msg = self._make_msg("bridge_status")
        # Simulate what _listen_loop does
        now = time.time()
        mgr._last_message_time = now
        if msg.type != "bridge_status":
            mgr._last_pioneer_message_time = now
        mgr._adapter.handle_message(msg)

        assert mgr._last_pioneer_message_time == 0.0
        assert mgr._last_message_time == now

    def test_device_found_updates_pioneer_time(self):
        """device_found messages MUST update _last_pioneer_message_time."""
        mgr = BridgeManager()
        msg = BridgeMessage(
            type="device_found",
            timestamp=time.time(),
            player_number=1,
            payload={
                "device_name": "XDJ-AZ",
                "device_number": 1,
                "device_type": "cdj",
                "ip_address": "169.254.20.101",
                "uses_dlp": True,
            },
        )
        now = time.time()
        mgr._last_message_time = now
        if msg.type != "bridge_status":
            mgr._last_pioneer_message_time = now
        mgr._adapter.handle_message(msg)

        assert mgr._last_pioneer_message_time == now

    def test_player_status_updates_pioneer_time(self):
        """player_status messages MUST update _last_pioneer_message_time."""
        mgr = BridgeManager()
        msg = BridgeMessage(
            type="player_status",
            timestamp=time.time(),
            player_number=1,
            payload={
                "bpm": 128.0, "pitch": 0.0, "beat_within_bar": 1,
                "beat_number": 1, "playback_state": "playing", "is_on_air": True,
            },
        )
        now = time.time()
        mgr._last_message_time = now
        if msg.type != "bridge_status":
            mgr._last_pioneer_message_time = now

        assert mgr._last_pioneer_message_time == now

    def test_beat_updates_pioneer_time(self):
        """beat messages MUST update _last_pioneer_message_time."""
        mgr = BridgeManager()
        msg = self._make_msg("beat", player_number=1)
        now = time.time()
        mgr._last_message_time = now
        if msg.type != "bridge_status":
            mgr._last_pioneer_message_time = now

        assert mgr._last_pioneer_message_time == now

    def test_mixed_messages_only_pioneer_updates_pioneer_time(self):
        """Sequence of bridge_status then device_found: only device_found
        should update pioneer time."""
        mgr = BridgeManager()

        # Process bridge_status
        bs_msg = self._make_msg("bridge_status")
        t1 = time.time()
        mgr._last_message_time = t1
        if bs_msg.type != "bridge_status":
            mgr._last_pioneer_message_time = t1
        mgr._adapter.handle_message(bs_msg)
        assert mgr._last_pioneer_message_time == 0.0

        # Process device_found
        df_msg = BridgeMessage(
            type="device_found",
            timestamp=time.time(),
            player_number=1,
            payload={
                "device_name": "XDJ-AZ",
                "device_number": 1,
                "device_type": "cdj",
                "ip_address": "169.254.20.101",
                "uses_dlp": True,
            },
        )
        t2 = time.time()
        mgr._last_message_time = t2
        if df_msg.type != "bridge_status":
            mgr._last_pioneer_message_time = t2
        mgr._adapter.handle_message(df_msg)

        assert mgr._last_pioneer_message_time == t2
        assert mgr._last_message_time == t2


class TestRestartLogic:
    """Test immediate-first-then-backoff restart behavior."""

    def _make_manager(self) -> BridgeManager:
        mgr = BridgeManager()
        # Prevent actual start() from launching subprocess
        mgr.start = AsyncMock()
        return mgr

    @pytest.mark.asyncio
    async def test_first_failure_immediate_retry(self):
        """First crash should retry with 0 delay."""
        mgr = self._make_manager()
        mgr._status = "crashed"

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == 1
        # Should NOT have called asyncio.sleep (delay == 0)
        mock_sleep.assert_not_called()
        # start() should have been called
        mgr.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_failure_base_backoff(self):
        """Second consecutive crash should use base delay (2s)."""
        mgr = self._make_manager()
        mgr._consecutive_failures = 1  # Already had one failure

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == 2
        mock_sleep.assert_awaited_once()
        delay = mock_sleep.call_args[0][0]
        assert delay == RESTART_BASE_DELAY  # 2.0s

    @pytest.mark.asyncio
    async def test_third_failure_transitions_to_fallback(self):
        """Third consecutive crash should switch to fallback (threshold=3)."""
        mgr = self._make_manager()
        mgr._consecutive_failures = 2

        with patch.object(mgr, "_start_fallback", new_callable=AsyncMock) as mock_fb:
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == 3
        mock_fb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crash_threshold_transitions_to_fallback(self):
        """After MAX_CRASH_BEFORE_FALLBACK consecutive crashes, switch to fallback."""
        mgr = self._make_manager()
        mgr._consecutive_failures = MAX_CRASH_BEFORE_FALLBACK - 1  # One more → threshold

        with patch.object(mgr, "_start_fallback", new_callable=AsyncMock) as mock_fb:
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == MAX_CRASH_BEFORE_FALLBACK
        mock_fb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_resets_failure_counter(self):
        """Successful start() should reset _consecutive_failures to 0."""
        mgr = BridgeManager()
        mgr._consecutive_failures = 5
        mgr._next_retry_at = time.time() + 10

        # Simulate a successful start reaching the "running" state
        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.start()

        assert mgr._consecutive_failures == 0
        assert mgr._next_retry_at is None
        assert mgr.status == "running"

    @pytest.mark.asyncio
    async def test_after_reset_next_crash_is_immediate(self):
        """After a successful start resets the counter, next crash should retry immediately."""
        mgr = self._make_manager()

        # Simulate: had failures, then success, then crash again
        mgr._consecutive_failures = 0  # Reset after success

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_jre_goes_to_fallback_not_retry(self):
        """no_jre should transition to fallback, not trigger _schedule_restart."""
        mgr = BridgeManager()
        with patch.object(mgr, "_check_jre", return_value=False), \
             patch.object(mgr, "_start_fallback", new_callable=AsyncMock):
            await mgr.start()

        assert mgr._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_no_jar_goes_to_fallback_not_retry(self):
        """no_jar should transition to fallback, not trigger _schedule_restart."""
        mgr = BridgeManager(jar_path=Path("/nonexistent/bridge.jar"))
        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_start_fallback", new_callable=AsyncMock):
            await mgr.start()

        assert mgr._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_backoff_progression(self):
        """Verify backoff sequence before fallback threshold: 0, 2."""
        # With MAX_CRASH_BEFORE_FALLBACK=3, only 2 retries happen before fallback
        expected_delays = [0.0, 2.0]
        mgr = self._make_manager()

        for i, expected in enumerate(expected_delays):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await mgr._schedule_restart()
                mgr.start.reset_mock()

                if expected == 0.0:
                    mock_sleep.assert_not_called()
                else:
                    delay = mock_sleep.call_args[0][0]
                    assert delay == expected, (
                        f"Attempt {i + 1}: expected {expected}s, got {delay}s"
                    )


class TestStatusDictRestartFields:
    """Test that to_status_dict() exposes restart state."""

    def test_running_state_has_zero_restart_fields(self):
        """When running normally, restart_attempt=0 and next_retry_in_s=None."""
        mgr = BridgeManager()
        mgr._status = "running"
        status = mgr.to_status_dict()

        assert status["restart_attempt"] == 0
        assert status["next_retry_in_s"] is None

    def test_crashed_state_shows_failure_count(self):
        """After failures, restart_attempt reflects consecutive_failures."""
        mgr = BridgeManager()
        mgr._consecutive_failures = 3
        status = mgr.to_status_dict()

        assert status["restart_attempt"] == 3

    def test_next_retry_in_s_when_waiting(self):
        """next_retry_in_s should show remaining time when a retry is scheduled."""
        mgr = BridgeManager()
        mgr._next_retry_at = time.time() + 5.0
        status = mgr.to_status_dict()

        assert status["next_retry_in_s"] is not None
        assert 4.0 < status["next_retry_in_s"] <= 5.0

    def test_next_retry_in_s_clamps_to_zero(self):
        """next_retry_in_s should not go negative if retry time has passed."""
        mgr = BridgeManager()
        mgr._next_retry_at = time.time() - 1.0  # Already past
        status = mgr.to_status_dict()

        assert status["next_retry_in_s"] == 0.0

    def test_restart_count_backward_compat(self):
        """restart_count field should still be present (backward compat)."""
        mgr = BridgeManager()
        mgr._consecutive_failures = 2
        status = mgr.to_status_dict()

        assert status["restart_count"] == 2
        assert status["restart_attempt"] == 2


class TestFallbackIntegration:
    """Test fallback parser integration in the manager."""

    @pytest.mark.asyncio
    async def test_fallback_messages_flow_through_adapter(self):
        """Fallback parser messages should reach both adapter and external callback."""
        received: list[BridgeMessage] = []
        mgr = BridgeManager(on_message=lambda msg: received.append(msg))

        msg = BridgeMessage(
            type="device_found",
            timestamp=time.time(),
            player_number=1,
            payload={
                "device_name": "XDJ-AZ",
                "device_number": 1,
                "device_type": "cdj",
                "ip_address": "169.254.20.101",
            },
        )

        # Simulate what _fallback_on_message does
        mgr._fallback_on_message(msg)

        assert len(received) == 1
        assert received[0].type == "device_found"
        # Adapter should have processed the device
        assert "169.254.20.101" in mgr.adapter.devices

    @pytest.mark.asyncio
    async def test_restart_from_fallback_stops_parser(self):
        """Calling restart() from fallback should stop parser and attempt bridge."""
        mgr = BridgeManager()
        mgr._status = "fallback"
        mock_parser = MagicMock()
        mgr._fallback_parser = mock_parser

        with patch.object(mgr, "_check_jre", return_value=False), \
             patch.object(mgr, "_start_fallback", new_callable=AsyncMock):
            await mgr.restart()

        mock_parser.stop.assert_called_once()

    def test_status_dict_reflects_fallback(self):
        """to_status_dict() should return status='fallback' and mode='fallback'."""
        mgr = BridgeManager()
        mgr._status = "fallback"
        status = mgr.to_status_dict()

        assert status["status"] == "fallback"
        assert status["mode"] == "fallback"

    def test_status_dict_mode_bridge_when_running(self):
        """to_status_dict() should return mode='bridge' when not in fallback."""
        mgr = BridgeManager()
        mgr._status = "running"
        status = mgr.to_status_dict()

        assert status["mode"] == "bridge"

    @pytest.mark.asyncio
    async def test_stop_from_fallback_stops_parser(self):
        """stop() should clean up fallback parser."""
        mgr = BridgeManager()
        mgr._status = "fallback"
        mock_parser = MagicMock()
        mgr._fallback_parser = mock_parser

        await mgr.stop()

        mock_parser.stop.assert_called_once()
        assert mgr._fallback_parser is None
        assert mgr.status == "stopped"

    @pytest.mark.asyncio
    async def test_start_fallback_sets_state(self):
        """_start_fallback() should set status to 'fallback' and store parser."""
        mgr = BridgeManager()

        with patch(
            "scue.bridge.manager.FallbackParser"
        ) as MockParser:
            mock_instance = MockParser.return_value
            mock_instance.start = AsyncMock()
            await mgr._start_fallback()

        assert mgr.status == "fallback"
        assert mgr._fallback_parser is mock_instance
        mock_instance.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_consecutive_failures_preserved_after_fallback_transition(self):
        """After transitioning to fallback via crashes, failure count is preserved."""
        mgr = BridgeManager()
        mgr.start = AsyncMock()  # Prevent real start
        mgr._consecutive_failures = MAX_CRASH_BEFORE_FALLBACK - 1

        with patch.object(mgr, "_start_fallback", new_callable=AsyncMock):
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == MAX_CRASH_BEFORE_FALLBACK
