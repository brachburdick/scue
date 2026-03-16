"""Fixture profile — maps abstract channels to DMX channel offsets.

Status: STUB — not yet implemented (Milestone 5).
"""

from dataclasses import dataclass


@dataclass
class ChannelMapping:
    offset: int                    # DMX channel offset from start address
    name: str                      # e.g. "red", "dimmer", "pan"
    abstract_type: str             # e.g. "color_r", "brightness", "position_x"
    value_range: tuple[int, int]   # DMX value range (usually [0, 255])


@dataclass
class FixtureProfile:
    """Defines how a fixture type maps abstract channels to DMX bytes."""
    id: str
    description: str
    channel_count: int
    channels: list[ChannelMapping]

    def abstract_to_dmx(self, abstract_channels: dict[str, float]) -> list[int]:
        """Convert abstract channel values (0.0–1.0) to DMX byte values (0–255).

        TODO(milestone-5): implement.
        """
        # TODO: implement
        return [0] * self.channel_count
