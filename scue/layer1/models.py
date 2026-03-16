"""Layer 1 data models.

All dataclasses used within Layer 1 and exposed to Layer 2 via the TrackCursor contract.
See docs/CONTRACTS.md for the exact shapes that Layer 2 may depend on.
"""

import time
from dataclasses import dataclass, asdict, field
from typing import Any

# ── Pioneer / live playback ────────────────────────────────────────────────

# Seconds with no packets before a deck/device is considered stale
STALE_TIMEOUT = 5.0


@dataclass
class DeckState:
    """Real-time state for a single Pioneer deck/player (from Pro DJ Link)."""

    channel: int = 0

    # Playback flags
    is_playing: bool = False
    is_on_air: bool = False
    is_synced: bool = False
    is_master: bool = False
    is_looping: bool = False

    # BPM
    original_bpm: float = 0.0       # Track's native BPM
    effective_bpm: float = 0.0      # BPM after pitch adjustment
    pitch_percent: float = 0.0      # Pitch fader offset in %

    # Position
    beat_number: int = 0            # Absolute beat from track start
    beat_within_bar: int = 0        # 1–4
    playback_position_ms: float = 0.0

    # Identity (from keepalive / status packets)
    device_name: str = ""
    player_number: int = 0          # 1–4 as reported by the hardware

    # Track metadata (populated via DBSERVER protocol — future work)
    track_title: str = ""
    track_artist: str = ""
    track_key: str = ""
    track_genre: str = ""
    track_length_sec: float = 0.0
    rekordbox_id: int = 0

    # Timing / diagnostics
    last_update: float = 0.0

    def is_stale(self) -> bool:
        if self.last_update == 0:
            return True
        return (time.time() - self.last_update) > STALE_TIMEOUT

    def to_dict(self) -> dict:
        return asdict(self)


# ── Offline track analysis ─────────────────────────────────────────────────

@dataclass
class Section:
    """A labeled section of a track (Tier 1 output)."""
    label: str                          # intro, verse, build, drop, breakdown, fakeout, outro
    start: float                        # seconds, at original BPM
    end: float                          # seconds, at original BPM
    confidence: float = 0.5            # 0.0–1.0
    bar_count: int = 0                 # actual measured bar count
    expected_bar_count: int = 0        # nearest valid multiple (8, 16, 32 …)
    irregular_phrase: bool = False     # True if bar_count != expected_bar_count
    fakeout: bool = False
    original_label: str = ""          # allin1-mlx label before EDM relabeling
    source: str = "analysis"          # "analysis" | "pioneer_enriched"


@dataclass
class MusicalEvent:
    """A single Tier 2 event (kick, riser, arp note, etc.)."""
    type: str                           # kick, snare, riser, faller, stab, arp_note, etc.
    timestamp: float                    # seconds from track start, at original BPM
    duration: float | None = None
    intensity: float = 0.5            # 0.0–1.0
    payload: dict = field(default_factory=dict)


@dataclass
class TrackFeatures:
    """Tier 3 track-level features (coarse descriptors)."""
    energy_curve: list[float] = field(default_factory=list)   # 0.0–1.0, downsampled
    mood: str = "neutral"              # dark, euphoric, melancholic, aggressive, neutral
    danceability: float = 0.5
    key: str = ""
    key_source: str = "analysis"      # "analysis" | "pioneer_enriched"


@dataclass
class TrackAnalysis:
    """Full offline analysis of a track. Stored in SQLite, keyed by fingerprint."""
    fingerprint: str                    # SHA256 of audio file bytes
    audio_path: str
    bpm: float
    beats: list[float]                  # beat timestamps, seconds
    downbeats: list[float]             # downbeat timestamps, seconds
    beatgrid_source: str = "analysis"  # "analysis" | "pioneer_enriched"
    sections: list[Section] = field(default_factory=list)
    events: list[MusicalEvent] = field(default_factory=list)  # Tier 2 (future)
    features: TrackFeatures = field(default_factory=TrackFeatures)
    version: int = 1                   # incremented each enrichment pass
    created_at: float = field(default_factory=time.time)


# ── TrackCursor (Layer 1 → Layer 2 contract) ─────────────────────────────
# Defined here; imported by layer2 ONLY as a type — no layer1 internals.

@dataclass
class SectionInfo:
    """Current or upcoming section, with progress info."""
    label: str
    start_time: float
    end_time: float
    bar_count: int
    expected_bar_count: int
    progress: float                    # 0.0–1.0
    confidence: float
    irregular_phrase: bool
    fakeout: bool
    source: str                        # "analysis" | "pioneer_enriched"


@dataclass
class BeatPosition:
    beat_in_bar: int                   # 1–4
    bar_in_section: int
    is_downbeat: bool
    bpm: float                         # effective BPM (pitch-adjusted)
    original_bpm: float
    timestamp: float                   # wall clock


@dataclass
class PlaybackState:
    is_playing: bool
    is_master: bool
    player_number: int
    playback_position_ms: float
    pitch_percent: float


@dataclass
class TrackCursorFeatures:
    """Interpolated Tier 3 features at the current playback position."""
    energy: float = 0.5               # 0.0–1.0
    mood: str = "neutral"
    danceability: float = 0.5


@dataclass
class TrackCursor:
    """Real-time cursor into a TrackAnalysis. The Layer 1 → Layer 2 interface.

    Layer 2 imports only this class (and its contained types) from layer1.
    Do not change this shape without updating docs/CONTRACTS.md.
    """
    current_section: SectionInfo
    next_section: SectionInfo | None
    upcoming_events: list[MusicalEvent]  # next N events, time-adjusted for current BPM
    current_features: TrackCursorFeatures
    beat_position: BeatPosition
    playback_state: PlaybackState


# ── Divergence logging ────────────────────────────────────────────────────

@dataclass
class DivergenceRecord:
    """Logs a mismatch between SCUE's analysis and Pioneer/rekordbox data."""
    track_fingerprint: str
    field: str                         # "beatgrid" | "bpm" | "key" | "section_boundary" | "section_label"
    scue_value: Any
    pioneer_value: Any
    resolution: str                    # "pioneer_adopted" | "scue_kept" | "manual_override"
    timestamp: float = field(default_factory=time.time)
