"""Bridge manager — subprocess lifecycle, WebSocket connection, and health monitoring.

Manages the beat-link Java bridge subprocess and the fallback UDP parser.
If the bridge JAR or JRE is unavailable, degrades gracefully.
"""

import asyncio
import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .adapter import BridgeAdapter
from .client import BridgeWebSocket, DEFAULT_BRIDGE_URL
from .messages import BridgeMessage

logger = logging.getLogger(__name__)

DEFAULT_JAR_PATH = Path("lib/beat-link-bridge.jar")
DEFAULT_PORT = 17400
HEALTH_CHECK_INTERVAL = 10.0  # seconds between health checks
MAX_BACKOFF = 30.0


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
        on_message: Callable[[BridgeMessage], None] | None = None,
    ) -> None:
        self._jar_path = jar_path
        self._port = port
        self._external_on_message = on_message

        self._status = "stopped"
        self._process: subprocess.Popen | None = None
        self._ws_client: BridgeWebSocket | None = None
        self._adapter = BridgeAdapter()
        self._listen_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._restart_count = 0
        self._last_message_time: float = 0.0

    @property
    def status(self) -> str:
        return self._status

    @property
    def adapter(self) -> BridgeAdapter:
        return self._adapter

    @property
    def port(self) -> int:
        return self._port

    def _check_jre(self) -> bool:
        """Check if Java is available on the system."""
        return shutil.which("java") is not None

    def _check_jar(self) -> bool:
        """Check if the bridge JAR exists."""
        return self._jar_path.exists()

    async def start(self) -> None:
        """Start the bridge. Degrades gracefully if JAR/JRE unavailable."""
        if self._status == "running":
            return

        self._status = "starting"

        if not self._check_jre():
            logger.warning("Java not found — bridge unavailable")
            self._status = "no_jre"
            return

        if not self._check_jar():
            logger.warning("Bridge JAR not found at %s — bridge unavailable", self._jar_path)
            self._status = "no_jar"
            return

        try:
            await self._launch_subprocess()
            await self._connect_websocket()
            self._status = "running"
            self._restart_count = 0
            self._start_listen_loop()
            self._start_health_check()
            logger.info("Bridge started on port %d", self._port)
        except Exception as e:
            logger.error("Bridge start failed: %s", e)
            self._status = "crashed"
            await self._cleanup()

    async def stop(self) -> None:
        """Stop the bridge and clean up."""
        logger.info("Stopping bridge")
        await self._cleanup()
        self._status = "stopped"

    async def _launch_subprocess(self) -> None:
        """Launch the bridge JAR as a subprocess."""
        cmd = [
            "java", "-jar", str(self._jar_path),
            "--port", str(self._port),
        ]
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Give the subprocess a moment to start its WebSocket server
        await asyncio.sleep(1.0)

        if self._process.poll() is not None:
            stderr = self._process.stderr.read().decode() if self._process.stderr else ""
            raise RuntimeError(f"Bridge subprocess exited immediately: {stderr}")

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
                self._last_message_time = time.time()
                self._adapter.handle_message(msg)
                if self._external_on_message is not None:
                    self._external_on_message(msg)
        except Exception as e:
            logger.error("Listen loop error: %s", e)
            if self._status == "running":
                self._status = "crashed"

    async def _health_check_loop(self) -> None:
        """Periodically check bridge health and restart if needed."""
        while self._status in ("running", "starting"):
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

            if self._status != "running":
                break

            # Check subprocess
            if self._process is not None and self._process.poll() is not None:
                logger.warning("Bridge subprocess died (exit code %d)", self._process.returncode)
                self._status = "crashed"
                await self._schedule_restart()
                break

            # Check message freshness
            if self._last_message_time > 0:
                silence = time.time() - self._last_message_time
                if silence > HEALTH_CHECK_INTERVAL * 2:
                    logger.warning("Bridge silent for %.1fs — restarting", silence)
                    self._status = "crashed"
                    await self._schedule_restart()
                    break

    async def _schedule_restart(self) -> None:
        """Restart with exponential backoff."""
        self._restart_count += 1
        backoff = min(2 ** self._restart_count, MAX_BACKOFF)
        logger.info("Restarting bridge in %.1fs (attempt %d)", backoff, self._restart_count)
        await self._cleanup()
        await asyncio.sleep(backoff)
        await self.start()

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
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)
            except Exception:
                pass
            self._process = None

    def to_status_dict(self) -> dict:
        """Return a JSON-serializable status summary."""
        return {
            "status": self._status,
            "port": self._port,
            "jar_path": str(self._jar_path),
            "jar_exists": self._check_jar(),
            "jre_available": self._check_jre(),
            "restart_count": self._restart_count,
            "devices": {
                ip: {
                    "device_name": d.device_name,
                    "device_number": d.device_number,
                    "device_type": d.device_type,
                }
                for ip, d in self._adapter.devices.items()
            },
            "players": {
                str(pn): {
                    "title": p.title,
                    "artist": p.artist,
                    "bpm": p.bpm,
                    "playback_state": p.playback_state,
                    "is_on_air": p.is_on_air,
                }
                for pn, p in self._adapter.players.items()
            },
        }
