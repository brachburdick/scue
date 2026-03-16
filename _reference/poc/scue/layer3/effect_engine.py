"""Effect Engine — Layer 3 main loop.

Receives CueEvent streams from Layer 2, matches them against routing rules,
instantiates/updates effect generators, blends overlapping effects, and
outputs per-fixture abstract channel values.

Status: STUB — not yet implemented (Milestone 4).
"""

from ..layer2.cue_types import CueEvent
from .models import FixtureOutput


class EffectEngine:
    """Maps CueEvent streams to abstract FixtureOutput values.

    TODO(milestone-4): implement.
    Sub-components:
      - routing.py: load routing YAML, match CueEvents to routes
      - effects/: run effect generators for active routes
      - blender.py: HTP/LTP merge of overlapping effects
      - palette.py: resolve palette.* bindings in routing params
    """

    def __init__(self, config_dir: str = "config"):
        # TODO: load routing tables, effect definitions, palettes
        self._config_dir = config_dir

    def process(self, cue_events: list[CueEvent], timestamp: float) -> list[FixtureOutput]:
        """Process cue events and produce fixture output values.

        Args:
            cue_events: cue events from Layer 2 for this tick
            timestamp: current wall clock (seconds)

        Returns:
            List of FixtureOutput, one per fixture with active effects.

        TODO(milestone-4): implement.
        """
        # TODO: implement
        return []
