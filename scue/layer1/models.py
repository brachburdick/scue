"""Layer 1 data models — all dataclasses for track analysis and live tracking.

These are the canonical data structures for Layer 1. TrackAnalysis is serialized
to JSON files (source of truth) and indexed in SQLite (derived cache).

Enrichment-ready fields are present from day one (nullable) so that Milestone 0
(Pioneer enrichment) doesn't require a schema migration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Tier 1 — Section Segmentation
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A labeled section of a track (intro, verse, build, drop, etc.).

    All timestamps are in seconds relative to track start at original BPM.
    """
    label: str                      # intro | verse | build | drop | breakdown | fakeout | outro
    start: float                    # seconds at original BPM
    end: float                      # seconds at original BPM
    confidence: float = 0.5         # 0.0–1.0
    bar_count: int = 0              # actual bars in this section
    expected_bar_count: int = 0     # nearest 8-bar multiple
    irregular_phrase: bool = False  # True if bar_count != expected_bar_count
    fakeout: bool = False           # True if this is a fakeout drop
    original_label: str = ""        # label before EDM flow relabeling
    source: str = "analysis"        # "analysis" | "pioneer_enriched"

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return self.end - self.start


# ---------------------------------------------------------------------------
# Tier 2 — Event Detection (stub for Milestone 7)
# ---------------------------------------------------------------------------

@dataclass
class MusicalEvent:
    """A discrete musical event (kick, snare, riser, etc.).

    Tier 2 — not populated until Milestone 7. Present in the schema from
    day one so downstream layers can reference the type.
    """
    type: str                       # kick | snare | hihat | clap | riser | faller | stab | arp_note
    timestamp: float                # seconds from track start
    duration: float | None = None   # None for instantaneous events
    intensity: float = 0.5          # 0.0–1.0
    payload: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tier 3 — Track-Level Features
# ---------------------------------------------------------------------------

@dataclass
class TrackFeatures:
    """Coarse track-level descriptors for mood/palette selection.

    energy_curve is downsampled RMS (one value per ~0.5s).
    """
    energy_curve: list[float] = field(default_factory=list)
    mood: str = "neutral"           # dark | euphoric | melancholic | aggressive | neutral
    danceability: float = 0.5       # 0.0–1.0
    key: str = ""                   # e.g. "Cm", "F#m", "Ab"
    key_confidence: float = 0.0     # 0.0–1.0
    key_source: str = "analysis"    # "analysis" | "pioneer_enriched"


# ---------------------------------------------------------------------------
# RGB Waveform
# ---------------------------------------------------------------------------

@dataclass
class RGBWaveform:
    """3-band waveform visualization data (R=bass, G=mids, B=highs).

    Each band is a list of normalized 0.0–1.0 values at the given sample rate.
    """
    sample_rate: int = 60           # frames per second
    duration: float = 0.0           # track duration in seconds
    low: list[float] = field(default_factory=list)   # bass (0–250 Hz)
    mid: list[float] = field(default_factory=list)    # mids (250 Hz–4 kHz)
    high: list[float] = field(default_factory=list)   # highs (4 kHz+)


# ---------------------------------------------------------------------------
# TrackAnalysis — the main persisted object
# ---------------------------------------------------------------------------

@dataclass
class TrackAnalysis:
    """Complete analysis of a single audio track.

    Serialized to JSON as the source of truth. Indexed in SQLite as a
    derived cache. Enrichment-ready fields are nullable from day one.
    """
    fingerprint: str                # SHA256 of audio bytes — primary key
    audio_path: str                 # path to the audio file at analysis time
    title: str = ""                 # from file metadata or filename
    artist: str = ""                # from file metadata

    # Beatgrid
    bpm: float = 0.0
    beats: list[float] = field(default_factory=list)       # beat timestamps (seconds)
    downbeats: list[float] = field(default_factory=list)    # downbeat timestamps (seconds)
    beatgrid_source: str = "analysis"                       # "analysis" | "pioneer_enriched"

    # Tier 1 — Section Segmentation
    sections: list[Section] = field(default_factory=list)

    # Tier 2 — Event Detection (empty until Milestone 7)
    events: list[MusicalEvent] = field(default_factory=list)
    drum_patterns: list = field(default_factory=list)  # list[DrumPattern] — compact percussion

    # Tier 3 — Track-Level Features
    features: TrackFeatures = field(default_factory=TrackFeatures)

    # RGB Waveform
    waveform: RGBWaveform | None = None

    # Versioning & enrichment
    version: int = 1                # incremented per enrichment pass
    source: str = "analysis"        # "analysis" for offline, "pioneer_enriched" for enriched
    created_at: float = field(default_factory=time.time)
    duration: float = 0.0           # track duration in seconds

    # Pioneer enrichment placeholders (null until bridge is built)
    pioneer_bpm: float | None = None
    pioneer_key: str | None = None
    pioneer_beatgrid: list[float] | None = None
    rekordbox_id: int | None = None
    enrichment_timestamp: float | None = None


