"""Venue configuration loader — Layer 4A.

Loads and validates venue YAML files from config/venues/.
Provides fixture instances, group membership, and spatial positions.

Status: STUB — not yet implemented (Milestone 5).
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class FixtureInstance:
    """A physical fixture in the venue."""
    name: str
    definition_id: str
    dmx_universe: int
    dmx_start_address: int
    position_x: float              # normalized 0.0–1.0
    position_y: float              # normalized 0.0–1.0
    groups: list[str] = field(default_factory=list)


@dataclass
class VenueConfig:
    """Loaded and validated venue configuration."""
    name: str
    fixtures: list[FixtureInstance] = field(default_factory=list)
    fixture_definitions: dict = field(default_factory=dict)
    groups: dict[str, list[str]] = field(default_factory=dict)  # group_name → [fixture_names]


def load_venue(yaml_path: str) -> VenueConfig:
    """Load a venue configuration from a YAML file.

    TODO(milestone-5): implement validation and fixture profile resolution.
    """
    # TODO: implement
    raise NotImplementedError("venue.load_venue not yet implemented — see Milestone 5")
