"""Abstract adapter interface — Layer 4B.

All protocol adapters (DMX, OSC, MIDI) implement this interface.
Adding a new protocol requires zero changes to Layers 1–3.
"""

from abc import ABC, abstractmethod
from ...layer3.models import FixtureOutput


class BaseAdapter(ABC):
    """Abstract base for all hardware protocol adapters."""

    @abstractmethod
    def send(self, outputs: list[FixtureOutput]) -> None:
        """Translate and transmit fixture output values via this protocol.

        Args:
            outputs: per-fixture abstract channel values from Layer 3
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Initialize the adapter (open connections, etc.)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Shut down the adapter cleanly."""
        ...
