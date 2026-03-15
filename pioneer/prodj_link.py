"""Direct Pro DJ Link UDP client.

Listens on the Pioneer Pro DJ Link ports without requiring beat-link-trigger.
Auto-discovers the correct network interface by binding to every local IPv4
address, so it works regardless of which adapter the Pioneer device is on.

Protocol reference: https://djl-analysis.deepsymmetry.org/
Beat-link source:   https://github.com/Deep-Symmetry/beat-link

Port layout
-----------
50001  Device keep-alive / announcement broadcasts  (we LISTEN)
50000  CDJ status broadcasts                        (we LISTEN)
"""

import asyncio
import socket
import struct
import sys
import time
from collections import deque
from dataclasses import asdict
from typing import Callable

from .state import DeckState, STALE_TIMEOUT
from .network import get_local_interfaces, pioneer_interfaces

# ── Protocol constants ──────────────────────────────────────────────────────

ANNOUNCE_PORT = 50001
STATUS_PORT   = 50000

# First 6 bytes of every Pro DJ Link packet ("QsptN\x1e")
MAGIC = b"\x51\x73\x70\x74\x4e\x1e"

# Packet type byte (offset 0x0a)
PKT_KEEPALIVE = 0x06
PKT_STATUS    = 0x0a

# ── Keep-alive packet offsets ────────────────────────────────────────────────
KA_NAME   = 0x0c   # 20 bytes, null-padded device name
KA_PNUM   = 0x21   # 1 byte  player number (1–4)
KA_IP     = 0x2a   # 4 bytes big-endian IP address
KA_MINLEN = 0x2e   # minimum valid keepalive length

# ── CDJ status packet offsets ────────────────────────────────────────────────
# Confirmed from beat-link CdjStatus.java and djl-analysis docs.
ST_PNUM     = 0x21   # 1 byte  player number
ST_ACTIVITY = 0x28   # 1 byte  0=empty, 2=CD, 3=SD, 4=USB, 5=collection
ST_RB_ID    = 0x2c   # 4 bytes rekordbox track ID  (big-endian)
ST_FLAGS    = 0x89   # 1 byte  play-state flags
ST_BPM      = 0x92   # 4 bytes track BPM * 100     (big-endian)
ST_PITCH    = 0x96   # 3 bytes pitch value          (big-endian, 0x100000 = 0%)
ST_BEAT_NUM = 0xa0   # 4 bytes beat count from start (big-endian)
ST_BEAT_BAR = 0xa6   # 1 byte  beat within bar (1–4)
ST_MINLEN   = 0xa7   # packet must be at least this many bytes

# Flag bits at ST_FLAGS
FLAG_PLAYING = 0x40
FLAG_MASTER  = 0x20
FLAG_SYNC    = 0x10
FLAG_ON_AIR  = 0x08


