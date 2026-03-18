"""Bridge manager — subprocess lifecycle, WebSocket connection, and health monitoring.

Manages the beat-link Java bridge subprocess and the fallback UDP parser.
If the bridge JAR or JRE is unavailable, degrades gracefully.
"""

import asyncio
import logging
import platform
import shutil
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


class BridgeManager:
    """Manages the beat-link bridge subprocess and adapter pipeline.

    States:
        stopped   — not running, no subprocess
        starting  — subprocess launching / WebSocket connecting
        running   — subprocess + WebSocket connected, receiving messages
        crashed   — subprocess died unexpectedly, will restart with backoff
        no_jre    — Java not found on system
        no_jar    — Bridge JAR not found at expected path
        fallback  — running UDP fallback parser (degraded mode)
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
        self._consecutive_failures = 0
        self._next_retry_at: float | None = None  # time.time() when next retry fires
        self._last_message_time: float = 0.0
        self._last_pioneer_message_time: float = 0.0
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
    def adapter(self) -> BridgeAdapter:
        return self._adapter

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
            self._consecutive_failures = 0
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

    async def stop(self) -> None:
        """Stop the bridge and clean up."""
        logger.info("Stopping bridge")
        self._stop_fallback()
        await self._cleanup()
        self._status = "stopped"
        self._notify_state_change()

    async def restart(self) -> None:
        """Stop and restart the bridge (e.g. after config change)."""
        logger.info("Restarting bridge")
        self._stop_fallback()
        await self.stop()
        self._consecutive_failures = 0
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
        cmd = [
            "java", "-jar", str(self._jar_path),
            "--port", str(self._port),
        ]
        if self._network_interface:
            cmd.extend(["--interface", self._network_interface])
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
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
        """Periodically check bridge health and restart if needed."""
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

            # Check message freshness
            if self._last_message_time > 0:
                silence = time.time() - self._last_message_time
                if silence > self._health_check_interval * 2:
                    logger.warning("Bridge silent for %.1fs — restarting", silence)
                    self._status = "crashed"
                    self._notify_state_change()
                    await self._schedule_restart()
                    break

    async def _schedule_restart(self) -> None:
        """Restart with immediate first retry, then exponential backoff.

        First retry after a crash: immediate (0 delay).
        Subsequent consecutive failures: base_delay * 2^(failures-1), capped.
        After MAX_CRASH_BEFORE_FALLBACK consecutive failures: switch to fallback.
        """
        self._consecutive_failures += 1
        await self._cleanup()

        if self._consecutive_failures >= self._max_crash_before_fallback:
            logger.warning(
                "Bridge crashed %d times, switching to fallback mode",
                self._consecutive_failures,
            )
            await self._start_fallback()
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

    async def _start_fallback(self) -> None:
        """Instantiate and start the fallback UDP parser (degraded mode)."""
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

    def to_status_dict(self) -> dict:
        """Return a JSON-serializable status summary."""
        # Compute seconds until next retry (null when not retrying)
        next_retry_in_s: float | None = None
        if self._next_retry_at is not None:
            next_retry_in_s = max(0.0, self._next_retry_at - time.time())

        return {
            "status": self._status,
            "mode": "fallback" if self._status == "fallback" else "bridge",
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
                }
                for pn, p in self._adapter.players.items()
            },
        }
