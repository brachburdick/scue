"""Direct UDP Pro DJ Link parser — fallback when the Java bridge is unavailable.

Ported from _reference/poc/scue/layer1/prodjlink.py. Outputs BridgeMessage
objects (same interface as the full bridge) so the manager can swap transparently.

Provides degraded mode: BPM, beat position, play state, and device discovery.
Does NOT provide track metadata, waveforms, phrase analysis, or cue points.

See LEARNINGS.md: "macOS broadcast UDP reception — IP_BOUND_IF required"
"""

import asyncio
import logging
import socket
import struct
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from .messages import (
    BEAT,
    DEVICE_FOUND,
    PLAYER_STATUS,
    BridgeMessage,
)

logger = logging.getLogger(__name__)

# ── Protocol constants ────────────────────────────────────────────────────

ANNOUNCE_PORT = 50001
STATUS_PORT = 50000

# First 6 bytes of every Pro DJ Link packet ("QsptN\x1e")
MAGIC = b"\x51\x73\x70\x74\x4e\x1e"

# Packet type byte (offset 0x0a)
PKT_KEEPALIVE = 0x06
PKT_STATUS = 0x0a

# Keep-alive packet offsets
KA_NAME = 0x0C  # 20 bytes, null-padded device name
KA_PNUM = 0x21  # 1 byte  player number (1–4)
KA_IP = 0x2A    # 4 bytes big-endian IP address
KA_MINLEN = 0x2E

# CDJ status packet offsets
ST_PNUM = 0x21     # 1 byte  player number
ST_RB_ID = 0x2C    # 4 bytes rekordbox track ID
ST_FLAGS = 0x89    # 1 byte  play-state flags
ST_BPM = 0x92      # 4 bytes track BPM * 100
ST_PITCH = 0x96    # 3 bytes pitch value (0x100000 = 0%)
ST_BEAT_NUM = 0xA0  # 4 bytes beat count from start
ST_BEAT_BAR = 0xA6  # 1 byte  beat within bar (1–4)
ST_MINLEN = 0xA7

# Flag bits
FLAG_PLAYING = 0x40
FLAG_MASTER = 0x20
FLAG_SYNC = 0x10
FLAG_ON_AIR = 0x08


# ── Network interface discovery ──────────────────────────────────────────

try:
    import netifaces
    _HAS_NETIFACES = True
except ImportError:
    _HAS_NETIFACES = False


def get_local_interfaces() -> list[dict]:
    """Return all local IPv4 interfaces (excluding loopback)."""
    results = []

    if _HAS_NETIFACES:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for addr in addrs.get(netifaces.AF_INET, []):
                ip = addr.get("addr", "")
                if not ip or ip.startswith("127."):
                    continue
                results.append({
                    "interface": iface,
                    "ip": ip,
                    "netmask": addr.get("netmask", ""),
                    "broadcast": addr.get("broadcast", ""),
                })
    else:
        try:
            hostname = socket.gethostname()
            for res in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = res[4][0]
                if not ip.startswith("127."):
                    results.append({
                        "interface": "unknown",
                        "ip": ip,
                        "netmask": "",
                        "broadcast": "",
                    })
        except Exception:
            pass

    return results


def pioneer_interfaces(all_ifaces: list[dict]) -> list[dict]:
    """Return interfaces most likely to carry Pro DJ Link traffic.

    Prioritises link-local (169.254.x.x) since Pioneer gear defaults to APIPA.
    """
    link_local = [i for i in all_ifaces if i["ip"].startswith("169.254.")]
    return link_local if link_local else all_ifaces


# ── UDP socket creation ──────────────────────────────────────────────────

