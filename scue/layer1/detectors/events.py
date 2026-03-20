"""Event detection framework — protocol, config, result types, and pattern utilities.

Provides the pluggable detector infrastructure for M7 Event Detection.
All detectors implement DetectorProtocol and return DetectorResult objects.
Percussion events are stored as compact DrumPattern objects; tonal events
as individual MusicalEvent objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..models import MusicalEvent, Section

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compact Percussion Storage
# ---------------------------------------------------------------------------

@dataclass
class DrumPattern:
    """Compact percussion pattern for a range of bars.

    Each instrument array has 16 slots per bar (16th-note resolution).
    A value of 1 = hit, 0 = silent. Arrays are flat: len = 16 * (bar_end - bar_start).

    Hi-hat is stored as pattern metadata rather than individual hits,
    per the M7 spec (pattern-level info only).
    """
    bar_start: int                  # inclusive bar index (0-based)
    bar_end: int                    # exclusive bar index
    kick: list[int] = field(default_factory=list)    # 16 slots per bar
    snare: list[int] = field(default_factory=list)
    clap: list[int] = field(default_factory=list)
    hihat_type: str = "none"        # "8ths" | "16ths" | "offbeat" | "roll" | "none"
    hihat_density: float = 0.0      # 0.0–1.0
    hihat_open_ratio: float = 0.0   # fraction of open vs closed hits
    confidence: float = 0.5         # overall pattern confidence

    @property
    def bar_count(self) -> int:
        """Number of bars in this pattern."""
        return self.bar_end - self.bar_start

    @property
    def total_slots(self) -> int:
        """Total 16th-note slots across all bars."""
        return 16 * self.bar_count


def expand_patterns(
    patterns: list[DrumPattern],
    beats: list[float],
    downbeats: list[float],
) -> list[MusicalEvent]:
    """Expand compact DrumPattern objects into individual MusicalEvent objects.

    Used by Layer 1B (TrackCursor) to populate upcoming_events at playback time.

    Args:
        patterns: List of DrumPattern objects from analysis.
        beats: Beat timestamps in seconds (quarter notes).
        downbeats: Downbeat timestamps in seconds (bar boundaries).

    Returns:
        List of MusicalEvent objects sorted by timestamp.
    """
    events: list[MusicalEvent] = []

    if not downbeats or not beats:
        return events

    # Compute 16th-note duration from BPM (approximate from beat spacing)
    if len(beats) >= 2:
        avg_beat_duration = (beats[-1] - beats[0]) / (len(beats) - 1)
        sixteenth_duration = avg_beat_duration / 4.0
    else:
        return events

    for pattern in patterns:
        for bar_idx in range(pattern.bar_start, pattern.bar_end):
            if bar_idx >= len(downbeats):
                break

            bar_time = downbeats[bar_idx]
            local_bar = bar_idx - pattern.bar_start
            slot_offset = local_bar * 16

            for slot in range(16):
                abs_slot = slot_offset + slot
                timestamp = bar_time + slot * sixteenth_duration

                # Kick
                if abs_slot < len(pattern.kick) and pattern.kick[abs_slot]:
                    events.append(MusicalEvent(
                        type="kick",
                        timestamp=timestamp,
                        intensity=0.8,
                        payload={"bar": bar_idx, "slot": slot},
                    ))

                # Snare
                if abs_slot < len(pattern.snare) and pattern.snare[abs_slot]:
                    events.append(MusicalEvent(
                        type="snare",
                        timestamp=timestamp,
                        intensity=0.7,
                        payload={"bar": bar_idx, "slot": slot},
                    ))

                # Clap
                if abs_slot < len(pattern.clap) and pattern.clap[abs_slot]:
                    events.append(MusicalEvent(
                        type="clap",
                        timestamp=timestamp,
                        intensity=0.6,
                        payload={"bar": bar_idx, "slot": slot},
                    ))

    events.sort(key=lambda e: e.timestamp)
    return events


# ---------------------------------------------------------------------------
# Detector Result
# ---------------------------------------------------------------------------

@dataclass
class DetectorResult:
    """Standardized detector output.

    Contains both individual events (for tonal detectors) and compact
    patterns (for percussion detectors). A detector may populate either
    or both depending on its event types.
    """
    events: list[MusicalEvent] = field(default_factory=list)
    patterns: list[DrumPattern] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detector Configuration
# ---------------------------------------------------------------------------

@dataclass
class DetectorConfig:
    """Configuration for the event detection pipeline.

    Loaded from config/detectors.yaml. Specifies which strategies are active
    for each event type and the parameters for each strategy.
    """
    active_strategies: dict[str, str] = field(default_factory=dict)
    params: dict[str, dict] = field(default_factory=dict)
    section_priors: dict[str, dict[str, float]] = field(default_factory=dict)


def load_detector_config(config_path: str | Path | None = None) -> DetectorConfig:
    """Load detector configuration from a YAML file.

    Args:
        config_path: Path to detectors.yaml. If None, uses the default
            config at config/detectors.yaml relative to the scue package.

    Returns:
        DetectorConfig with all settings populated.
    """
    import yaml

    if config_path is None:
        # Default: scue/config/detectors.yaml
        config_path = Path(__file__).parent.parent.parent / "config" / "detectors.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning("Detector config not found at %s, using defaults", config_path)
        return _default_config()

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        logger.warning("Empty detector config at %s, using defaults", config_path)
        return _default_config()

    return DetectorConfig(
        active_strategies=raw.get("active_strategies", {}),
        params=raw.get("params", {}),
        section_priors=raw.get("section_priors", {}),
    )


def _default_config() -> DetectorConfig:
    """Sensible defaults when no config file is present."""
    return DetectorConfig(
        active_strategies={
            "percussion": "heuristic",
            "riser": "centroid_slope",
            "faller": "centroid_slope",
            "stab": "hpss_harmonic",
        },
        params={
            "heuristic": {
                "kick_low_band_threshold": 0.6,
                "snare_mid_band_threshold": 0.5,
                "hihat_high_band_threshold": 0.4,
            },
            "centroid_slope": {
                "min_slope": 50.0,
                "min_r_squared": 0.7,
                "min_bars": 2,
            },
            "hpss_harmonic": {
                "harmonic_ratio_threshold": 0.3,
                "min_centroid_hz": 500,
                "max_duration_ms": 200,
            },
        },
        section_priors={
            "riser": {"build": 1.5, "drop": 0.3, "breakdown": 0.5, "intro": 1.2, "verse": 0.5, "outro": 0.3},
            "faller": {"build": 0.2, "drop": 1.2, "breakdown": 1.5, "intro": 0.5, "verse": 0.5, "outro": 1.0},
            "stab": {"build": 0.8, "drop": 1.5, "breakdown": 0.5, "intro": 0.3, "verse": 0.5, "outro": 0.3},
        },
    )


# ---------------------------------------------------------------------------
# Detector Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class DetectorProtocol(Protocol):
    """Interface all event detectors must implement.

    Detectors receive extracted audio features, beatgrid info, section labels,
    and their config. They return a DetectorResult with detected events
    and/or drum patterns.
    """
    name: str
    event_types: list[str]

    def detect(
        self,
        features: Any,  # AudioFeatures — Any to avoid circular import
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult:
        """Run detection and return results."""
        ...


# ---------------------------------------------------------------------------
# Serialization Helpers
# ---------------------------------------------------------------------------

def drum_pattern_to_dict(pattern: DrumPattern) -> dict:
    """Serialize a DrumPattern to a JSON-safe dict."""
    return {
        "bar_start": pattern.bar_start,
        "bar_end": pattern.bar_end,
        "kick": pattern.kick,
        "snare": pattern.snare,
        "clap": pattern.clap,
        "hihat_type": pattern.hihat_type,
        "hihat_density": pattern.hihat_density,
        "hihat_open_ratio": pattern.hihat_open_ratio,
        "confidence": pattern.confidence,
    }


def drum_pattern_from_dict(data: dict) -> DrumPattern:
    """Deserialize a DrumPattern from a dict."""
    return DrumPattern(
        bar_start=data["bar_start"],
        bar_end=data["bar_end"],
        kick=data.get("kick", []),
        snare=data.get("snare", []),
        clap=data.get("clap", []),
        hihat_type=data.get("hihat_type", "none"),
        hihat_density=data.get("hihat_density", 0.0),
        hihat_open_ratio=data.get("hihat_open_ratio", 0.0),
        confidence=data.get("confidence", 0.5),
    )
