"""Layer 3 output models — the Layer 3 → Layer 4 interface contract.

Layer 4 imports ONLY FixtureOutput from this module.
See docs/CONTRACTS.md for the authoritative schema.
"""

from dataclasses import dataclass, field


@dataclass
class FixtureOutput:
    """Abstract channel values for a single fixture.

    Channels are normalized 0.0–1.0. Layer 4 translates these to
    protocol-specific values using fixture profiles.

    Standard channel names:
      brightness, color_r, color_g, color_b,
      color_h, color_s, color_v,
      position_x, position_y,
      beam_width, strobe_rate, visual_trigger

    Do not change this shape without updating docs/CONTRACTS.md.
    """
    fixture_name: str
    group: str
    channels: dict[str, float] = field(default_factory=dict)