# ---------------------------------------------------------------------------
# Layer 1B — Live Tracking Types (TrackCursor contract)
# ---------------------------------------------------------------------------

@dataclass
class SectionInfo:
    """Current or upcoming section with progress info. Part of TrackCursor."""
    label: str
    start_time: float
    end_time: float
    bar_count: int
    expected_bar_count: int
    progress: float              # 0.0–1.0
    confidence: float
    irregular_phrase: bool
    fakeout: bool
    source: str                  # "analysis" | "pioneer_enriched"


@dataclass
class BeatPosition:
    """Current beat position within a section. Part of TrackCursor."""
    beat_in_bar: int             # 1–4
    bar_in_section: int
    is_downbeat: bool
    bpm: float                   # effective BPM (pitch-adjusted)
    original_bpm: float
    timestamp: float             # wall clock


@dataclass
class PlaybackState:
    """Playback transport state from Pioneer hardware. Part of TrackCursor."""
    is_playing: bool
    is_on_air: bool
    player_number: int
    playback_position_ms: float
    pitch_percent: float


@dataclass
class TrackCursorFeatures:
    """Interpolated Tier 3 features at the current playback position."""
    energy: float = 0.5          # 0.0–1.0
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


# ---------------------------------------------------------------------------
# Divergence Logging
# ---------------------------------------------------------------------------

@dataclass
class DivergenceRecord:
    """Logs a mismatch between SCUE's analysis and Pioneer/rekordbox data."""
    track_fingerprint: str
    divergence_field: str        # "beatgrid" | "bpm" | "key" | "section_boundary" | "section_label"
    scue_value: str
    pioneer_value: str
    resolution: str              # "pioneer_adopted" | "scue_kept" | "manual_override"
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def section_to_dict(section: Section) -> dict:
    """Serialize a Section to a JSON-safe dict."""
    return {
        "label": section.label,
        "start": section.start,
        "end": section.end,
        "confidence": section.confidence,
        "bar_count": section.bar_count,
        "expected_bar_count": section.expected_bar_count,
        "irregular_phrase": section.irregular_phrase,
        "fakeout": section.fakeout,
        "original_label": section.original_label,
        "source": section.source,
    }


def section_from_dict(data: dict) -> Section:
    """Deserialize a Section from a dict."""
    return Section(
        label=data["label"],
        start=data["start"],
        end=data["end"],
        confidence=data.get("confidence", 0.5),
        bar_count=data.get("bar_count", 0),
        expected_bar_count=data.get("expected_bar_count", 0),
        irregular_phrase=data.get("irregular_phrase", False),
        fakeout=data.get("fakeout", False),
        original_label=data.get("original_label", ""),
        source=data.get("source", "analysis"),
    )


def event_to_dict(event: MusicalEvent) -> dict:
    """Serialize a MusicalEvent to a JSON-safe dict."""
    return {
        "type": event.type,
        "timestamp": event.timestamp,
        "duration": event.duration,
        "intensity": event.intensity,
        "payload": event.payload,
    }


def event_from_dict(data: dict) -> MusicalEvent:
    """Deserialize a MusicalEvent from a dict."""
    return MusicalEvent(
        type=data["type"],
        timestamp=data["timestamp"],
        duration=data.get("duration"),
        intensity=data.get("intensity", 0.5),
        payload=data.get("payload", {}),
    )


