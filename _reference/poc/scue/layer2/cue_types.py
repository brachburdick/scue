"""CueEvent dataclasses — the Layer 2 → Layer 3 interface contract.

Layer 3 imports ONLY CueEvent and MusicalContext from this module.
See docs/CONTRACTS.md for the authoritative schema.
"""

from dataclasses import dataclass, field
import uuid


@dataclass
class MusicalContext:
    """Musical state at the moment a cue fires."""
    section_label: str              # intro, verse, build, drop, breakdown, fakeout, outro
    section_progress: float         # 0.0–1.0 through current section
    track_energy: float             # 0.0–1.0
    track_mood: str                 # dark, euphoric, melancholic, aggressive, neutral


@dataclass
class CueEvent:
    """A typed semantic music event consumed by Layer 3.

    Do not change this shape without updating docs/CONTRACTS.md.
    """
    type: str                       # see taxonomy in docs/CONTRACTS.md
    timestamp: float                # wall clock (seconds)
    musical_context: MusicalContext
    intensity: float = 0.5         # 0.0–1.0
    duration: float | None = None  # None for instantaneous
    payload: dict = field(default_factory=dict)
    priority: int = 5              # for drop-under-load decisions (lower = drop first)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ── Priority table (lower number = drop first under load) ─────────────────
# section_change and impact are always delivered (priority 10).
CUE_PRIORITIES: dict[str, int] = {
    "energy_level":              1,
    "mood_shift":                2,
    "section_progress":          3,
    "beat":                      4,
    "sweep":                     4,
    "arp_note":                  4,
    "percussion_pattern_change": 5,
    "kick":                      6,
    "snare":                     6,
    "riser":                     7,
    "faller":                    7,
    "stab":                      7,
    "arp_start":                 7,
    "arp_end":                   7,
    "section_anticipation":      8,
    "section_change":            10,
    "impact":                    10,
}
