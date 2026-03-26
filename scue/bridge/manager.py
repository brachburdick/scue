"""Bridge manager — subprocess lifecycle, WebSocket connection, and health monitoring.

Manages the beat-link Java bridge subprocess and the fallback UDP parser.
If the bridge JAR or JRE is unavailable, degrades gracefully.
"""

import asyncio
import logging
import platform
import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .adapter import BridgeAdapter
from .client import BridgeWebSocket, DEFAULT_BRIDGE_URL
from .fallback import FallbackParser
from .messages import BRIDGE_STATUS, BridgeMessage
from ..network.models import RouteFixResult
from ..network.route import check_route as network_check_route
from ..network.route import fix_route as network_fix_route

logger = logging.getLogger(__name__)

DEFAULT_JAR_PATH = Path("lib/beat-link-bridge.jar")
DEFAULT_PORT = 17400

# Minimum uptime (seconds) for a "running" bridge to be considered a stable start.
# If the bridge crashes faster than this, it counts as a consecutive failure even
# if it briefly reached "running" state — preventing _consecutive_failures from
# resetting and blocking fallback from ever triggering.
_MIN_STABLE_UPTIME_S = 30.0

# Polling interval (seconds) when waiting for hardware to reappear after the
# bridge has reached its crash threshold. Chosen to be infrequent enough to
# avoid OS focus-steal nuisance while still recovering reasonably quickly.
_HARDWARE_POLL_INTERVAL_S = 30.0

# JVM flags that suppress macOS AWT/Dock behaviour for headless subprocesses.
# -Djava.awt.headless=true  — prevents AWT from opening a display connection,
#   which is what causes the "beat link trigger" name to flash in the menu bar.
# -Dapple.awt.UIElement=true — (belt-and-suspenders) marks the process as a
#   background UI element so it never gets a Dock icon or Cmd-Tab entry even if
#   AWT does initialise.
# -Xdock:name=SCUE Bridge   — sets the app name shown in any AWT menu bar entry.
_JVM_FLAGS = [
    "-Djava.awt.headless=true",
    "-Dapple.awt.UIElement=true",
    "-Xdock:name=SCUE Bridge",
]


