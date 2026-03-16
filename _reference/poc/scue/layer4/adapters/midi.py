"""MIDI output adapter — Layer 4B.

Sends MIDI CC messages or note-on/off to lighting controllers and visual software.

Status: STUB — not yet implemented (Milestone 10).
"""

from ...layer3.models import FixtureOutput
from .base import BaseAdapter


class MidiAdapter(BaseAdapter):
    """MIDI output adapter.

    TODO(milestone-10): implement using python-rtmidi or mido.
    """

    def __init__(self, port_name: str | None = None):
        self._port_name = port_name

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def send(self, outputs: list[FixtureOutput]) -> None:
        pass
