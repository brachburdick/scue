"""TrackCursor — Layer 1B.

Maps the current playback position (from Pioneer via bridge adapter) into a
stored TrackAnalysis and produces a TrackCursor snapshot consumed by Layer 2.

Key responsibilities:
  - Identify current_section and next_section from playback position
  - Compute progress through the current section (0.0-1.0)
  - Provide a sliding window of upcoming_events
  - Interpolate Tier 3 features at the current position

Consumes PlayerState from scue.bridge.adapter (not DeckState from POC).
"""

import bisect
import time as _time

from ..bridge.adapter import PlayerState
from .models import (
    TrackAnalysis,
    TrackCursor, SectionInfo, BeatPosition, PlaybackState, TrackCursorFeatures,
    MusicalEvent, Section,
)


def _section_to_info(section: Section, position: float) -> SectionInfo:
    """Convert a Section + current position into a SectionInfo with progress."""
    duration = section.end - section.start
    progress = 0.0
    if duration > 0:
        progress = max(0.0, min(1.0, (position - section.start) / duration))
    return SectionInfo(
        label=section.label,
        start_time=section.start,
        end_time=section.end,
        bar_count=section.bar_count,
        expected_bar_count=section.expected_bar_count,
        progress=progress,
        confidence=section.confidence,
        irregular_phrase=section.irregular_phrase,
        fakeout=section.fakeout,
        source=section.source,
    )


def _find_section_index(sections: list[Section], position: float) -> int | None:
    """Find the index of the section containing the given position.

    Uses linear scan since section count is small (typically <20).
    """
    for i, sec in enumerate(sections):
        if sec.start <= position < sec.end:
            return i
    # If past all sections, return last section
    if sections and position >= sections[-1].start:
        return len(sections) - 1
    return None


def _count_bars_in_section(
    downbeats: list[float], section_start: float, position: float
) -> int:
    """Count how many downbeats have passed since section_start up to position."""
    start_idx = bisect.bisect_left(downbeats, section_start)
    pos_idx = bisect.bisect_right(downbeats, position)
    return max(0, pos_idx - start_idx)


def _interpolate_energy(energy_curve: list[float], position: float, duration: float) -> float:
    """Interpolate the energy curve at the given position."""
    if not energy_curve or duration <= 0:
        return 0.5
    frac = max(0.0, min(1.0, position / duration))
    idx_f = frac * (len(energy_curve) - 1)
    idx_lo = int(idx_f)
    idx_hi = min(idx_lo + 1, len(energy_curve) - 1)
    t = idx_f - idx_lo
    return energy_curve[idx_lo] * (1 - t) + energy_curve[idx_hi] * t


def build_cursor(
    analysis: TrackAnalysis,
    player: PlayerState,
    position_ms: float | None = None,
    lookahead_events: int = 20,
) -> TrackCursor | None:
    """Build a TrackCursor from a stored analysis and current player state.

    Args:
        analysis: the stored TrackAnalysis (preferably pioneer_enriched if available).
        player: current PlayerState from bridge adapter.
        position_ms: override playback position (ms). Uses beat-estimated position
                     if None — callers should provide this from player_status.
        lookahead_events: number of upcoming events to include.

    Returns:
        A TrackCursor snapshot, or None if position cannot be determined.
    """
    if not analysis.sections:
        return None

    # Position in seconds
    pos_ms = position_ms if position_ms is not None else 0.0
    position = pos_ms / 1000.0

    effective_bpm = player.bpm if player.bpm > 0 else analysis.bpm
    original_bpm = analysis.bpm

    # Find current section
    sec_idx = _find_section_index(analysis.sections, position)
    if sec_idx is None:
        return None

    current_section = _section_to_info(analysis.sections[sec_idx], position)

    # Next section
    next_section = None
    if sec_idx + 1 < len(analysis.sections):
        next_section = _section_to_info(analysis.sections[sec_idx + 1], position)

    # Upcoming events — filter events after current position, take N
    upcoming: list[MusicalEvent] = []
    if analysis.events:
        start_idx = bisect.bisect_left(
            [e.timestamp for e in analysis.events], position
        )
        upcoming = analysis.events[start_idx:start_idx + lookahead_events]

    # Beat position
    beat_in_bar = player.beat_within_bar if player.beat_within_bar > 0 else 1
    bar_in_section = _count_bars_in_section(
        analysis.downbeats, analysis.sections[sec_idx].start, position
    )

    beat_position = BeatPosition(
        beat_in_bar=beat_in_bar,
        bar_in_section=bar_in_section,
        is_downbeat=(beat_in_bar == 1),
        bpm=effective_bpm,
        original_bpm=original_bpm,
        timestamp=_time.time(),
    )

    # Playback state
    playback_state = PlaybackState(
        is_playing=(player.playback_state == "playing"),
        is_on_air=player.is_on_air,
        player_number=player.player_number,
        playback_position_ms=pos_ms,
        pitch_percent=player.pitch,
    )

    # Interpolated features
    track_duration = analysis.sections[-1].end if analysis.sections else 0
    energy = _interpolate_energy(
        analysis.features.energy_curve, position, track_duration
    )
    cursor_features = TrackCursorFeatures(
        energy=energy,
        mood=analysis.features.mood,
        danceability=analysis.features.danceability,
    )

    return TrackCursor(
        current_section=current_section,
        next_section=next_section,
        upcoming_events=upcoming,
        current_features=cursor_features,
        beat_position=beat_position,
        playback_state=playback_state,
    )
