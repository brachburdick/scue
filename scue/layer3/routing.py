"""Routing table — Layer 3B.

Loads routing YAML from config/routing/ and matches incoming CueEvents
to route definitions. A matched route triggers an effect instance on a
target fixture group.

Status: STUB — not yet implemented (Milestone 4).
"""

import yaml
from pathlib import Path
from ..layer2.cue_types import CueEvent


class RoutingTable:
    """Loads and matches routing rules.

    TODO(milestone-4): implement.
    """

    def __init__(self, routing_yaml_path: str):
        # TODO: load and validate YAML
        pass

    def match(self, event: CueEvent) -> list[dict]:
        """Return all routes that match this cue event.

        TODO(milestone-4): implement condition matching
        (cue_type, musical_context filters, intensity thresholds).
        """
        # TODO: implement
        return []
