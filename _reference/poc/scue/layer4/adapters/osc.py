"""OSC output adapter — Layer 4B.

Sends OSC messages to visual software (Resolume, TouchDesigner, VDMX, etc.).
The OSC address mapping is per-target-software config.

Status: STUB — not yet implemented (Milestone 9).
"""

from ...layer3.models import FixtureOutput
from .base import BaseAdapter


class OscAdapter(BaseAdapter):
    """OSC output via python-osc.

    TODO(milestone-9): implement.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self._host = host
        self._port = port

    def start(self) -> None:
        # TODO: initialize python-osc UDPClient
        pass

    def stop(self) -> None:
        pass

    def send(self, outputs: list[FixtureOutput]) -> None:
        # TODO: map abstract channels to OSC addresses and send
        pass