class ProDJLinkClient:
    """Passive listener for Pro DJ Link broadcasts.

    Binds one UDP socket per local IP on each Pro DJ Link port so that
    Pioneer broadcasts on any interface (including link-local en16) are
    reliably received on macOS with multiple active adapters.
    """

    def __init__(self):
        self.decks: dict[int, DeckState] = {}   # keyed by player number
        self.devices: dict[str, dict] = {}       # keyed by source IP

        self._callbacks: list[Callable] = []
        self._transports: list = []

        # Diagnostics
        self.packet_count = 0
        self.last_packet_time: float = 0.0
        self.recent_packets: deque = deque(maxlen=100)
        self._bound_addresses: list[tuple] = []

    # ── Public API (matches PioneerOSCReceiver) ──────────────────────────────

    def on_update(self, callback: Callable):
        """Register callback(channel: int, state: dict) for every deck update."""
        self._callbacks.append(callback)

    @property
    def is_receiving(self) -> bool:
        if self.last_packet_time == 0:
            return False
        return (time.time() - self.last_packet_time) < STALE_TIMEOUT

    @property
    def active_channels(self) -> list[int]:
        now = time.time()
        return [
            ch for ch, d in self.decks.items()
            if d.last_update > 0 and (now - d.last_update) < STALE_TIMEOUT
        ]

    def get_state(self) -> dict:
        """Return {player_num: deck_state_dict} for all known players."""
        return {ch: d.to_dict() for ch, d in self.decks.items()}

    def get_debug_info(self) -> dict:
        return {
            "is_receiving": self.is_receiving,
            "packet_count": self.packet_count,
            "last_packet_time": self.last_packet_time,
            "seconds_since_last": (
                round(time.time() - self.last_packet_time, 1)
                if self.last_packet_time > 0 else None
            ),
            "active_channels": self.active_channels,
            "bound_addresses": [f"{ip}:{port}" for ip, port in self._bound_addresses],
            "discovered_devices": self.devices,
            "recent_packets": list(self.recent_packets),
        }

    async def start(self):
        """Bind sockets on all suitable interfaces and start listening."""
        all_ifaces = get_local_interfaces()
        ifaces = pioneer_interfaces(all_ifaces)

        print(f"[ProDJLink] All interfaces found: {[i['ip'] for i in all_ifaces]}")
        print(f"[ProDJLink] Using interfaces:      {[i['ip'] for i in ifaces]}")

        loop = asyncio.get_event_loop()

        for iface in ifaces:
            for port in (ANNOUNCE_PORT, STATUS_PORT):
                try:
                    sock = _make_udp_socket(iface["ip"], port, iface["interface"])
                    transport, _ = await loop.create_datagram_endpoint(
                        lambda: _UDPProtocol(self._on_packet),
                        sock=sock,
                    )
                    self._transports.append(transport)
                    self._bound_addresses.append((iface["ip"], port))
                    print(f"[ProDJLink] Listening  {iface['interface']:8s}  {iface['ip']}:{port}")
                except OSError as e:
                    print(f"[ProDJLink] Bind failed {iface['ip']}:{port}  {e}")

        if not self._transports:
            print("[ProDJLink] WARNING: no sockets bound — Pioneer data will not arrive")

    def stop(self):
        for t in self._transports:
            t.close()
        self._transports.clear()

    # ── Packet handling ───────────────────────────────────────────────────────

    def _on_packet(self, data: bytes, addr: tuple):
        src_ip = addr[0]
        src_port = addr[1]

        self.packet_count += 1
        self.last_packet_time = time.time()

        # Log every packet for the debug endpoint
        self.recent_packets.append({
            "t": round(self.last_packet_time, 3),
            "src": f"{src_ip}:{src_port}",
            "len": len(data),
            "hex5": data[:5].hex(),
        })

        if len(data) < 11 or data[:6] != MAGIC:
            return   # Not a Pro DJ Link packet

        pkt_type = data[0x0a]

        if pkt_type == PKT_KEEPALIVE and len(data) >= KA_MINLEN:
            self._parse_keepalive(data, src_ip)
        elif pkt_type == PKT_STATUS and len(data) >= ST_MINLEN:
            self._parse_status(data, src_ip)
        else:
            print(f"[ProDJLink] Unknown pkt type=0x{pkt_type:02x} len={len(data)} from {src_ip}")

    def _parse_keepalive(self, data: bytes, src_ip: str):
        """Extract device name, player number and IP from announcement."""
        name_raw = data[KA_NAME: KA_NAME + 20]
        name = name_raw.split(b"\x00")[0].decode("utf-8", errors="replace")
        player_num = data[KA_PNUM]
        dev_ip = ".".join(str(b) for b in data[KA_IP: KA_IP + 4])

        if src_ip not in self.devices:
            print(f"[ProDJLink] Discovered  \"{name}\"  player={player_num}  ip={dev_ip}")

        self.devices[src_ip] = {
            "name": name,
            "player_num": player_num,
            "ip": dev_ip,
            "last_seen": time.time(),
        }

        # Ensure we have a DeckState for this player
        if player_num not in self.decks:
            self.decks[player_num] = DeckState(channel=player_num)
        self.decks[player_num].device_name = name
        self.decks[player_num].player_number = player_num

    def _parse_status(self, data: bytes, src_ip: str):
        """Parse a CDJ/XDJ status broadcast and update deck state."""
        player_num = data[ST_PNUM]

        if player_num < 1 or player_num > 6:
            return  # Ignore unexpected player numbers

        if player_num not in self.decks:
            self.decks[player_num] = DeckState(channel=player_num)

        deck = self.decks[player_num]

        # ── Flags ──────────────────────────────────────────────────
        flags = data[ST_FLAGS]
        deck.is_playing = bool(flags & FLAG_PLAYING)
        deck.is_master  = bool(flags & FLAG_MASTER)
        deck.is_synced  = bool(flags & FLAG_SYNC)
        deck.is_on_air  = bool(flags & FLAG_ON_AIR)

        # ── BPM ────────────────────────────────────────────────────
        # 4-byte big-endian unsigned int, stored as BPM * 100
        bpm_raw = struct.unpack_from(">I", data, ST_BPM)[0]
        original_bpm = bpm_raw / 100.0

        # ── Pitch ──────────────────────────────────────────────────
        # 3-byte big-endian unsigned int.
        # 0x100000 = neutral (0% pitch), range ~0x000000–0x200000
        p = data[ST_PITCH: ST_PITCH + 3]
        pitch_raw = (p[0] << 16) | (p[1] << 8) | p[2]
        # Guard against zeroed pitch field on some firmware
        pitch_multiplier = pitch_raw / 0x100000 if pitch_raw > 0 else 1.0
        effective_bpm  = original_bpm * pitch_multiplier
        pitch_percent  = (pitch_multiplier - 1.0) * 100.0

        # ── Beat position ──────────────────────────────────────────
        beat_num = struct.unpack_from(">I", data, ST_BEAT_NUM)[0]
        beat_bar = data[ST_BEAT_BAR]
        if not (1 <= beat_bar <= 4):
            beat_bar = 0  # Not yet cued to a beat grid position

        # ── Playback position (estimated from beat count + BPM) ────
        if effective_bpm > 0 and beat_num > 0:
            ms_per_beat = 60_000.0 / effective_bpm
            position_ms = (beat_num - 1) * ms_per_beat
        else:
            position_ms = 0.0

        # ── Rekordbox track ID ─────────────────────────────────────
        rb_id = struct.unpack_from(">I", data, ST_RB_ID)[0]

        # ── Commit ─────────────────────────────────────────────────
        deck.original_bpm       = round(original_bpm, 2)
        deck.effective_bpm      = round(effective_bpm, 2)
        deck.pitch_percent      = round(pitch_percent, 3)
        deck.beat_number        = int(beat_num)
        deck.beat_within_bar    = int(beat_bar)
        deck.playback_position_ms = round(position_ms, 1)
        deck.rekordbox_id       = int(rb_id)
        deck.last_update        = time.time()

        self._notify(player_num)

    def _notify(self, channel: int):
        state = self.decks[channel].to_dict()
        for cb in self._callbacks:
            try:
                cb(channel, state)
            except Exception:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_udp_socket(ip: str, port: int, iface_name: str = "") -> socket.socket:
    """Create a non-blocking UDP socket for receiving Pro DJ Link broadcasts.

    On macOS, binding to a unicast IP (169.254.x.x) silently prevents reception
    of broadcast packets from that interface.  The fix is to bind to INADDR_ANY
    (0.0.0.0) and use IP_BOUND_IF to lock the socket to a specific interface.
    Linux uses SO_BINDTODEVICE for the same effect.  Both fallback to a plain
    unicast bind if the privileged option fails.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)

    if iface_name:
        if sys.platform == "darwin":
            # IP_BOUND_IF = 25 (net/in.h) — binds INADDR_ANY socket to one iface
            try:
                IP_BOUND_IF = 25
                if_idx = socket.if_nametoindex(iface_name)
                sock.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, if_idx)
                sock.bind(("", port))
                print(f"[ProDJLink] macOS IP_BOUND_IF: {iface_name} (idx {if_idx}) port {port}")
                return sock
            except OSError as e:
                print(f"[ProDJLink] IP_BOUND_IF failed ({e}), falling back to unicast bind")
        elif sys.platform.startswith("linux"):
            # SO_BINDTODEVICE requires CAP_NET_RAW on Linux
            try:
                sock.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_BINDTODEVICE,
                    (iface_name + "\x00").encode(),
                )
                sock.bind(("", port))
                print(f"[ProDJLink] Linux SO_BINDTODEVICE: {iface_name} port {port}")
                return sock
            except PermissionError as e:
                print(f"[ProDJLink] SO_BINDTODEVICE failed ({e}), falling back to unicast bind")

    # Fallback: bind to the unicast IP (works on Windows; limited on macOS/Linux)
    sock.bind((ip, port))
    return sock


class _UDPProtocol(asyncio.DatagramProtocol):
    """Minimal asyncio protocol that forwards datagrams to a callback."""

    def __init__(self, callback: Callable):
        self._cb = callback

    def datagram_received(self, data: bytes, addr: tuple):
        self._cb(data, addr)

    def error_received(self, exc: Exception):
        print(f"[ProDJLink] UDP error: {exc}")

    def connection_lost(self, exc):
        if exc:
            print(f"[ProDJLink] Connection lost: {exc}")
