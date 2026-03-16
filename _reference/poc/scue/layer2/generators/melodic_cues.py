"""Melodic/harmonic cue generators — Milestone 8.

Generates: arp_start, arp_note, arp_end, riser, faller, stab
from TrackCursor.upcoming_events.

Status: STUB — not yet implemented (Milestone 8, depends on Tier 2 event detection).
"""

from ...layer1.models import TrackCursor
from ..cue_types import CueEvent


def generate(cursor: TrackCursor) -> list[CueEvent]:
    """Generate melodic cue events from upcoming Tier 2 events.

    TODO(milestone-8): implement once Tier 2 melodic detection is built.
    """
    # TODO: implement
    return []
