"""DMX512 / Art-Net / sACN adapter — Layer 4B.

Translates abstract FixtureOutput channel values to DMX universe frames
and sends them at ~44Hz via OLA or python-sacn.

Status: STUB — not yet implemented (Milestone 5).
"""

from ...layer3.models import FixtureOutput
from .base import BaseAdapter


class DmxAdapter(BaseAdapter):
    """DMX output via OLA or python-sacn.

    TODO(milestone-5): implement.
    Options:
      - OLA (Open Lighting Architecture): runs as a daemon, supports Art-Net,
        sACN, USB-DMX (Enttec OpenDMX, DMXIS, etc.). Use pyola or ola Python bindings.
      - python-sacn: lighter weight, sACN only, no daemon required.
    """

    def __init__(self, universe: int = 1, backend: str = "sacn"):
        self._universe = universe
        self._backend = backend

    def start(self) -> None:
        # TODO: initialize sacn/OLA sender
        pass

    def stop(self) -> None:
        # TODO: cleanup
        pass

    def send(self, outputs: list[FixtureOutput]) -> None:
        # TODO: translate channel values → DMX frame bytes and transmit
        pass
