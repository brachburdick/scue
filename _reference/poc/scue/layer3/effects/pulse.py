"""Pulse effect — brightness pulse with attack/sustain/decay envelope.

Status: STUB — not yet implemented (Milestone 4).
"""

import math
from .base import BaseEffect


class PulseEffect(BaseEffect):
    """Single brightness pulse. One-shot, fires once per trigger.

    Parameters (from config/effects/pulse.yaml):
      attack:    seconds to peak
      sustain:   seconds at peak
      decay:     seconds to fade out
      intensity: peak brightness (0.0–1.0)
      color:     [r, g, b] (0.0–1.0 each)

    TODO(milestone-4): implement render().
    """

    name = "pulse"
    one_shot = True

    def render(self, time: float, params: dict) -> dict[str, float]:
        """Compute envelope position at `time` seconds since trigger.

        TODO(milestone-4): implement ADSR envelope.
        """
        # TODO: implement
        attack  = params.get("attack",  0.02)
        sustain = params.get("sustain", 0.0)
        decay   = params.get("decay",  0.2)
        intensity = params.get("intensity", 1.0)
        color   = params.get("color", [1.0, 1.0, 1.0])

        # Placeholder: return zero
        return {
            "brightness": 0.0,
            "color_r": color[0] if isinstance(color, list) else 1.0,
            "color_g": color[1] if isinstance(color, list) else 1.0,
            "color_b": color[2] if isinstance(color, list) else 1.0,
        }
