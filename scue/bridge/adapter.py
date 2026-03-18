"""Bridge adapter — normalizes BridgeMessage objects into bridge-level output types.

The adapter is stateful: it accumulates per-player metadata, beat grid,
cue points, etc. across multiple messages. It emits typed callbacks that
Layer 1 can consume without importing bridge internals.

Layer 1 does NOT import from bridge directly. This adapter defines its own
output types; Layer 1 will consume them when Milestone 2 is built.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .messages import (
    BEAT,
    BEAT_GRID,
    BRIDGE_STATUS,
    CUE_POINTS,
    DEVICE_FOUND,
    DEVICE_LOST,
    PHRASE_ANALYSIS,
    PLAYER_STATUS,
    TRACK_METADATA,
    WAVEFORM_DETAIL,
    BridgeMessage,
    parse_typed_payload,
    BeatGridPayload,
    BeatPayload,
    CuePointsPayload,
    DevicePayload,
    PhraseAnalysisPayload,
    PlayerStatusPayload,
    TrackMetadataPayload,
    WaveformDetailPayload,
)

logger = logging.getLogger(__name__)


# ── Adapter output types ─────────────────────────────────────────────────
# These are the bridge layer's output. Layer 1 consumes them.

@dataclass
class DeviceInfo:
    """A discovered Pioneer device on the network."""
    device_name: str
    device_number: int
    device_type: str  # "cdj" | "djm" | "rekordbox"
    ip_address: str
    last_seen: float = 0.0
    uses_dlp: bool = False  # True for Device Library Plus hardware (XDJ-AZ, Opus Quad, etc.)


@dataclass
class PlayerState:
    """Accumulated state for a single player/deck."""
    player_number: int

    # Playback
    bpm: float = 0.0
    pitch: float = 0.0
    beat_within_bar: int = 0
    beat_number: int = 0
    playback_state: str = "paused"
    is_on_air: bool = False

    # Track metadata (from track_metadata messages)
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    key: str = ""
    duration: float = 0.0
    rekordbox_id: int = 0

    # Beat grid (from beat_grid messages)
    beat_grid: list[dict] = field(default_factory=list)

    # Phrase analysis (from phrase_analysis messages)
    phrases: list[dict] = field(default_factory=list)

    # Cue points (from cue_points messages)
    cue_points: list[dict] = field(default_factory=list)
    memory_points: list[dict] = field(default_factory=list)
    hot_cues: list[dict] = field(default_factory=list)

    # Waveform
    has_waveform: bool = False

    # Timing
    last_update: float = 0.0
    last_beat_time: float = 0.0


# ── Callback types ────────────────────────────────────────────────────────

OnDeviceChange = Callable[[DeviceInfo, str], None]  # (device, "found"|"lost")
OnPlayerUpdate = Callable[[PlayerState], None]
OnBeat = Callable[[int, int, float], None]  # (player_number, beat_within_bar, bpm)
OnTrackLoaded = Callable[[int, str, str], None]  # (player_number, title, artist)


# ── BridgeAdapter ─────────────────────────────────────────────────────────

class BridgeAdapter:
    """Stateful adapter that normalizes BridgeMessage streams into typed callbacks.

    Usage:
        adapter = BridgeAdapter()
        adapter.on_device_change = my_device_handler
        adapter.on_player_update = my_player_handler
        adapter.on_beat = my_beat_handler

        # Feed messages from bridge or fallback
        for msg in message_stream:
            adapter.handle_message(msg)
    """

    def __init__(self) -> None:
        self._devices: dict[str, DeviceInfo] = {}  # keyed by ip_address
        self._players: dict[int, PlayerState] = {}  # keyed by player_number

        # Callbacks (set by consumer)
        self.on_device_change: OnDeviceChange | None = None
        self.on_player_update: OnPlayerUpdate | None = None
        self.on_beat: OnBeat | None = None
        self.on_track_loaded: OnTrackLoaded | None = None

        # Bridge status
        self.bridge_connected: bool = False
        self.bridge_version: str = ""

    @property
    def devices(self) -> dict[str, DeviceInfo]:
        return dict(self._devices)

    @property
    def players(self) -> dict[int, PlayerState]:
        return dict(self._players)

    def get_player(self, player_number: int) -> PlayerState | None:
        return self._players.get(player_number)

    def handle_message(self, msg: BridgeMessage) -> None:
        """Dispatch a BridgeMessage to the appropriate handler."""
        handler = self._handlers.get(msg.type)
        if handler is not None:
            handler(self, msg)
        else:
            logger.debug("Unhandled message type: %s", msg.type)

    # ── Per-type handlers ────────────────────────────────────────────────

    def _handle_bridge_status(self, msg: BridgeMessage) -> None:
        payload = parse_typed_payload(msg)
        if payload is not None and hasattr(payload, "connected"):
            self.bridge_connected = payload.connected
            self.bridge_version = payload.version
            logger.info("Bridge status: connected=%s version=%s", payload.connected, payload.version)

    def _handle_device_found(self, msg: BridgeMessage) -> None:
        payload = parse_typed_payload(msg)
        if not isinstance(payload, DevicePayload):
            return

        device = DeviceInfo(
            device_name=payload.device_name,
            device_number=payload.device_number,
            device_type=payload.device_type,
            ip_address=payload.ip_address,
            last_seen=msg.timestamp,
            uses_dlp=payload.uses_dlp,
        )
        self._devices[payload.ip_address] = device
        logger.info(
            "Device found: %s (#%d) at %s (dlp=%s)",
            payload.device_name, payload.device_number, payload.ip_address, payload.uses_dlp,
        )

        if self.on_device_change is not None:
            self.on_device_change(device, "found")

    def _handle_device_lost(self, msg: BridgeMessage) -> None:
        payload = parse_typed_payload(msg)
        if not isinstance(payload, DevicePayload):
            return

        device = self._devices.pop(payload.ip_address, None)
        if device is None:
            device = DeviceInfo(
                device_name=payload.device_name,
                device_number=payload.device_number,
                device_type=payload.device_type,
                ip_address=payload.ip_address,
            )
        logger.info("Device lost: %s (#%d)", payload.device_name, payload.device_number)

        if self.on_device_change is not None:
            self.on_device_change(device, "lost")

    def _handle_player_status(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, PlayerStatusPayload):
            return

        # Infer device presence from player_status if no device_found was received.
        # This happens when the Python side connects to the bridge WebSocket after
        # the device was already discovered (device_found fired before we connected).
        self._ensure_device_from_player(msg.player_number, msg.timestamp)

        player = self._ensure_player(msg.player_number)
        player.bpm = payload.bpm
        player.pitch = payload.pitch
        player.beat_within_bar = payload.beat_within_bar
        player.beat_number = payload.beat_number
        player.playback_state = payload.playback_state
        player.is_on_air = payload.is_on_air
        player.last_update = msg.timestamp

        # Detect track changes via rekordbox_id in player_status.
        # Per ADR-012: The bridge no longer sends track_metadata messages.
        # Metadata is resolved by the Python side (via rbox for DLP hardware).
        # We fire on_track_loaded when the rekordbox_id changes so Layer 1 can
        # look up metadata from the USB database.
        new_rb_id = payload.rekordbox_id
        if new_rb_id != 0 and new_rb_id != player.rekordbox_id:
            old_rb_id = player.rekordbox_id
            player.rekordbox_id = new_rb_id
            if old_rb_id != 0:
                logger.info("Track changed on player %d: rbid %d → %d", msg.player_number, old_rb_id, new_rb_id)
            else:
                logger.info("Track detected on player %d: rbid=%d", msg.player_number, new_rb_id)

            # Fire track loaded callback with rekordbox_id so Layer 1 can resolve metadata
            if self.on_track_loaded is not None:
                self.on_track_loaded(msg.player_number, str(new_rb_id), "")
        elif new_rb_id == 0 and player.rekordbox_id != 0:
            # Track unloaded
            player.rekordbox_id = 0
            logger.info("Track unloaded on player %d", msg.player_number)

        if self.on_player_update is not None:
            self.on_player_update(player)

    def _handle_track_metadata(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, TrackMetadataPayload):
            return

        player = self._ensure_player(msg.player_number)
        old_title = player.title

        player.title = payload.title
        player.artist = payload.artist
        player.album = payload.album
        player.genre = payload.genre
        player.key = payload.key
        player.duration = payload.duration
        player.rekordbox_id = payload.rekordbox_id
        player.last_update = msg.timestamp

        logger.info(
            "Track loaded on player %d: %s — %s",
            msg.player_number, payload.title, payload.artist,
        )

        if self.on_track_loaded is not None and payload.title != old_title:
            self.on_track_loaded(msg.player_number, payload.title, payload.artist)

    def _handle_beat_grid(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, BeatGridPayload):
            return

        player = self._ensure_player(msg.player_number)
        player.beat_grid = [
            {"beat_number": b.beat_number, "time_ms": b.time_ms, "bpm": b.bpm}
            for b in payload.beats
        ]
        player.last_update = msg.timestamp

    def _handle_waveform_detail(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        player = self._ensure_player(msg.player_number)
        player.has_waveform = True
        player.last_update = msg.timestamp

    def _handle_phrase_analysis(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, PhraseAnalysisPayload):
            return

        player = self._ensure_player(msg.player_number)
        player.phrases = [
            {
                "start_beat": p.start_beat,
                "end_beat": p.end_beat,
                "kind": p.kind,
                "mood": p.mood,
            }
            for p in payload.phrases
        ]
        player.last_update = msg.timestamp

    def _handle_cue_points(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, CuePointsPayload):
            return

        player = self._ensure_player(msg.player_number)
        player.cue_points = [
            {"time_ms": c.time_ms, "name": c.name, "color": c.color}
            for c in payload.cue_points
        ]
        player.memory_points = [
            {"time_ms": c.time_ms, "name": c.name, "color": c.color}
            for c in payload.memory_points
        ]
        player.hot_cues = [
            {"slot": h.slot, "time_ms": h.time_ms, "name": h.name, "color": h.color}
            for h in payload.hot_cues
        ]
        player.last_update = msg.timestamp

    def _handle_beat(self, msg: BridgeMessage) -> None:
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, BeatPayload):
            return

        player = self._ensure_player(msg.player_number)
        player.beat_within_bar = payload.beat_within_bar
        player.bpm = payload.bpm
        player.last_beat_time = msg.timestamp

        if self.on_beat is not None:
            self.on_beat(msg.player_number, payload.beat_within_bar, payload.bpm)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _ensure_player(self, player_number: int) -> PlayerState:
        if player_number not in self._players:
            self._players[player_number] = PlayerState(player_number=player_number)
        return self._players[player_number]

    def _ensure_device_from_player(self, player_number: int, timestamp: float) -> None:
        """Synthesize a device entry if we see player data but never got device_found.

        When the Python side connects to the bridge WebSocket after device discovery
        already happened, device_found events are missed. We infer device presence
        from player_status messages to keep the devices dict and downstream status
        (frontend device list, pioneer_status.is_receiving) accurate.
        """
        # Check if any existing device matches this player number
        for dev in self._devices.values():
            if dev.device_number == player_number:
                dev.last_seen = timestamp
                return

        # No device found for this player — synthesize one
        # Use a placeholder IP keyed by player number since we don't know the real IP
        placeholder_ip = f"inferred-player-{player_number}"
        device = DeviceInfo(
            device_name=f"Player {player_number}",
            device_number=player_number,
            device_type="cdj",
            ip_address=placeholder_ip,
            last_seen=timestamp,
            uses_dlp=True,  # Assume DLP since that's our primary hardware
        )
        self._devices[placeholder_ip] = device
        logger.info(
            "Device inferred from player_status: player %d (no device_found received)",
            player_number,
        )

        if self.on_device_change is not None:
            self.on_device_change(device, "found")

    # Handler dispatch table
    _handlers: dict[str, Callable[["BridgeAdapter", BridgeMessage], None]] = {
        BRIDGE_STATUS: _handle_bridge_status,
        DEVICE_FOUND: _handle_device_found,
        DEVICE_LOST: _handle_device_lost,
        PLAYER_STATUS: _handle_player_status,
        TRACK_METADATA: _handle_track_metadata,
        BEAT_GRID: _handle_beat_grid,
        WAVEFORM_DETAIL: _handle_waveform_detail,
        PHRASE_ANALYSIS: _handle_phrase_analysis,
        CUE_POINTS: _handle_cue_points,
        BEAT: _handle_beat,
    }
