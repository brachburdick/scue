"""OSC receiver for beat-link-trigger data.

Listens for OSC messages from beat-link-trigger and maintains
a real-time state dict for each deck/channel. Notifies registered
callbacks on every update so the WebSocket layer can push to clients.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Callable

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer

OSC_PORT = 9000  # beat-link-trigger sends here

# How long (seconds) before we consider Pioneer "disconnected"
STALE_TIMEOUT = 5.0


@dataclass
class DeckState:
    """Real-time state for a single Pioneer deck/channel."""

    channel: int = 0
    is_playing: bool = False
    is_on_air: bool = False
    is_synced: bool = False
    is_master: bool = False
    is_looping: bool = False

    # BPM
    original_bpm: float = 0.0
    effective_bpm: float = 0.0
    pitch_percent: float = 0.0

    # Position
    beat_number: int = 0
    beat_within_bar: int = 0
    playback_position_ms: float = 0.0

    # Track metadata
    track_title: str = ""
    track_artist: str = ""
    track_key: str = ""
    track_genre: str = ""
    track_length_sec: float = 0.0
    rekordbox_id: int = 0

    # Timing
    last_update: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class PioneerOSCReceiver:
    """Manages OSC server and deck state from beat-link-trigger."""

    def __init__(self, osc_port: int = OSC_PORT):
        self.osc_port = osc_port
        self.decks: dict[int, DeckState] = {
            1: DeckState(channel=1),
            2: DeckState(channel=2),
        }
        self._callbacks: list[Callable] = []
        self._server = None

        # Debug / diagnostics
        self.last_osc_received: float = 0.0  # timestamp of ANY osc message
        self.osc_message_count: int = 0
        self.recent_messages: deque = deque(maxlen=50)  # last 50 raw OSC msgs

    def on_update(self, callback: Callable):
        """Register a callback that fires on every deck state change.
        Callback receives (channel: int, deck_state: dict).
        """
        self._callbacks.append(callback)

    @property
    def is_receiving(self) -> bool:
        """True if we've received OSC data within the last STALE_TIMEOUT seconds."""
        if self.last_osc_received == 0:
            return False
        return (time.time() - self.last_osc_received) < STALE_TIMEOUT

    @property
    def active_channels(self) -> list[int]:
        """List of channels that have received data recently."""
        now = time.time()
        return [
            ch for ch, deck in self.decks.items()
            if deck.last_update > 0 and (now - deck.last_update) < STALE_TIMEOUT
        ]

    def get_state(self) -> dict:
        """Return current state of all decks."""
        return {ch: deck.to_dict() for ch, deck in self.decks.items()}

    def get_debug_info(self) -> dict:
        """Return diagnostic information."""
        return {
            "osc_port": self.osc_port,
            "is_receiving": self.is_receiving,
            "last_osc_received": self.last_osc_received,
            "seconds_since_last": round(time.time() - self.last_osc_received, 1) if self.last_osc_received > 0 else None,
            "osc_message_count": self.osc_message_count,
            "active_channels": self.active_channels,
            "recent_messages": list(self.recent_messages),
        }

    async def start(self):
        """Start the async OSC UDP server."""
        dispatcher = Dispatcher()

        # Catch-all handler — logs everything for debugging
        dispatcher.set_default_handler(self._handle_any)

        # Status messages: /deck/<channel>/<field>
        dispatcher.map("/deck/*/playing", self._handle_bool, "is_playing")
        dispatcher.map("/deck/*/on_air", self._handle_bool, "is_on_air")
        dispatcher.map("/deck/*/synced", self._handle_bool, "is_synced")
        dispatcher.map("/deck/*/master", self._handle_bool, "is_master")
        dispatcher.map("/deck/*/looping", self._handle_bool, "is_looping")

        dispatcher.map("/deck/*/original_bpm", self._handle_float, "original_bpm")
        dispatcher.map("/deck/*/effective_bpm", self._handle_float, "effective_bpm")
        dispatcher.map("/deck/*/pitch_percent", self._handle_float, "pitch_percent")

        dispatcher.map("/deck/*/beat_number", self._handle_int, "beat_number")
        dispatcher.map("/deck/*/beat_within_bar", self._handle_int, "beat_within_bar")
        dispatcher.map("/deck/*/position_ms", self._handle_float, "playback_position_ms")

        dispatcher.map("/deck/*/track_title", self._handle_str, "track_title")
        dispatcher.map("/deck/*/track_artist", self._handle_str, "track_artist")
        dispatcher.map("/deck/*/track_key", self._handle_str, "track_key")
        dispatcher.map("/deck/*/track_genre", self._handle_str, "track_genre")
        dispatcher.map("/deck/*/track_length", self._handle_float, "track_length_sec")
        dispatcher.map("/deck/*/rekordbox_id", self._handle_int, "rekordbox_id")

        # Beat events
        dispatcher.map("/deck/*/beat", self._handle_beat)

        self._server = AsyncIOOSCUDPServer(
            ("0.0.0.0", self.osc_port), dispatcher, asyncio.get_event_loop()
        )
        transport, protocol = await self._server.create_serve_endpoint()
        return transport

    # --- Handlers ---

    def _log_message(self, address: str, args):
        """Record every OSC message for debugging."""
        self.last_osc_received = time.time()
        self.osc_message_count += 1
        self.recent_messages.append({
            "t": round(self.last_osc_received, 2),
            "addr": address,
            "args": [str(a) for a in args] if args else [],
        })

    def _handle_any(self, address: str, *args):
        """Catch-all: log everything, including messages we don't have specific handlers for."""
        self._log_message(address, args)
        print(f"[OSC] {address}  {args}")

    def _parse_channel(self, address: str) -> int | None:
        """Extract channel number from OSC address like /deck/1/playing."""
        parts = address.split("/")
        if len(parts) >= 3:
            try:
                ch = int(parts[2])
                if ch in self.decks:
                    return ch
            except ValueError:
                pass
        return None

    def _field_and_value(self, args: tuple, value_default):
        """pythonosc passes (handler_args, *osc_message_args). handler_args is a list from map()."""
        if not args:
            return None, value_default
        field_arg = args[0]
        field_name = field_arg[0] if isinstance(field_arg, list) else field_arg
        value = args[1] if len(args) > 1 else value_default
        if isinstance(value, list):
            value = value[0] if value else value_default
        return field_name, value

    def _handle_float(self, address: str, *args):
        self._log_message(address, args)
        field_name, value = self._field_and_value(args, 0.0)
        if field_name is None:
            return
        ch = self._parse_channel(address)
        if ch is None:
            return
        setattr(self.decks[ch], field_name, float(value))
        self.decks[ch].last_update = time.time()
        self._notify(ch)

    def _handle_int(self, address: str, *args):
        self._log_message(address, args)
        field_name, value = self._field_and_value(args, 0)
        if field_name is None:
            return
        ch = self._parse_channel(address)
        if ch is None:
            return
        setattr(self.decks[ch], field_name, int(value))
        self.decks[ch].last_update = time.time()
        self._notify(ch)

    def _handle_bool(self, address: str, *args):
        self._log_message(address, args)
        field_name, value = self._field_and_value(args, 0)
        if field_name is None:
            return
        ch = self._parse_channel(address)
        if ch is None:
            return
        setattr(self.decks[ch], field_name, bool(value))
        self.decks[ch].last_update = time.time()
        self._notify(ch)

    def _handle_str(self, address: str, *args):
        self._log_message(address, args)
        field_name, value = self._field_and_value(args, "")
        if field_name is None:
            return
        ch = self._parse_channel(address)
        if ch is None:
            return
        setattr(self.decks[ch], field_name, str(value))
        self.decks[ch].last_update = time.time()
        self._notify(ch)

    def _handle_beat(self, address: str, *args):
        self._log_message(address, args)
        ch = self._parse_channel(address)
        if ch is None:
            return
        if len(args) > 0:
            self.decks[ch].beat_within_bar = int(args[0])
        self.decks[ch].last_update = time.time()
        self._notify(ch)

    def _notify(self, channel: int):
        """Fire all registered callbacks."""
        state = self.decks[channel].to_dict()
        for cb in self._callbacks:
            try:
                cb(channel, state)
            except Exception:
                pass
