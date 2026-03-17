"""BridgeMessage dataclass and typed payload models for Layer 0.

All messages from the beat-link Java bridge (and the UDP fallback parser)
are represented as BridgeMessage objects. The payload is deserialized into
a typed dataclass based on the message type.

See docs/ARCHITECTURE.md § Layer 0 and docs/CONTRACTS.md for schemas.
"""

import json
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Message type constants ────────────────────────────────────────────────

DEVICE_FOUND = "device_found"
DEVICE_LOST = "device_lost"
BRIDGE_STATUS = "bridge_status"
PLAYER_STATUS = "player_status"
TRACK_METADATA = "track_metadata"
BEAT_GRID = "beat_grid"
WAVEFORM_DETAIL = "waveform_detail"
PHRASE_ANALYSIS = "phrase_analysis"
CUE_POINTS = "cue_points"
BEAT = "beat"

ALL_TYPES = frozenset({
    DEVICE_FOUND, DEVICE_LOST, BRIDGE_STATUS,
    PLAYER_STATUS, TRACK_METADATA, BEAT_GRID,
    WAVEFORM_DETAIL, PHRASE_ANALYSIS, CUE_POINTS, BEAT,
})


# ── Core message ──────────────────────────────────────────────────────────

@dataclass
class BridgeMessage:
    """Universal message from the beat-link bridge or UDP fallback.

    Matches the contract in docs/CONTRACTS.md.
    """
    type: str
    timestamp: float
    player_number: int | None
    payload: dict = field(default_factory=dict)


# ── Typed payloads ────────────────────────────────────────────────────────

@dataclass
class DevicePayload:
    """Payload for device_found / device_lost messages."""
    device_name: str
    device_number: int
    device_type: str  # "cdj" | "djm" | "rekordbox"
    ip_address: str
    uses_dlp: bool = False  # True for Device Library Plus hardware (XDJ-AZ, Opus Quad, etc.)


@dataclass
class BridgeStatusPayload:
    """Payload for bridge_status messages."""
    connected: bool
    devices_online: int
    version: str = ""


@dataclass
class PlayerStatusPayload:
    """Payload for player_status messages."""
    bpm: float
    pitch: float  # pitch adjustment percentage
    beat_within_bar: int  # 1–4
    beat_number: int  # absolute beat count
    playback_state: str  # "playing" | "paused" | "cued" | "searching"
    is_on_air: bool
    track_source_player: int = 0
    track_source_slot: str = ""  # "sd" | "usb" | "cd" | "collection"
    track_type: str = ""
    rekordbox_id: int = 0


@dataclass
class TrackMetadataPayload:
    """Payload for track_metadata messages."""
    title: str
    artist: str
    album: str = ""
    genre: str = ""
    key: str = ""
    bpm: float = 0.0
    duration: float = 0.0
    color: str | None = None
    rating: int = 0
    comment: str = ""
    rekordbox_id: int = 0


@dataclass
class BeatGridEntry:
    beat_number: int
    time_ms: float
    bpm: float


@dataclass
class BeatGridPayload:
    """Payload for beat_grid messages."""
    beats: list[BeatGridEntry] = field(default_factory=list)


@dataclass
class WaveformDetailPayload:
    """Payload for waveform_detail messages."""
    data: str  # base64-encoded
    total_beats: int = 0


@dataclass
class PhraseEntry:
    start_beat: int
    end_beat: int
    kind: str
    mood: int = 0


@dataclass
class PhraseAnalysisPayload:
    """Payload for phrase_analysis messages."""
    phrases: list[PhraseEntry] = field(default_factory=list)


@dataclass
class CuePoint:
    time_ms: float
    name: str = ""
    color: str = ""


@dataclass
class HotCue:
    slot: int
    time_ms: float
    name: str = ""
    color: str = ""


@dataclass
class CuePointsPayload:
    """Payload for cue_points messages."""
    cue_points: list[CuePoint] = field(default_factory=list)
    memory_points: list[CuePoint] = field(default_factory=list)
    hot_cues: list[HotCue] = field(default_factory=list)


@dataclass
class BeatPayload:
    """Payload for beat (real-time) messages."""
    beat_within_bar: int
    bpm: float
    pitch: float = 0.0


# ── Type → payload class mapping ─────────────────────────────────────────

PAYLOAD_TYPES: dict[str, type] = {
    DEVICE_FOUND: DevicePayload,
    DEVICE_LOST: DevicePayload,
    BRIDGE_STATUS: BridgeStatusPayload,
    PLAYER_STATUS: PlayerStatusPayload,
    TRACK_METADATA: TrackMetadataPayload,
    BEAT_GRID: BeatGridPayload,
    WAVEFORM_DETAIL: WaveformDetailPayload,
    PHRASE_ANALYSIS: PhraseAnalysisPayload,
    CUE_POINTS: CuePointsPayload,
    BEAT: BeatPayload,
}


# ── Parsing ───────────────────────────────────────────────────────────────

def _build_payload(msg_type: str, raw: dict) -> object | None:
    """Attempt to deserialize a raw payload dict into a typed dataclass."""
    cls = PAYLOAD_TYPES.get(msg_type)
    if cls is None:
        return None

    try:
        # Handle nested lists of dataclasses
        if cls is BeatGridPayload:
            beats = [BeatGridEntry(**b) for b in raw.get("beats", [])]
            return BeatGridPayload(beats=beats)
        if cls is PhraseAnalysisPayload:
            phrases = [PhraseEntry(**p) for p in raw.get("phrases", [])]
            return PhraseAnalysisPayload(phrases=phrases)
        if cls is CuePointsPayload:
            cue_points = [CuePoint(**c) for c in raw.get("cue_points", [])]
            memory_points = [CuePoint(**c) for c in raw.get("memory_points", [])]
            hot_cues = [HotCue(**h) for h in raw.get("hot_cues", [])]
            return CuePointsPayload(
                cue_points=cue_points,
                memory_points=memory_points,
                hot_cues=hot_cues,
            )
        return cls(**raw)
    except (TypeError, KeyError) as e:
        logger.warning("Failed to parse %s payload: %s", msg_type, e)
        return None


def parse_message(raw_json: str) -> BridgeMessage:
    """Parse a JSON string from the bridge WebSocket into a BridgeMessage.

    Raises ValueError if the JSON is malformed or missing required fields.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    msg_type = data.get("type")
    if not msg_type or not isinstance(msg_type, str):
        raise ValueError("Missing or invalid 'type' field")

    timestamp = data.get("timestamp")
    if timestamp is None:
        timestamp = time.time()
    timestamp = float(timestamp)

    player_number = data.get("player_number")
    if player_number is not None:
        player_number = int(player_number)

    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    return BridgeMessage(
        type=msg_type,
        timestamp=timestamp,
        player_number=player_number,
        payload=payload,
    )


def parse_typed_payload(msg: BridgeMessage) -> object | None:
    """Parse a BridgeMessage's raw payload dict into a typed dataclass.

    Returns None if the message type is unknown or parsing fails.
    """
    return _build_payload(msg.type, msg.payload)


def message_to_json(msg: BridgeMessage) -> str:
    """Serialize a BridgeMessage to JSON string (for mock bridge / testing)."""
    return json.dumps({
        "type": msg.type,
        "timestamp": msg.timestamp,
        "player_number": msg.player_number,
        "payload": msg.payload,
    })
