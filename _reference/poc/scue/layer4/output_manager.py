"""Output manager — Layer 4 coordinator.

Receives per-fixture abstract channel values from Layer 3 and routes them
to the appropriate protocol adapters.

Status: STUB — not yet implemented (Milestone 5).
"""

from ..layer3.models import FixtureOutput
from .adapters.base import BaseAdapter


class OutputManager:
    """Coordinates all protocol adapters.

    TODO(milestone-5): implement.
    """

    def __init__(self, adapters: list[BaseAdapter] | None = None):
        self._adapters: list[BaseAdapter] = adapters or []

    def send(self, outputs: list[FixtureOutput]) -> None:
        """Route fixture outputs to all registered adapters.

        TODO(milestone-5): implement — translate FixtureOutput channel values
        through fixture profiles to protocol-specific frames and send.
        """
        # TODO: implement
        pass