def make_udp_socket(ip: str, port: int, iface_name: str = "") -> socket.socket:
    """Create a non-blocking UDP socket for Pro DJ Link broadcasts.

    Uses IP_BOUND_IF on macOS, SO_BINDTODEVICE on Linux.
    See LEARNINGS.md for the macOS broadcast reception quirk.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)

    if iface_name:
        if sys.platform == "darwin":
            try:
                IP_BOUND_IF = 25
                if_idx = socket.if_nametoindex(iface_name)
                sock.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, if_idx)
                sock.bind(("", port))
                logger.info(
                    "macOS IP_BOUND_IF: %s (idx %d) port %d",
                    iface_name, if_idx, port,
                )
                return sock
            except OSError as e:
                logger.warning("IP_BOUND_IF failed (%s), falling back to unicast bind", e)
        elif sys.platform.startswith("linux"):
            try:
                sock.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_BINDTODEVICE,
                    (iface_name + "\x00").encode(),
                )
                sock.bind(("", port))
                logger.info("Linux SO_BINDTODEVICE: %s port %d", iface_name, port)
                return sock
            except PermissionError as e:
                logger.warning("SO_BINDTODEVICE failed (%s), falling back", e)

    sock.bind((ip, port))
    return sock


# ── UDP protocol handler ─────────────────────────────────────────────────

class _UDPProtocol(asyncio.DatagramProtocol):
    """Minimal asyncio protocol that forwards datagrams to a callback."""

    def __init__(self, callback: Callable[[bytes, tuple], None]):
        self._cb = callback

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._cb(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.warning("UDP connection lost: %s", exc)


# ── FallbackParser ────────────────────────────────────────────────────────

@dataclass
class _DeviceInfo:
    name: str
    player_number: int
    ip: str
    last_seen: float


class FallbackParser:
    """Passive listener for Pro DJ Link UDP broadcasts.

    Emits BridgeMessage objects via the on_message callback,
    matching the same interface as the full Java bridge.
    Degraded mode: only device_found, player_status, and beat messages.
    """

    def __init__(self, on_message: Callable[[BridgeMessage], None] | None = None):
        self._on_message = on_message
        self._devices: dict[str, _DeviceInfo] = {}
        self._last_beat: dict[int, int] = {}  # player → last beat_within_bar
        self._transports: list[asyncio.BaseTransport] = []
        self._running = False

        # Diagnostics
        self.packet_count = 0
        self.last_packet_time: float = 0.0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def devices(self) -> dict[str, _DeviceInfo]:
        return dict(self._devices)

    async def start(self) -> None:
        """Bind sockets on all suitable interfaces and start listening."""
        all_ifaces = get_local_interfaces()
        ifaces = pioneer_interfaces(all_ifaces)

        logger.info(
            "Fallback UDP parser starting — interfaces: %s",
            [i["ip"] for i in ifaces],
        )

        loop = asyncio.get_event_loop()

        for iface in ifaces:
            for port in (ANNOUNCE_PORT, STATUS_PORT):
                try:
                    sock = make_udp_socket(iface["ip"], port, iface["interface"])
                    transport, _ = await loop.create_datagram_endpoint(
                        lambda: _UDPProtocol(self._on_packet),
                        sock=sock,
                    )
                    self._transports.append(transport)
                    logger.info(
                        "Listening %s %s:%d",
                        iface["interface"], iface["ip"], port,
                    )
                except OSError as e:
                    logger.warning("Bind failed %s:%d — %s", iface["ip"], port, e)

        if not self._transports:
            logger.warning("No sockets bound — Pioneer data will not arrive")

        self._running = True

    def stop(self) -> None:
        """Close all UDP sockets."""
        for t in self._transports:
            t.close()
        self._transports.clear()
        self._running = False
        logger.info("Fallback UDP parser stopped")

    def _emit(self, msg: BridgeMessage) -> None:
        if self._on_message is not None:
            self._on_message(msg)

    def _on_packet(self, data: bytes, addr: tuple) -> None:
        self.packet_count += 1
        self.last_packet_time = time.time()

        if len(data) < 11 or data[:6] != MAGIC:
            return

        pkt_type = data[0x0A]

        if pkt_type == PKT_KEEPALIVE and len(data) >= KA_MINLEN:
            self._parse_keepalive(data, addr[0])
        elif pkt_type == PKT_STATUS and len(data) >= ST_MINLEN:
            self._parse_status(data)

    def _parse_keepalive(self, data: bytes, src_ip: str) -> None:
        name_raw = data[KA_NAME: KA_NAME + 20]
        name = name_raw.split(b"\x00")[0].decode("utf-8", errors="replace")
        player_num = data[KA_PNUM]
        dev_ip = ".".join(str(b) for b in data[KA_IP: KA_IP + 4])

        is_new = src_ip not in self._devices
        self._devices[src_ip] = _DeviceInfo(
            name=name,
            player_number=player_num,
            ip=dev_ip,
            last_seen=time.time(),
        )

        if is_new:
            logger.info("Discovered %r player=%d ip=%s", name, player_num, dev_ip)
            # Determine device type from player number
            # CDJs are typically 1-4, DJMs are 33+
            device_type = "djm" if player_num >= 33 else "cdj"
            self._emit(BridgeMessage(
                type=DEVICE_FOUND,
                timestamp=time.time(),
                player_number=player_num if device_type == "cdj" else None,
                payload={
                    "device_name": name,
                    "device_number": player_num,
                    "device_type": device_type,
                    "ip_address": dev_ip,
                },
            ))

    def _parse_status(self, data: bytes) -> None:
        player_num = data[ST_PNUM]
        if player_num < 1 or player_num > 6:
            return

        now = time.time()

        # Flags
        flags = data[ST_FLAGS]
        is_playing = bool(flags & FLAG_PLAYING)
        is_on_air = bool(flags & FLAG_ON_AIR)

        # BPM
        bpm_raw = struct.unpack_from(">I", data, ST_BPM)[0]
        original_bpm = bpm_raw / 100.0

        # Pitch
        p = data[ST_PITCH: ST_PITCH + 3]
        pitch_raw = (p[0] << 16) | (p[1] << 8) | p[2]
        pitch_multiplier = pitch_raw / 0x100000 if pitch_raw > 0 else 1.0
        effective_bpm = original_bpm * pitch_multiplier
        pitch_percent = (pitch_multiplier - 1.0) * 100.0

        # Beat position
        beat_num = struct.unpack_from(">I", data, ST_BEAT_NUM)[0]
        beat_bar = data[ST_BEAT_BAR]
        if not (1 <= beat_bar <= 4):
            beat_bar = 0

        # Determine playback state string
        if is_playing:
            playback_state = "playing"
        else:
            playback_state = "paused"

        # Emit player_status
        self._emit(BridgeMessage(
            type=PLAYER_STATUS,
            timestamp=now,
            player_number=player_num,
            payload={
                "bpm": round(effective_bpm, 2),
                "pitch": round(pitch_percent, 3),
                "beat_within_bar": int(beat_bar),
                "beat_number": int(beat_num),
                "playback_state": playback_state,
                "is_on_air": is_on_air,
                "track_source_player": player_num,
                "track_source_slot": "",
                "track_type": "",
            },
        ))

        # Emit beat event on beat change
        prev_beat = self._last_beat.get(player_num, 0)
        if beat_bar != prev_beat and beat_bar >= 1 and is_playing:
            self._last_beat[player_num] = beat_bar
            self._emit(BridgeMessage(
                type=BEAT,
                timestamp=now,
                player_number=player_num,
                payload={
                    "beat_within_bar": int(beat_bar),
                    "bpm": round(effective_bpm, 2),
                    "pitch": round(pitch_percent, 3),
                },
            ))
