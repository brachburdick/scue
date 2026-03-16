"""Priority & blending system — Layer 3C.

Merges multiple active effect instances targeting the same fixture group.
  HTP (Highest Takes Precedence) for brightness/intensity
  LTP (Latest Takes Precedence) for color and position

Status: STUB — not yet implemented (Milestone 4).
"""

from .models import FixtureOutput


def blend(outputs: list[FixtureOutput]) -> list[FixtureOutput]:
    """Merge overlapping FixtureOutputs using HTP/LTP rules.

    Args:
        outputs: all active effect outputs (may have multiple per fixture)

    Returns:
        One FixtureOutput per fixture with merged channel values.

    TODO(milestone-4): implement.
    HTP channels: brightness, strobe_rate
    LTP channels: color_*, position_*, beam_width, visual_trigger
    """
    # TODO: implement
    return outputs
