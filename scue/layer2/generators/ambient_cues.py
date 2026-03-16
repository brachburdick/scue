"""Ambient cue generators — Milestone 3/8.

Generates: mood_shift, energy_level, impact
from TrackCursor.current_features and section context.

Status: STUB — not yet implemented.
"""

from ...layer1.models import TrackCursor
from ..cue_types import CueEvent


def generate(cursor: TrackCursor) -> list[CueEvent]:
    """Generate ambient cue events.

    TODO(milestone-3): implement energy_level from cursor.current_features.energy.
    TODO(milestone-8): implement mood_shift once Tier 3 features are built.
    TODO: implement impact as composite of section_change + kick + energy.
    """
    # TODO: implement
    return []
