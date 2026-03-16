"""Rhythmic cue generators — Milestone 3/7.

Generates: beat, kick, snare, percussion_pattern_change
from TrackCursor.beat_position and TrackCursor.upcoming_events.

Status: STUB — not yet implemented.
"""

from ...layer1.models import TrackCursor
from ..cue_types import CueEvent


def generate(cursor: TrackCursor) -> list[CueEvent]:
    """Generate rhythmic cue events.

    TODO(milestone-3): implement beat cues from cursor.beat_position.
    TODO(milestone-7): implement kick/snare from cursor.upcoming_events
      once Tier 2 percussion detection is built.
    """
    # TODO: implement
    return []
