"""User override state management — Layer 4C.

Allows real-time intervention from browser UI or MIDI controller:
  - Mute/unmute specific routing rules
  - Solo a fixture group
  - Override effect parameters
  - Manual one-shot cue triggers
  - Palette switching
  - Master brightness override
  - Blackout / full-on

Overrides are injected into Layer 3's blending system at highest priority.

Status: STUB — not yet implemented (Milestone 10).
"""

from dataclasses import dataclass, field


@dataclass
class OverrideState:
    """Current user override state. Injected into Layer 3 blender."""
    muted_routes: set[str] = field(default_factory=set)         # route names
    soloed_groups: set[str] = field(default_factory=set)        # group names
    master_brightness: float = 1.0                              # 0.0–1.0
    active_palette: str | None = None                           # override palette name
    blackout: bool = False
    full_on: bool = False
    parameter_overrides: dict[str, dict] = field(default_factory=dict)  # route → {param: value}


class OverrideManager:
    """Manages override state and exposes it to the blending system.

    TODO(milestone-10): implement with WebSocket and MIDI input.
    """

    def __init__(self):
        self.state = OverrideState()

    def mute_route(self, route_name: str) -> None:
        self.state.muted_routes.add(route_name)

    def unmute_route(self, route_name: str) -> None:
        self.state.muted_routes.discard(route_name)

    def set_master_brightness(self, value: float) -> None:
        self.state.master_brightness = max(0.0, min(1.0, value))

    def set_blackout(self, enabled: bool) -> None:
        self.state.blackout = enabled