class BridgeManager:
    """Manages the beat-link bridge subprocess and adapter pipeline.

    States:
        stopped              — not running, no subprocess
        starting             — subprocess launching / WebSocket connecting
        running              — subprocess + WebSocket connected, receiving messages
        crashed              — subprocess died unexpectedly, will restart with backoff
        no_jre               — Java not found on system
        no_jar               — Bridge JAR not found at expected path
        fallback             — running UDP fallback parser (degraded mode)
        waiting_for_hardware — bridge reached crash threshold with no hardware present;
                               polling every 30 s for hardware to reappear
    """

    def __init__(
        self,
        jar_path: Path = DEFAULT_JAR_PATH,
        port: int = DEFAULT_PORT,
        network_interface: str | None = None,
        on_message: Callable[[BridgeMessage], None] | None = None,
        auto_fix_route: bool = True,
        health_check_interval: float = 10.0,
        restart_base_delay: float = 2.0,
        restart_max_delay: float = 30.0,
        max_crash_before_fallback: int = 3,
    ) -> None:
        self._jar_path = jar_path
        self._port = port
        self._network_interface = network_interface
        self._external_on_message = on_message
        self._auto_fix_route = auto_fix_route
        self._health_check_interval = health_check_interval
        self._restart_base_delay = restart_base_delay
        self._restart_max_delay = restart_max_delay
        self._max_crash_before_fallback = max_crash_before_fallback

        self._status = "stopped"
        self._process: subprocess.Popen | None = None
        self._ws_client: BridgeWebSocket | None = None
        self._adapter = BridgeAdapter()
        self._listen_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._wait_task: asyncio.Task | None = None  # hardware-wait polling task
        self._consecutive_failures = 0
        self._next_retry_at: float | None = None  # time.time() when next retry fires
        self._last_message_time: float = 0.0
        self._last_pioneer_message_time: float = 0.0
        self._last_stable_start_time: float = 0.0  # time.time() when last "running" began
        self._route_correct: bool | None = None
        self._route_warning: str | None = None
        self._fallback_parser: FallbackParser | None = None

        # Callback for state change notifications (used by WebSocket broadcaster)
        self.on_state_change: Callable[[], None] | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def _restart_count(self) -> int:
        """Backward-compat alias for _consecutive_failures."""
        return self._consecutive_failures

    @_restart_count.setter
    def _restart_count(self, value: int) -> None:
        self._consecutive_failures = value

    @property
    def pioneer_traffic_active(self) -> bool:
        """Whether Pioneer hardware traffic has been received recently (within 5s).

        Uses _last_pioneer_message_time which only updates on device/player/beat
        messages — not bridge heartbeats.
        """
        if self._last_pioneer_message_time <= 0:
            return False
        return (time.time() - self._last_pioneer_message_time) < 5.0

    @property
    def route_correct(self) -> bool | None:
        """Whether the macOS broadcast route points to the configured interface.

        Returns None if not checked yet or not applicable (non-macOS / no interface).
        """
        return self._route_correct

    @property
    def adapter(self) -> BridgeAdapter:
        return self._adapter

    @property
    def ws_client(self) -> BridgeWebSocket | None:
        """The WebSocket client, if connected. Used by the scanner for commands."""
        return self._ws_client if self._ws_client and self._ws_client.connected else None

    @property
    def port(self) -> int:
        return self._port

    @property
    def network_interface(self) -> str | None:
        return self._network_interface

    @network_interface.setter
    def network_interface(self, value: str | None) -> None:
        self._network_interface = value

    def _check_jre(self) -> bool:
        """Check if Java is available on the system."""
        return shutil.which("java") is not None

    def _check_jar(self) -> bool:
        """Check if the bridge JAR exists."""
        return self._jar_path.exists()

    def _notify_state_change(self) -> None:
        """Notify listeners of a state change (for WebSocket broadcast)."""
        if self.on_state_change is not None:
            try:
                self.on_state_change()
            except Exception as e:
                logger.debug("State change callback error: %s", e)

    async def start(self) -> None:
        """Start the bridge. Degrades gracefully if JAR/JRE unavailable."""
        if self._status == "running":
            return

        self._last_message_time = 0.0
        self._last_pioneer_message_time = 0.0
        self._adapter.clear()
        self._status = "starting"
        self._notify_state_change()

        if not self._check_jre():
            logger.warning(
                "Bridge unavailable (no_jre), starting UDP fallback parser (degraded mode)"
            )
            await self._start_fallback()
            return

        if not self._check_jar():
            logger.warning(
                "Bridge unavailable (no_jar), starting UDP fallback parser (degraded mode)"
            )
            await self._start_fallback()
            return

        try:
            await self._launch_subprocess()
            await self._connect_websocket()
            self._status = "running"
            # Only reset the consecutive failure counter if the bridge was stable
            # for at least _MIN_STABLE_UPTIME_S on its previous run.  A quick
            # start-then-crash cycle (hardware absent / no route) would otherwise
            # reset the counter before it accumulates enough failures to reach the
            # waiting_for_hardware threshold.
            uptime = time.time() - self._last_stable_start_time
            if self._last_stable_start_time == 0.0 or uptime >= _MIN_STABLE_UPTIME_S:
                self._consecutive_failures = 0
            self._last_stable_start_time = time.time()
            self._next_retry_at = None
            self._start_listen_loop()
            self._start_health_check()
            self._notify_state_change()
            logger.info("Bridge started on port %d", self._port)
        except Exception as e:
            logger.error("Bridge start failed: %s", e)
            self._status = "crashed"
            self._notify_state_change()
            await self._cleanup()
            await self._schedule_restart()

    async def stop(self) -> None:
        """Stop the bridge and clean up."""
        logger.info("Stopping bridge")
        self._stop_fallback()
        self._cancel_wait_task()
        await self._cleanup()
        self._status = "stopped"
        self._notify_state_change()

    async def restart(self) -> None:
        """Stop and restart the bridge (e.g. after config change)."""
        logger.info("Restarting bridge")
        self._stop_fallback()
        self._cancel_wait_task()
        await self.stop()
        self._consecutive_failures = 0
        self._last_stable_start_time = 0.0
        self._next_retry_at = None
        await self.start()

    def _check_and_fix_route(self) -> None:
        """Check the macOS broadcast route and attempt to fix it if auto_fix is enabled.

        Uses the network.route module for both checking and fixing. Falls back
        to logging a warning if the sudoers entry is not installed.
        """
        if platform.system() != "Darwin" or not self._network_interface:
            self._route_correct = None
            self._route_warning = None
            return

        try:
            result = network_check_route(self._network_interface)
            self._route_correct = result.correct

            if result.correct:
                logger.info(
                    "macOS broadcast route OK: 169.254.255.255 -> %s",
                    result.current_interface,
                )
                self._route_warning = None
                return

            # Route is wrong — try to fix if auto_fix is enabled
            logger.warning(
                "macOS routes 169.254.255.255 via %s, not %s",
                result.current_interface,
                self._network_interface,
            )

            if self._auto_fix_route:
                fix_result = network_fix_route(self._network_interface)
                if fix_result.success:
                    logger.info(
                        "Auto-fixed broadcast route: %s -> %s",
                        fix_result.previous_interface,
                        fix_result.new_interface,
                    )
                    self._route_correct = True
                    self._route_warning = None
                    return
                else:
                    logger.warning("Auto-fix failed: %s", fix_result.error)
                    self._route_warning = fix_result.error

            # Could not fix — log the manual fix command
            if not self._route_warning:
                self._route_warning = (
                    f"macOS routes 169.254.255.255 via {result.current_interface}, "
                    f"not {self._network_interface}. Fix with: "
                    f"sudo ./tools/fix-djlink-route.sh {self._network_interface}"
                )
        except Exception as e:
            logger.debug("Could not check macOS broadcast route: %s", e)
            self._route_correct = None
            self._route_warning = None

    async def fix_route(self) -> RouteFixResult:
        """Attempt to fix the broadcast route. Callable from the API."""
        if not self._network_interface:
            return RouteFixResult(
                success=False,
                error="No network interface configured",
                previous_interface=None,
                new_interface="",
            )
        result = network_fix_route(self._network_interface)
        if result.success:
            self._route_correct = True
            self._route_warning = None
            self._notify_state_change()
        elif result.error:
            # Wrap raw kernel errors with a user-friendly message.
            # "route: bad address: <iface>" is the macOS error when the
            # interface doesn't exist (adapter unplugged / hardware off).
            if "bad address" in result.error or "no such interface" in result.error.lower():
                friendly = (
                    f"Network interface '{self._network_interface}' is not available. "
                    f"Make sure your USB-Ethernet adapter is connected and the interface "
                    f"is up before fixing the route. "
                    f"(kernel error: {result.error})"
                )
                result = RouteFixResult(
                    success=False,
                    error=friendly,
                    previous_interface=result.previous_interface,
                    new_interface=result.new_interface,
                )
        return result

    def _check_macos_route(self) -> None:
        """On macOS, check if the 169.254.255.255 broadcast route matches the configured interface.

        Pro DJ Link uses link-local broadcasts. If macOS routes them to the wrong
        interface, beat-link will never discover devices. Logs a warning with the fix command.

        Deprecated: use _check_and_fix_route() instead, which also attempts auto-fix.
        """
        self._check_and_fix_route()

    async def _launch_subprocess(self) -> None:
        """Launch the bridge JAR as a subprocess."""
        self._check_and_fix_route()
        # JVM flags are inserted between "java" and "-jar" so they are processed
        # by the JVM itself, not forwarded to the application's main() args.
        # _JVM_FLAGS suppress AWT/Dock initialisation to prevent macOS window
        # focus-stealing and the "beat link trigger" menu-bar flash.
        cmd = [
            "java",
            *_JVM_FLAGS,
            "-jar", str(self._jar_path),
            "--port", str(self._port),
        ]
        if self._network_interface:
            cmd.extend(["--interface", self._network_interface])
        # Pass DLP database key if configured (for exportLibrary.db decryption)
        import os
        db_key = os.environ.get("SCUE_DLP_DATABASE_KEY", "")
        if db_key:
            cmd.extend(["--database-key", db_key])
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # Java bridge needs several seconds to start WebSocket server + join network
        for attempt in range(10):
            await asyncio.sleep(1.0)
            if self._process.poll() is not None:
                stderr_bytes = await asyncio.to_thread(self._process.stderr.read) if self._process.stderr else b""
                stderr = stderr_bytes.decode() if stderr_bytes else ""
                raise RuntimeError(f"Bridge subprocess exited (code {self._process.returncode}): {stderr[:500]}")
            # Check if WebSocket port is accepting connections
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("localhost", self._port), timeout=1.0
                )
                writer.close()
                await writer.wait_closed()
                logger.info("Bridge subprocess ready after %ds", attempt + 1)
                return
            except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
                continue
        raise RuntimeError(f"Bridge subprocess did not open WebSocket port {self._port} within 10s")

    async def _connect_websocket(self) -> None:
        """Connect to the bridge's WebSocket server."""
        url = f"ws://localhost:{self._port}"
        self._ws_client = BridgeWebSocket(url)
        await self._ws_client.connect()

    def _start_listen_loop(self) -> None:
        """Start the async loop that reads messages from the WebSocket."""
        self._listen_task = asyncio.create_task(self._listen_loop())

    def _start_health_check(self) -> None:
        """Start the periodic health check."""
        self._health_task = asyncio.create_task(self._health_check_loop())

    async def _listen_loop(self) -> None:
        """Read messages from WebSocket and feed to adapter."""
        if self._ws_client is None:
            return

        try:
            async for msg in self._ws_client.listen():
                now = time.time()
                self._last_message_time = now
                # Track Pioneer-originated messages separately from bridge
                # heartbeats so is_receiving reflects actual hardware traffic
                if msg.type != BRIDGE_STATUS:
                    self._last_pioneer_message_time = now
                self._adapter.handle_message(msg)
                if self._external_on_message is not None:
                    self._external_on_message(msg)
                self._notify_state_change()
        except Exception as e:
            logger.error("Listen loop error: %s", e)
            if self._status == "running":
                self._status = "crashed"
                self._notify_state_change()
                await self._schedule_restart()

    async def _health_check_loop(self) -> None:
        """Periodically check bridge health and restart if needed.

        Restart triggers:
          1. The Java subprocess has exited (process poll() is not None).
          2. The WebSocket connection has gone silent — no bridge heartbeats
             (bridge_status messages) for 2 × health_check_interval.

        NOT a restart trigger:
          - Pioneer hardware silence (_last_pioneer_message_time is stale).
            Hardware being off or disconnected is normal; the bridge is still
            healthy and should stay "running" waiting for hardware to return.
            Restarting on Pioneer silence caused the crash-restart cycle when
            hardware was absent.
        """
        while self._status in ("running", "starting"):
            await asyncio.sleep(self._health_check_interval)

            if self._status != "running":
                break

            # Check subprocess
            if self._process is not None and self._process.poll() is not None:
                logger.warning("Bridge subprocess died (exit code %d)", self._process.returncode)
                self._status = "crashed"
                self._notify_state_change()
                await self._schedule_restart()
                break

            # Check bridge WebSocket heartbeat freshness (all messages, including
            # bridge_status heartbeats). If the bridge process is alive but the
            # WebSocket has gone silent for 2× the health check interval, the
            # connection is dead and a restart is warranted.
            #
            # NOTE: Pioneer traffic silence (_last_pioneer_message_time) is NOT
            # checked here. Hardware being off is normal; do not restart for it.
            if self._last_message_time > 0:
                bridge_silence = time.time() - self._last_message_time
                if bridge_silence > self._health_check_interval * 2:
                    logger.warning(
                        "Bridge WebSocket silent for %.1fs (no heartbeats) — restarting",
                        bridge_silence,
                    )
                    self._status = "crashed"
                    self._notify_state_change()
                    await self._schedule_restart()
                    break

    async def _schedule_restart(self) -> None:
        """Restart with immediate first retry, then exponential backoff.

        First retry after a crash: immediate (0 delay).
        Subsequent consecutive failures: base_delay * 2^(failures-1), capped.
        After MAX_CRASH_BEFORE_FALLBACK consecutive failures: enter
        waiting_for_hardware state (slow polling every 30 s) rather than the
        UDP fallback parser. The fallback parser is only entered when JRE or
        JAR is absent — not when hardware is temporarily disconnected.
        """
        self._consecutive_failures += 1
        await self._cleanup()

        if self._consecutive_failures >= self._max_crash_before_fallback:
            logger.warning(
                "Bridge crashed %d times — entering waiting_for_hardware state "
                "(will retry every %.0fs)",
                self._consecutive_failures,
                _HARDWARE_POLL_INTERVAL_S,
            )
            await self._enter_waiting_for_hardware()
            return

        if self._consecutive_failures == 1:
            # First failure — retry immediately
            delay = 0.0
            logger.info("Restarting bridge immediately (attempt %d)", self._consecutive_failures)
        else:
            # Subsequent failures — exponential backoff
            delay = min(
                self._restart_base_delay * (2 ** (self._consecutive_failures - 2)),
                self._restart_max_delay,
            )
            logger.info(
                "Restarting bridge in %.1fs (attempt %d)",
                delay, self._consecutive_failures,
            )

        if delay > 0:
            self._next_retry_at = time.time() + delay
            self._notify_state_change()
            await asyncio.sleep(delay)
        self._next_retry_at = None
        await self.start()

    async def _enter_waiting_for_hardware(self) -> None:
        """Enter the waiting_for_hardware state and start a slow-poll task.

        In this state the bridge is NOT restarting aggressively.  It polls
        every _HARDWARE_POLL_INTERVAL_S seconds to check whether the network
        interface has reappeared, then attempts a full bridge restart.

        This state is separate from "fallback" (which runs the UDP parser).
        It is entered when the bridge has crashed max_crash_before_fallback
        times in a row, most likely due to absent or disconnected hardware.
        """
        self._status = "waiting_for_hardware"
        self._consecutive_failures = 0  # reset so next real crash starts fresh
        self._last_stable_start_time = 0.0
        self._next_retry_at = None
        self._notify_state_change()
        logger.info(
            "Bridge waiting for hardware — will poll every %.0fs",
            _HARDWARE_POLL_INTERVAL_S,
        )
        self._wait_task = asyncio.create_task(self._wait_for_hardware_loop())

    async def _wait_for_hardware_loop(self) -> None:
        """Slow-poll loop that attempts bridge restart when hardware reappears.

        Runs while status == "waiting_for_hardware". Attempts a restart every
        _HARDWARE_POLL_INTERVAL_S seconds. If start() succeeds the status
        transitions to "running" and the loop exits naturally. If start() fails
        again, _schedule_restart() will be called, which either backs off and
        retries within the normal cycle or re-enters waiting_for_hardware.
        """
        while self._status == "waiting_for_hardware":
            self._next_retry_at = time.time() + _HARDWARE_POLL_INTERVAL_S
            self._notify_state_change()
            try:
                await asyncio.sleep(_HARDWARE_POLL_INTERVAL_S)
            except asyncio.CancelledError:
                return
            if self._status != "waiting_for_hardware":
                return
            self._next_retry_at = None
            # Pre-check: if a specific interface is configured, verify it exists
            # before launching a subprocess. When interface is None (auto-detect
            # mode), skip the check — auto-detect doesn't target a single iface.
            if self._network_interface is not None:
                try:
                    socket.if_nametoindex(self._network_interface)
                except OSError:
                    logger.debug(
                        "Interface %s not available — skipping restart attempt",
                        self._network_interface,
                    )
                    continue
            logger.info(
                "Hardware poll — attempting bridge restart "
                "(consecutive_failures=%d)",
                self._consecutive_failures,
            )
            await self.start()

    def _cancel_wait_task(self) -> None:
        """Cancel the hardware-wait polling task if it is running."""
        if self._wait_task is not None and not self._wait_task.done():
            self._wait_task.cancel()
        self._wait_task = None

    async def _start_fallback(self) -> None:
        """Instantiate and start the fallback UDP parser (degraded mode).

        Only entered when JRE or JAR is absent — not when hardware is
        temporarily disconnected. For the hardware-absent case, use
        _enter_waiting_for_hardware() instead.
        """
        self._fallback_parser = FallbackParser(
            on_message=self._fallback_on_message,
            interface=self._network_interface,
        )
        await self._fallback_parser.start()
        self._status = "fallback"
        self._notify_state_change()
        logger.info("Fallback UDP parser active (degraded mode)")

    def _stop_fallback(self) -> None:
        """Stop the fallback parser if running."""
        if self._fallback_parser is not None:
            self._fallback_parser.stop()
            self._fallback_parser = None

    def _fallback_on_message(self, msg: BridgeMessage) -> None:
        """Route fallback parser messages through the same pipeline as bridge messages."""
        now = time.time()
        self._last_message_time = now
        if msg.type != BRIDGE_STATUS:
            self._last_pioneer_message_time = now
        self._adapter.handle_message(msg)
        if self._external_on_message is not None:
            self._external_on_message(msg)
        self._notify_state_change()

    async def _cleanup(self) -> None:
        """Clean up subprocess, WebSocket, and tasks."""
        if self._listen_task is not None and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._health_task is not None and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        if self._ws_client is not None:
            await self._ws_client.disconnect()
            self._ws_client = None

        if self._process is not None:
            try:
                self._process.terminate()
                try:
                    await asyncio.to_thread(self._process.wait, timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    await asyncio.to_thread(self._process.wait, timeout=2)
            except Exception:
                pass
            self._process = None

        # Clear accumulated adapter state so to_status_dict() returns empty
        # devices/players until fresh data arrives from the new bridge session.
        self._adapter.clear()

    def to_status_dict(self) -> dict:
        """Return a JSON-serializable status summary."""
        # Compute seconds until next retry (null when not retrying)
        next_retry_in_s: float | None = None
        if self._next_retry_at is not None:
            next_retry_in_s = max(0.0, self._next_retry_at - time.time())

        if self._status == "fallback":
            mode = "fallback"
        elif self._status == "waiting_for_hardware":
            mode = "waiting_for_hardware"
        else:
            mode = "bridge"

        return {
            "status": self._status,
            "mode": mode,
            "port": self._port,
            "network_interface": self._network_interface,
            "jar_path": str(self._jar_path),
            "jar_exists": self._check_jar(),
            "jre_available": self._check_jre(),
            "restart_count": self._consecutive_failures,
            "restart_attempt": self._consecutive_failures,
            "next_retry_in_s": next_retry_in_s,
            "route_correct": self._route_correct,
            "route_warning": self._route_warning,
            "devices": {
                ip: {
                    "device_name": d.device_name,
                    "device_number": d.device_number,
                    "device_type": d.device_type,
                    "uses_dlp": d.uses_dlp,
                }
                for ip, d in self._adapter.devices.items()
            },
            "players": {
                str(pn): {
                    "bpm": p.bpm,
                    "pitch": p.pitch,
                    "playback_state": p.playback_state,
                    "is_on_air": p.is_on_air,
                    "rekordbox_id": p.rekordbox_id,
                    "beat_within_bar": p.beat_within_bar,
                    "track_type": getattr(p, "track_type", ""),
                    "playback_position_ms": p.playback_position_ms,
                    "track_source_player": p.track_source_player,
                    "track_source_slot": p.track_source_slot,
                    "pioneer_waveform_version": p.pioneer_waveform_version,
                }
                for pn, p in self._adapter.players.items()
            },
        }
