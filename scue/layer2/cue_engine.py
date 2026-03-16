"""Cue generation engine — Layer 2 main loop.

Receives TrackCursor snapshots from Layer 1 and produces CueEvent streams
by calling all registered generators and merging their output.

This is a pure function at its core: (TrackCursor) → list[CueEvent].
No side effects. No state beyond the current input.

Status: STUB — not yet implemented (Milestone 3).
"""

from ..layer1.models import TrackCursor
from .cue_types import CueEvent


class CueEngine:
    """Transforms TrackCursor snapshots into CueEvent streams.

    TODO(milestone-3): implement.
    Runs at 40Hz tick rate. Beat events are injected from the cursor.
    """

    def __init__(self):
        # TODO: initialize generators
        pass

    def process(self, cursor: TrackCursor) -> list[CueEvent]:
        """Generate all cue events for the current cursor state.

        Args:
            cursor: current TrackCursor snapshot from Layer 1

        Returns:
            List of CueEvent objects sorted by priority (highest first).

        TODO(milestone-3): implement by calling each generator module
        and merging their output.
        """
        # TODO: implement
        return []
