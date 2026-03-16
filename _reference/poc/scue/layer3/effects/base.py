"""Abstract base class for effect generators — Layer 3A.

All effects implement this interface. Effects are parameterized generators:
  (time: float, params: dict) → dict[str, float]  (channel_name → 0.0–1.0)

Status: STUB — not yet implemented (Milestone 4).
"""

from abc import ABC, abstractmethod


class BaseEffect(ABC):
    """Abstract base for all effect generator implementations."""

    @abstractmethod
    def render(self, time: float, params: dict) -> dict[str, float]:
        """Compute channel values at the given time with the given parameters.

        Args:
            time: seconds since the effect was triggered
            params: merged parameter dict (route definition + runtime bindings)

        Returns:
            Dict of channel_name → 0.0–1.0 for each output channel.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Effect name, matching the YAML effect definition."""
        ...

    @property
    def one_shot(self) -> bool:
        """True if this effect fires once and does not repeat."""
        return False
