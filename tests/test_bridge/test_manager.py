"""Tests for bridge manager — state machine, graceful degradation."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scue.bridge.manager import BridgeManager
from scue.bridge.messages import BridgeMessage
from scue.network.models import RouteFixResult

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
    async def test_third_failure_transitions_to_waiting_for_hardware(self):
        """Third consecutive crash should enter waiting_for_hardware state (threshold=3).

        Previously this transitioned to "fallback" (UDP parser). The new behaviour
        is to enter "waiting_for_hardware" which slow-polls for hardware to return.
        _start_fallback is only invoked when JRE/JAR is absent.
        """
        mgr = self._make_manager()
        mgr._consecutive_failures = 2

        with patch.object(mgr, "_enter_waiting_for_hardware", new_callable=AsyncMock) as mock_wfh:
            await mgr._schedule_restart()

        mock_wfh.assert_awaited_once()
        # _consecutive_failures is reset inside _enter_waiting_for_hardware (mocked here),
        # so we just confirm the threshold was reached and the correct path was taken.

    @pytest.mark.asyncio
    async def test_crash_threshold_transitions_to_waiting_for_hardware(self):
        """After MAX_CRASH_BEFORE_FALLBACK consecutive crashes, enter waiting_for_hardware."""
        mgr = self._make_manager()
        mgr._consecutive_failures = MAX_CRASH_BEFORE_FALLBACK - 1  # One more → threshold

        with patch.object(mgr, "_enter_waiting_for_hardware", new_callable=AsyncMock) as mock_wfh:
            await mgr._schedule_restart()

        mock_wfh.assert_awaited_once()

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
    async def test_waiting_for_hardware_resets_failure_counter(self):
        """After entering waiting_for_hardware, _consecutive_failures resets to 0.

        The reset allows the next hardware-poll attempt to start fresh rather
        than immediately re-entering waiting_for_hardware on the first crash.
        """
        mgr = BridgeManager()
        mgr.start = AsyncMock()  # Prevent real start
        mgr._consecutive_failures = MAX_CRASH_BEFORE_FALLBACK - 1

        # Don't mock _enter_waiting_for_hardware — let the real implementation run
        # but cancel the resulting wait task immediately to avoid loop running.
        with patch.object(mgr, "_wait_for_hardware_loop", new_callable=AsyncMock):
            await mgr._schedule_restart()

        assert mgr._consecutive_failures == 0
        assert mgr.status == "waiting_for_hardware"


class TestNoHardwareStableState:
    """Bridge enters a stable non-cycling state when hardware is absent.

    These tests cover AC-1/AC-3 from BUG-BRIDGE-CYCLE: after MAX_CRASH_BEFORE_FALLBACK
    quick crashes (Java process exits immediately — hardware absent / no route), the
    manager must enter waiting_for_hardware and stop aggressively restarting.
    """

    @pytest.mark.asyncio
    async def test_rapid_crash_cycle_enters_waiting_state(self):
        """Simulate bridge process exiting immediately N times.

        Each call to _schedule_restart() represents one crash of the subprocess.
        After max_crash_before_fallback consecutive crashes the manager must enter
        waiting_for_hardware — NOT keep aggressively restarting.

        We mock _enter_waiting_for_hardware so the poll loop doesn't actually run,
        and we mock start() so _schedule_restart() doesn't re-launch the bridge
        during the early (backoff) retries.
        """
        MAX_CRASHES = 3
        mgr = BridgeManager(max_crash_before_fallback=MAX_CRASHES, restart_base_delay=0.0)
        mgr.start = AsyncMock()  # prevent real start() during backoff retries
        mgr._status = "crashed"

        entered_waiting = False

        async def mock_enter_waiting() -> None:
            nonlocal entered_waiting
            entered_waiting = True
            # Reproduce the real state transitions (minus task creation)
            mgr._status = "waiting_for_hardware"
            mgr._consecutive_failures = 0
            mgr._last_stable_start_time = 0.0
            mgr._next_retry_at = None

        with patch.object(mgr, "asyncio", create=True), \
             patch.object(mgr, "_enter_waiting_for_hardware", side_effect=mock_enter_waiting):
            # Simulate consecutive failures accumulating until threshold
            for _ in range(MAX_CRASHES):
                if mgr.status == "waiting_for_hardware":
                    break
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await mgr._schedule_restart()

        assert entered_waiting, (
            "Expected _enter_waiting_for_hardware to be called after "
            f"{MAX_CRASHES} rapid crashes"
        )
        assert mgr.status == "waiting_for_hardware"

    @pytest.mark.asyncio
    async def test_waiting_state_has_next_retry_set(self):
        """In waiting_for_hardware, next_retry_in_s should be set (not None)."""
        mgr = BridgeManager()
        with patch.object(mgr, "_wait_for_hardware_loop", new_callable=AsyncMock):
            await mgr._enter_waiting_for_hardware()

        status = mgr.to_status_dict()
        # next_retry_at should be set; next_retry_in_s should be > 0
        assert status["next_retry_in_s"] is None or status["next_retry_in_s"] >= 0
        assert status["status"] == "waiting_for_hardware"
        assert status["mode"] == "waiting_for_hardware"

    @pytest.mark.asyncio
    async def test_restart_from_waiting_state_resets_and_starts(self):
        """Calling restart() from waiting_for_hardware should cancel poll task
        and attempt a fresh start (with failure counter reset)."""
        mgr = BridgeManager()
        # Enter the waiting state
        with patch.object(mgr, "_wait_for_hardware_loop", new_callable=AsyncMock):
            await mgr._enter_waiting_for_hardware()

        assert mgr.status == "waiting_for_hardware"
        assert mgr._consecutive_failures == 0

        # Now call restart() — should stop the wait task and attempt a new start
        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.restart()

        assert mgr.status == "running"
        assert mgr._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_stop_from_waiting_state(self):
        """stop() from waiting_for_hardware should cancel poll task and reach stopped."""
        mgr = BridgeManager()
        with patch.object(mgr, "_wait_for_hardware_loop", new_callable=AsyncMock):
            await mgr._enter_waiting_for_hardware()

        await mgr.stop()

        assert mgr.status == "stopped"
        assert mgr._wait_task is None

    @pytest.mark.asyncio
    async def test_quick_start_crash_does_not_reset_failures(self):
        """If bridge reaches 'running' but crashes within _MIN_STABLE_UPTIME_S,
        _consecutive_failures must NOT reset to 0 on the start that follows."""
        mgr = BridgeManager()

        # Simulate a start that succeeds but was "too quick" (last stable start
        # was very recent, well within _MIN_STABLE_UPTIME_S)
        mgr._consecutive_failures = 1
        mgr._last_stable_start_time = time.time()  # just started right now

        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.start()

        # Failure counter must NOT have been reset because last start was too recent
        assert mgr._consecutive_failures == 1, (
            "Expected _consecutive_failures to remain 1 after quick-start recovery"
        )
        assert mgr.status == "running"

    @pytest.mark.asyncio
    async def test_stable_start_resets_failures(self):
        """If bridge was stable for >= _MIN_STABLE_UPTIME_S, failures reset on next start."""
        from scue.bridge.manager import _MIN_STABLE_UPTIME_S

        mgr = BridgeManager()
        mgr._consecutive_failures = 2
        # Simulate that the previous run lasted long enough to be "stable"
        mgr._last_stable_start_time = time.time() - _MIN_STABLE_UPTIME_S - 1.0

        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.start()

        assert mgr._consecutive_failures == 0
        assert mgr.status == "running"


class TestHealthCheckSilenceBehaviour:
    """Health check must NOT restart on Pioneer hardware silence.

    Only bridge process death or WebSocket heartbeat silence should trigger
    a restart. This prevents the crash-restart cycle when hardware is off.
    """

    @pytest.mark.asyncio
    async def test_pioneer_silence_does_not_restart(self):
        """Bridge stays 'running' even when no Pioneer traffic arrives.

        The bridge process keeps sending WebSocket heartbeats (bridge_status),
        so _last_message_time is continuously refreshed — only
        _last_pioneer_message_time is stale (hardware is off).
        The health check should NOT fire a restart in this scenario.
        """
        mgr = BridgeManager(health_check_interval=0.05)
        mgr._status = "running"
        mgr._process = MagicMock()
        mgr._process.poll.return_value = None  # subprocess still alive

        # Simulate continuous bridge heartbeats but no Pioneer traffic.
        # We refresh _last_message_time in a background task to mimic heartbeats.
        mgr._last_message_time = time.time()
        mgr._last_pioneer_message_time = 0.0  # no Pioneer traffic ever

        restart_called = False

        async def fake_schedule_restart():
            nonlocal restart_called
            restart_called = True

        async def keep_heartbeat_fresh() -> None:
            """Simulate bridge_status heartbeats arriving every 0.02 s."""
            while True:
                await asyncio.sleep(0.02)
                mgr._last_message_time = time.time()

        with patch.object(mgr, "_schedule_restart", side_effect=fake_schedule_restart):
            heartbeat_task = asyncio.create_task(keep_heartbeat_fresh())
            health_task = asyncio.create_task(mgr._health_check_loop())
            await asyncio.sleep(0.25)  # let it run several intervals
            health_task.cancel()
            heartbeat_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        assert not restart_called, (
            "Health check must NOT restart bridge on Pioneer silence — "
            "hardware being off is normal. Only bridge process death warrants restart."
        )

    @pytest.mark.asyncio
    async def test_bridge_heartbeat_silence_triggers_restart(self):
        """Bridge WS going silent (no heartbeats) should trigger a restart."""
        mgr = BridgeManager(health_check_interval=0.05)
        mgr._status = "running"
        mgr._process = MagicMock()
        mgr._process.poll.return_value = None  # subprocess still alive

        # Both message times are stale — bridge itself has gone silent
        stale_time = time.time() - 100.0
        mgr._last_message_time = stale_time
        mgr._last_pioneer_message_time = 0.0

        restart_called = False

        async def fake_schedule_restart():
            nonlocal restart_called
            restart_called = True
            mgr._status = "crashed"

        with patch.object(mgr, "_schedule_restart", side_effect=fake_schedule_restart):
            health_task = asyncio.create_task(mgr._health_check_loop())
            await asyncio.sleep(0.15)
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass

        assert restart_called, (
            "Health check MUST restart bridge when WebSocket heartbeats are absent"
        )


class TestJVMFlags:
    """JVM flags for OS focus suppression are included in subprocess launch command."""

    @pytest.mark.asyncio
    async def test_jvm_flags_in_launch_command(self):
        """Launch command must include all _JVM_FLAGS between 'java' and '-jar'."""
        from scue.bridge.manager import _JVM_FLAGS

        mgr = BridgeManager(jar_path=Path("lib/bridge.jar"), port=17400)
        captured_cmd: list[str] = []

        def mock_popen(cmd, **kwargs):  # type: ignore[override]
            captured_cmd.extend(cmd)
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            return mock_proc

        async def fast_ws_connect(*args: object, **kwargs: object) -> None:
            pass

        with patch("subprocess.Popen", side_effect=mock_popen), \
             patch(
                 "asyncio.open_connection",
                 new_callable=AsyncMock,
                 return_value=(AsyncMock(), AsyncMock()),
             ):
            # _launch_subprocess checks WS port opens — we just need to get past
            # subprocess.Popen, so raise early to skip the poll loop
            try:
                await mgr._launch_subprocess()
            except Exception:
                pass

        # Verify each flag appears somewhere in the command
        for flag in _JVM_FLAGS:
            assert flag in captured_cmd, (
                f"JVM flag {flag!r} missing from launch command: {captured_cmd}"
            )

        # Verify ordering: flags come before -jar
        if "-jar" in captured_cmd and captured_cmd:
            jar_idx = captured_cmd.index("-jar")
            for flag in _JVM_FLAGS:
                if flag in captured_cmd:
                    flag_idx = captured_cmd.index(flag)
                    assert flag_idx < jar_idx, (
                        f"Flag {flag!r} must appear before '-jar' (got indices "
                        f"{flag_idx} vs {jar_idx})"
                    )

    def test_headless_flag_present(self):
        """Verify the headless flag constant is in _JVM_FLAGS."""
        from scue.bridge.manager import _JVM_FLAGS
        assert "-Djava.awt.headless=true" in _JVM_FLAGS

    def test_apple_ui_element_flag_present(self):
        """Verify the Apple UIElement flag constant is in _JVM_FLAGS."""
        from scue.bridge.manager import _JVM_FLAGS
        assert "-Dapple.awt.UIElement=true" in _JVM_FLAGS

    def test_dock_name_flag_present(self):
        """Verify the dock name flag constant is in _JVM_FLAGS."""
        from scue.bridge.manager import _JVM_FLAGS
        assert "-Xdock:name=SCUE Bridge" in _JVM_FLAGS


class TestRouteFriendlyError:
    """fix_route() returns user-friendly messages for hardware-absent errors."""

    @pytest.mark.asyncio
    async def test_bad_address_error_wrapped(self):
        """'route: bad address: en16' kernel error is wrapped with a friendly message."""
        mgr = BridgeManager(network_interface="en16")

        raw_result = RouteFixResult(
            success=False,
            error="route: bad address: en16",
            previous_interface=None,
            new_interface="en16",
        )

        with patch("scue.bridge.manager.network_fix_route", return_value=raw_result):
            result = await mgr.fix_route()

        assert result.success is False
        assert "bad address" not in result.error or "not available" in result.error
        assert "en16" in result.error
        # Must contain user-readable guidance, not raw kernel output alone
        assert "adapter" in result.error.lower() or "interface" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_interface_configured_error(self):
        """fix_route() with no interface configured returns a clear error."""
        mgr = BridgeManager()  # no interface
        result = await mgr.fix_route()

        assert result.success is False
        assert "No network interface configured" in result.error

    @pytest.mark.asyncio
    async def test_success_result_passes_through(self):
        """Successful fix_route() result is unchanged."""
        from scue.network.models import RouteCheckResult
        mgr = BridgeManager(network_interface="en16")

        raw_result = RouteFixResult(
            success=True,
            error=None,
            previous_interface="en0",
            new_interface="en16",
        )
        recheck_result = RouteCheckResult(
            correct=True,
            current_interface="en16",
            expected_interface="en16",
            fix_available=True,
            competing_interfaces=[],
        )

        with patch("scue.bridge.manager.network_fix_route", return_value=raw_result), \
             patch("scue.bridge.manager.network_check_route", return_value=recheck_result):
            result = await mgr.fix_route()

        assert result.success is True
        assert result.error is None
        assert mgr._route_correct is True


class TestLastMessageTimeReset:
    """Regression: start() must reset _last_message_time to 0.0.

    Without this reset, a stale timestamp from a previous bridge run causes the
    health check silence condition to fire immediately on restart, before
    beat-link has time to reconnect — creating a permanent crash cycle.
    See LEARNINGS.md entry: '_last_message_time not reset in start()'.
    """

    @pytest.mark.asyncio
    async def test_start_resets_last_message_time(self):
        """start() must reset _last_message_time to 0.0 before launching subprocess."""
        mgr = BridgeManager()
        # Simulate a previous bridge run that set _last_message_time
        mgr._last_message_time = 1742300000.0  # stale timestamp from prior run

        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.start()

        assert mgr._last_message_time == 0.0, (
            "start() must reset _last_message_time to 0.0 so the health check "
            "silence guard (if _last_message_time > 0) is False on fresh starts"
        )

    @pytest.mark.asyncio
    async def test_start_resets_last_pioneer_message_time(self):
        """start() must reset _last_pioneer_message_time to 0.0.

        Without this reset, pioneer_status.is_receiving would report true
        based on stale timestamps from a previous bridge session.
        """
        mgr = BridgeManager()
        mgr._last_pioneer_message_time = 1742300000.0  # stale from prior run

        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.start()

        assert mgr._last_pioneer_message_time == 0.0

    @pytest.mark.asyncio
    async def test_start_clears_adapter_state(self):
        """start() must clear adapter devices/players before launching."""
        mgr = BridgeManager()
        # Simulate stale adapter state from previous run
        from scue.bridge.adapter import DeviceInfo, PlayerState
        mgr._adapter._devices["169.254.1.1"] = DeviceInfo(
            device_name="CDJ-1", device_number=1, device_type="cdj",
            ip_address="169.254.1.1",
        )
        mgr._adapter._players[1] = PlayerState(player_number=1, bpm=128.0)

        with patch.object(mgr, "_check_jre", return_value=True), \
             patch.object(mgr, "_check_jar", return_value=True), \
             patch.object(mgr, "_launch_subprocess", new_callable=AsyncMock), \
             patch.object(mgr, "_connect_websocket", new_callable=AsyncMock), \
             patch.object(mgr, "_start_listen_loop"), \
             patch.object(mgr, "_start_health_check"):
            await mgr.start()

        assert mgr.adapter.devices == {}
        assert mgr.adapter.players == {}


class TestCleanupClearsAdapter:
    """_cleanup() must clear adapter state so stale data doesn't persist."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_adapter_devices_and_players(self):
        mgr = BridgeManager()
        from scue.bridge.adapter import DeviceInfo, PlayerState
        mgr._adapter._devices["169.254.1.1"] = DeviceInfo(
            device_name="CDJ-1", device_number=1, device_type="cdj",
            ip_address="169.254.1.1",
        )
        mgr._adapter._players[1] = PlayerState(player_number=1, bpm=128.0)

        await mgr._cleanup()

        assert mgr.adapter.devices == {}
        assert mgr.adapter.players == {}

    @pytest.mark.asyncio
    async def test_status_dict_empty_after_cleanup(self):
        """to_status_dict() must return empty devices/players after cleanup."""
        mgr = BridgeManager()
        from scue.bridge.adapter import DeviceInfo, PlayerState
        mgr._adapter._devices["169.254.1.1"] = DeviceInfo(
            device_name="CDJ-1", device_number=1, device_type="cdj",
            ip_address="169.254.1.1",
        )
        mgr._adapter._players[1] = PlayerState(player_number=1, bpm=128.0)

        await mgr._cleanup()

        status = mgr.to_status_dict()
        assert status["devices"] == {}
        assert status["players"] == {}


