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
    TRACK_WAVEFORM,
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
    TrackWaveformPayload,
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

    # Track source (from player_status messages — which player/slot loaded the track)
    track_source_player: int = 0
    track_source_slot: str = ""  # "sd" | "usb" | "cd" | "collection"

    # Playback position (from player_status messages)
    playback_position_ms: float | None = None

    # Beat grid (from beat_grid messages)
    beat_grid: list[dict] = field(default_factory=list)

    # Phrase analysis (from phrase_analysis messages)
    phrases: list[dict] = field(default_factory=list)

    # Cue points (from cue_points messages)
    cue_points: list[dict] = field(default_factory=list)
    memory_points: list[dict] = field(default_factory=list)
    hot_cues: list[dict] = field(default_factory=list)

    # Waveform (raw from beat-link)
    has_waveform: bool = False
    waveform_data: str = ""  # base64-encoded waveform bytes

    # Pioneer waveform (decoded RGB, ready for frontend)
    pioneer_waveform: dict | None = None  # RGBWaveform shape: {low, mid, high, sample_rate, duration}
    pioneer_waveform_version: int = 0

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

    def clear(self) -> None:
        """Reset accumulated device and player state.

        Called on bridge crash/restart to prevent stale data from persisting
        across sessions.  Does NOT reset callbacks (wired once at startup)
        or bridge_connected / bridge_version (managed by bridge_status messages).
        """
        self._devices.clear()
        self._players.clear()

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
        player.track_source_player = payload.track_source_player
        player.track_source_slot = payload.track_source_slot
        player.playback_position_ms = self._compute_position_ms(player, payload.beat_number)
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
        old_rb_id = player.rekordbox_id

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

        # Fire on_track_loaded if title OR rekordbox_id changed
        title_changed = payload.title != old_title
        rb_id_changed = payload.rekordbox_id != 0 and payload.rekordbox_id != old_rb_id
        if self.on_track_loaded is not None and (title_changed or rb_id_changed):
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

        payload = parse_typed_payload(msg)
        if not isinstance(payload, WaveformDetailPayload):
            return

        player = self._ensure_player(msg.player_number)
        player.has_waveform = True
        player.waveform_data = payload.data
        player.last_update = msg.timestamp

    def _handle_track_waveform(self, msg: BridgeMessage) -> None:
        """Decode Pioneer waveform into RGBWaveform-shaped dict."""
        if msg.player_number is None:
            return

        payload = parse_typed_payload(msg)
        if not isinstance(payload, TrackWaveformPayload):
            return

        import base64
        raw = base64.b64decode(payload.data)
        n_samples = payload.frame_count
        if len(raw) != n_samples * 3:
            logger.warning(
                "track_waveform size mismatch: expected %d bytes, got %d",
                n_samples * 3, len(raw),
            )
            return

        low = [raw[i * 3] / 31.0 for i in range(n_samples)]
        mid = [raw[i * 3 + 1] / 31.0 for i in range(n_samples)]
        high = [raw[i * 3 + 2] / 31.0 for i in range(n_samples)]
        duration = payload.total_time_ms / 1000.0
        sample_rate = n_samples / duration if duration > 0 else 150.0

        player = self._ensure_player(msg.player_number)
        player.pioneer_waveform = {
            "low": low,
            "mid": mid,
            "high": high,
            "sample_rate": sample_rate,
            "duration": duration,
        }
        player.pioneer_waveform_version += 1
        player.last_update = msg.timestamp
        logger.info(
            "Pioneer waveform decoded for player %d: %d samples, %.1fs, color=%s",
            msg.player_number, n_samples, duration, payload.is_color,
        )

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

    @staticmethod
    def _compute_position_ms(player: PlayerState, beat_number: int) -> float | None:
        """Derive playback position in ms from beat_number + beat_grid.

        beat-link 8.0.0 does not expose playback position directly.
        We interpolate from the ANLZ beat grid that was delivered via
        beat_grid messages. Returns None if no beat grid is available
        or beat_number is 0 (no track / unknown position).
        """
        if beat_number <= 0 or not player.beat_grid:
            return None

        grid = player.beat_grid
        # Find the grid entry matching or just before beat_number
        # Grid entries: [{"beat_number": N, "time_ms": T, "bpm": B}, ...]
        if beat_number <= grid[0].get("beat_number", 1):
            return grid[0].get("time_ms", 0.0)

        for i in range(len(grid) - 1, -1, -1):
            entry = grid[i]
            entry_beat = entry.get("beat_number", 0)
            if entry_beat <= beat_number:
                # Interpolate from this grid entry
                time_ms = entry.get("time_ms", 0.0)
                bpm = entry.get("bpm", 0.0)
                if bpm > 0:
                    ms_per_beat = 60_000.0 / bpm
                    time_ms += (beat_number - entry_beat) * ms_per_beat
                return time_ms

        return None

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
        TRACK_WAVEFORM: _handle_track_waveform,
        PHRASE_ANALYSIS: _handle_phrase_analysis,
        CUE_POINTS: _handle_cue_points,
        BEAT: _handle_beat,
    }