def features_to_dict(features: TrackFeatures) -> dict:
    """Serialize TrackFeatures to a JSON-safe dict."""
    return {
        "energy_curve": features.energy_curve,
        "mood": features.mood,
        "danceability": features.danceability,
        "key": features.key,
        "key_confidence": features.key_confidence,
        "key_source": features.key_source,
    }


def features_from_dict(data: dict) -> TrackFeatures:
    """Deserialize TrackFeatures from a dict."""
    return TrackFeatures(
        energy_curve=data.get("energy_curve", []),
        mood=data.get("mood", "neutral"),
        danceability=data.get("danceability", 0.5),
        key=data.get("key", ""),
        key_confidence=data.get("key_confidence", 0.0),
        key_source=data.get("key_source", "analysis"),
    )


def waveform_to_dict(waveform: RGBWaveform) -> dict:
    """Serialize RGBWaveform to a JSON-safe dict."""
    return {
        "sample_rate": waveform.sample_rate,
        "duration": waveform.duration,
        "low": waveform.low,
        "mid": waveform.mid,
        "high": waveform.high,
    }


def waveform_from_dict(data: dict) -> RGBWaveform:
    """Deserialize RGBWaveform from a dict."""
    return RGBWaveform(
        sample_rate=data.get("sample_rate", 60),
        duration=data.get("duration", 0.0),
        low=data.get("low", []),
        mid=data.get("mid", []),
        high=data.get("high", []),
    )


def analysis_to_dict(analysis: TrackAnalysis) -> dict:
    """Serialize a TrackAnalysis to a JSON-safe dict."""
    from .detectors.events import drum_pattern_to_dict

    result = {
        "fingerprint": analysis.fingerprint,
        "audio_path": analysis.audio_path,
        "title": analysis.title,
        "artist": analysis.artist,
        "bpm": analysis.bpm,
        "beats": analysis.beats,
        "downbeats": analysis.downbeats,
        "beatgrid_source": analysis.beatgrid_source,
        "sections": [section_to_dict(s) for s in analysis.sections],
        "events": [event_to_dict(e) for e in analysis.events],
        "drum_patterns": [drum_pattern_to_dict(p) for p in analysis.drum_patterns],
        "features": features_to_dict(analysis.features),
        "waveform": waveform_to_dict(analysis.waveform) if analysis.waveform else None,
        "version": analysis.version,
        "source": analysis.source,
        "created_at": analysis.created_at,
        "duration": analysis.duration,
        "pioneer_bpm": analysis.pioneer_bpm,
        "pioneer_key": analysis.pioneer_key,
        "pioneer_beatgrid": analysis.pioneer_beatgrid,
        "rekordbox_id": analysis.rekordbox_id,
        "enrichment_timestamp": analysis.enrichment_timestamp,
    }
    return result


def analysis_from_dict(data: dict) -> TrackAnalysis:
    """Deserialize a TrackAnalysis from a dict."""
    from .detectors.events import drum_pattern_from_dict

    return TrackAnalysis(
        fingerprint=data["fingerprint"],
        audio_path=data["audio_path"],
        title=data.get("title", ""),
        artist=data.get("artist", ""),
        bpm=data.get("bpm", 0.0),
        beats=data.get("beats", []),
        downbeats=data.get("downbeats", []),
        beatgrid_source=data.get("beatgrid_source", "analysis"),
        sections=[section_from_dict(s) for s in data.get("sections", [])],
        events=[event_from_dict(e) for e in data.get("events", [])],
        drum_patterns=[drum_pattern_from_dict(p) for p in data.get("drum_patterns", [])],
        features=features_from_dict(data["features"]) if "features" in data else TrackFeatures(),
        waveform=waveform_from_dict(data["waveform"]) if data.get("waveform") else None,
        version=data.get("version", 1),
        source=data.get("source", "analysis"),
        created_at=data.get("created_at", 0.0),
        duration=data.get("duration", 0.0),
        pioneer_bpm=data.get("pioneer_bpm"),
        pioneer_key=data.get("pioneer_key"),
        pioneer_beatgrid=data.get("pioneer_beatgrid"),
        rekordbox_id=data.get("rekordbox_id"),
        enrichment_timestamp=data.get("enrichment_timestamp"),
    )