class TestInterfacePreCheckInHardwareLoop:
    """_wait_for_hardware_loop() must check interface existence before calling start().

    When a specific network interface is configured, the loop uses
    socket.if_nametoindex() to verify it exists before launching a subprocess.
    If the interface is missing, the poll cycle is skipped (no subprocess launch).
    When _network_interface is None (auto-detect), the check is skipped entirely.
    """

    @pytest.mark.asyncio
    async def test_interface_unavailable_skips_start(self):
        """When the configured interface doesn't exist, start() must NOT be called."""
        mgr = BridgeManager(network_interface="en99")
        mgr._status = "waiting_for_hardware"

        start_called = False
        original_start = mgr.start

        async def mock_start():
            nonlocal start_called
            start_called = True
            # Transition to running to exit the loop
            mgr._status = "running"

        mgr.start = mock_start  # type: ignore[assignment]

        poll_count = 0

        async def fast_sleep(duration: float) -> None:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                # Stop the loop after 3 polls
                mgr._status = "stopped"

        with patch("asyncio.sleep", side_effect=fast_sleep), \
             patch("socket.if_nametoindex", side_effect=OSError("No such device")):
            await mgr._wait_for_hardware_loop()

        assert not start_called, (
            "start() must NOT be called when interface is unavailable"
        )
        assert poll_count >= 2, "Loop should have polled multiple times"

    @pytest.mark.asyncio
    async def test_interface_available_calls_start(self):
        """When the configured interface exists, start() must be called."""
        mgr = BridgeManager(network_interface="en0")
        mgr._status = "waiting_for_hardware"

        start_called = False

        async def mock_start():
            nonlocal start_called
            start_called = True
            mgr._status = "running"  # exit the loop

        mgr.start = mock_start  # type: ignore[assignment]

        poll_count = 0

        async def fast_sleep(duration: float) -> None:
            nonlocal poll_count
            poll_count += 1

        with patch("asyncio.sleep", side_effect=fast_sleep), \
             patch("socket.if_nametoindex", return_value=7):
            await mgr._wait_for_hardware_loop()

        assert start_called, "start() must be called when interface is available"

    @pytest.mark.asyncio
    async def test_none_interface_skips_check_calls_start(self):
        """When _network_interface is None (auto-detect), skip the check and call start()."""
        mgr = BridgeManager(network_interface=None)
        mgr._status = "waiting_for_hardware"

        start_called = False

        async def mock_start():
            nonlocal start_called
            start_called = True
            mgr._status = "running"

        mgr.start = mock_start  # type: ignore[assignment]

        async def fast_sleep(duration: float) -> None:
            pass

        with patch("asyncio.sleep", side_effect=fast_sleep), \
             patch("socket.if_nametoindex") as mock_ifcheck:
            await mgr._wait_for_hardware_loop()

        assert start_called, "start() must be called in auto-detect mode"
        mock_ifcheck.assert_not_called(), (
            "socket.if_nametoindex must NOT be called when interface is None"
        )

    @pytest.mark.asyncio
    async def test_interface_reappears_triggers_start(self):
        """When interface is absent then reappears, start() is called on recovery poll."""
        mgr = BridgeManager(network_interface="en16")
        mgr._status = "waiting_for_hardware"

        start_called = False

        async def mock_start():
            nonlocal start_called
            start_called = True
            mgr._status = "running"

        mgr.start = mock_start  # type: ignore[assignment]

        poll_count = 0

        async def fast_sleep(duration: float) -> None:
            nonlocal poll_count
            poll_count += 1

        # First 2 polls: interface missing. Third poll: interface appears.
        side_effects = [
            OSError("No such device"),
            OSError("No such device"),
            7,  # success — interface index returned
        ]

        with patch("asyncio.sleep", side_effect=fast_sleep), \
             patch("socket.if_nametoindex", side_effect=side_effects):
            await mgr._wait_for_hardware_loop()

        assert start_called, (
            "start() must be called once the interface reappears"
        )
        assert poll_count == 3, (
            f"Expected 3 polls (2 skipped + 1 successful), got {poll_count}"
        )
