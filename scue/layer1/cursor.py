"""TrackCursor — Layer 1B.

Maps the current playback position (from Pioneer) into a stored TrackAnalysis
and produces a TrackCursor snapshot consumed by Layer 2.

Key responsibilities:
  - Identify current_section and next_section from playback position
  - Compute progress through the current section (0.0-1.0)
  - Scale event timestamps from original BPM to effective BPM:
      scaled_time = original_time * (original_bpm / effective_bpm)
  - Provide a sliding window of upcoming_events
  - Interpolate Tier 3 features at the current position
"""

import bisect
import time as _time

from .models import (
    TrackAnalysis, DeckState,
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
    # Energy curve is uniformly sampled over the track duration
    frac = position / duration
    frac = max(0.0, min(1.0, frac))
    idx_f = frac * (len(energy_curve) - 1)
    idx_lo = int(idx_f)
    idx_hi = min(idx_lo + 1, len(energy_curve) - 1)
    t = idx_f - idx_lo
    return energy_curve[idx_lo] * (1 - t) + energy_curve[idx_hi] * t


def build_cursor(
    analysis: TrackAnalysis,
    deck: DeckState,
    lookahead_events: int = 20,
) -> TrackCursor | None:
    """Build a TrackCursor from a stored analysis and current deck state.

    Args:
        analysis: the stored TrackAnalysis (preferably pioneer_enriched if available)
        deck: current DeckState from Pioneer
        lookahead_events: number of upcoming events to include

    Returns:
        A TrackCursor snapshot, or None if position cannot be determined.
    """
    if not analysis.sections:
        return None

    # 1. Position in seconds (Pioneer reports ms)
    position_sec = deck.playback_position_ms / 1000.0

    # 2. If BPMs differ (pitch-adjusted playback), map position to original-BPM timeline
    #    Analysis timestamps are stored at original BPM.
    #    Pioneer position_ms tracks real elapsed time at effective BPM.
    #    To find where we are in the analysis: pos_original = pos_real * (effective / original)
    #    But if analysis is already pioneer_enriched, timestamps match Pioneer's BPM,
    #    so we only need to scale by pitch adjustment.
    effective_bpm = deck.effective_bpm if deck.effective_bpm > 0 else analysis.bpm
    original_bpm = analysis.bpm

    # The analysis timestamps are at analysis.bpm.
    # Real playback is at effective_bpm.
    # position_in_analysis_timeline = position_sec (no extra scaling needed,
    #   because playback_position_ms already accounts for playback speed)
    position = position_sec

    # 3. Find current section
    sec_idx = _find_section_index(analysis.sections, position)
    if sec_idx is None:
        return None

    current_section = _section_to_info(analysis.sections[sec_idx], position)

    # 4. Next section
    next_section = None
    if sec_idx + 1 < len(analysis.sections):
        next_section = _section_to_info(analysis.sections[sec_idx + 1], position)

    # 5. Upcoming events — filter events after current position, take N
    upcoming: list[MusicalEvent] = []
    if analysis.events:
        start_idx = bisect.bisect_left(
            [e.timestamp for e in analysis.events], position
        )
        upcoming = analysis.events[start_idx:start_idx + lookahead_events]

    # 6. Beat position
    beat_in_bar = deck.beat_within_bar if deck.beat_within_bar > 0 else 1
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

    # 7. Playback state
    playback_state = PlaybackState(
        is_playing=deck.is_playing,
        is_master=deck.is_master,
        player_number=deck.player_number,
        playback_position_ms=deck.playback_position_ms,
        pitch_percent=deck.pitch_percent,
    )

    # 8. Interpolated features
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
