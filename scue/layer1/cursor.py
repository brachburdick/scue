"""TrackCursor — Layer 1B.

Maps the current playback position (from Pioneer) into a stored TrackAnalysis
and produces a TrackCursor snapshot consumed by Layer 2.

Key responsibilities:
  - Identify current_section and next_section from playback position
  - Compute progress through the current section (0.0–1.0)
  - Scale event timestamps from original BPM to effective BPM:
      scaled_time = original_time * (original_bpm / effective_bpm)
  - Provide a sliding window of upcoming_events
  - Interpolate Tier 3 features at the current position

Status: STUB — not yet implemented (Milestone 2).
"""

from .models import (
    TrackAnalysis, DeckState,
    TrackCursor, SectionInfo, BeatPosition, PlaybackState, TrackCursorFeatures,
    MusicalEvent,
)


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

    TODO(milestone-2): implement.
    """
    # TODO: implement
    # Steps:
    # 1. Compute position in seconds from deck.playback_position_ms / 1000
    # 2. Scale position: position_sec_original = position_sec * (effective_bpm / original_bpm)
    # 3. Find current_section: the section where start <= position < end
    # 4. Compute section.progress = (position - section.start) / (section.end - section.start)
    # 5. Find next_section (sections[i+1] or None)
    # 6. upcoming_events: events where event.timestamp > position, time-scaled, next N
    # 7. bar_in_section: count downbeats since section start
    # 8. Interpolate Tier 3 energy curve at current position
    return None
