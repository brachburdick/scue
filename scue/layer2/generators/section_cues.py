"""Section cue generators — Milestone 3.

Generates: section_change, section_anticipation, section_progress
from TrackCursor.current_section and TrackCursor.next_section.

Status: STUB — not yet implemented (Milestone 3).
"""

from ...layer1.models import TrackCursor
from ..cue_types import CueEvent


def generate(cursor: TrackCursor) -> list[CueEvent]:
    """Generate section-level cue events.

    TODO(milestone-3): implement.
      - section_change: fire when current_section.label changes from last tick
      - section_anticipation: fire N beats before next_section starts
        (use cursor.next_section and cursor.beat_position to compute beats_until)
      - section_progress: fire every bar with progress info
    """
    # TODO: implement
    return []
