"""Chase effect — sequential brightness sweep across fixture positions.

Status: STUB — not yet implemented (Milestone 4).
"""

from .base import BaseEffect


class ChaseEffect(BaseEffect):
    """Moving brightness peak across fixture group position axis.

    Parameters (from config/effects/chase.yaml):
      speed:     Hz (cycles per second)
      width:     fraction of position range that is lit (0.05–1.0)
      direction: "forward" | "reverse" | "bounce"
      color:     [r, g, b]
      intensity: peak brightness

    TODO(milestone-4): implement render().
    """

    name = "chase"
    one_shot = False

    def render(self, time: float, params: dict) -> dict[str, float]:
        """Compute brightness at normalized position `params['position']`.

        TODO(milestone-4): implement.
        The position parameter is passed per-fixture by the effect engine
        based on each fixture's configured position in the venue.
        """
        # TODO: implement
        return {"brightness": 0.0, "position_x": 0.0}
