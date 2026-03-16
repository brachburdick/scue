# Interface Contracts

The single most important document for preventing cross-layer breakage.
Any change to these contracts requires a discussion with Brach, an ADR entry in DECISIONS.md,
and updates to both the producing and consuming layer's tests.

---

## Layer 1 → Layer 2: TrackCursor

The `TrackCursor` is the only interface between Layer 1 and Layer 2.
Layer 2 MUST NOT import anything from `scue.layer1` except `TrackCursor` and its contained types.

```python
# scue/layer1/cursor.py  (source of truth for this contract)

@dataclass
class TrackCursor:
    current_section: SectionInfo
    next_section: SectionInfo | None
    upcoming_events: list[MusicalEvent]    # next N events, time-adjusted for current tempo
    current_features: TrackFeatures
    beat_position: BeatPosition
    playback_state: PlaybackState


@dataclass
class SectionInfo:
    label: str                             # intro, verse, build, drop, breakdown, fakeout, outro
    start_time: float                      # seconds, at original BPM
    end_time: float                        # seconds, at original BPM
    bar_count: int
    expected_bar_count: int                # nearest 8-bar multiple
    progress: float                        # 0.0–1.0 through this section
    confidence: float                      # 0.0–1.0
    irregular_phrase: bool                 # True if bar_count != expected_bar_count
    fakeout: bool
    source: str                            # "analysis" | "pioneer_enriched"


@dataclass
class BeatPosition:
    beat_in_bar: int                       # 1–4
    bar_in_section: int
    is_downbeat: bool
    bpm: float                             # effective BPM (after pitch adjustment)
    original_bpm: float                    # track's native BPM
    timestamp: float                       # seconds, wall clock


@dataclass
class PlaybackState:
    is_playing: bool
    is_master: bool
    player_number: int                     # Pioneer player number (1–4)
    playback_position_ms: float
    pitch_percent: float


@dataclass
class TrackFeatures:
    """Interpolated Tier 3 features at the current playback position."""
    energy: float                          # 0.0–1.0
    mood: str                              # dark, euphoric, melancholic, aggressive, neutral
    danceability: float                    # 0.0–1.0 (placeholder until Tier 3 is built)


@dataclass
class MusicalEvent:
    """A single Tier 2 event from the stored TrackAnalysis, time-adjusted for current BPM."""
    type: str                              # kick, snare, riser, faller, stab, arp, etc.
    timestamp: float                       # seconds from now (negative = just passed)
    duration: float | None
    intensity: float                       # 0.0–1.0
    payload: dict                          # type-specific data
```

---

## Layer 2 → Layer 3: CueEvent stream

Layer 3 MUST NOT import anything from `scue.layer2` except `CueEvent` and `MusicalContext`.

```python
# scue/layer2/cue_types.py  (source of truth for this contract)

@dataclass
class CueEvent:
    id: str                                # unique event ID (uuid)
    type: str                              # see taxonomy below
    timestamp: float                       # when this event fires (wall clock)
    duration: float | None                 # None for instantaneous
    intensity: float                       # 0.0–1.0
    musical_context: MusicalContext
    payload: dict                          # type-specific (schema per cue type)
    priority: int                          # for drop-under-load decisions


@dataclass
class MusicalContext:
    section_label: str                     # current section
    section_progress: float                # 0.0–1.0
    track_energy: float                    # 0.0–1.0
    track_mood: str                        # dark, euphoric, melancholic, aggressive, neutral
```

### CueEvent.type taxonomy

**Section cues** (from Tier 1):
- `section_change` — payload: `{ from_label, to_label, is_fakeout }`
- `section_anticipation` — payload: `{ upcoming_label, beats_until, is_fakeout }`
- `section_progress` — payload: `{ bars_elapsed, bars_total, progress }`

**Rhythmic cues** (from Tier 2):
- `beat` — payload: `{ beat_in_bar (1–4), is_downbeat }`
- `kick` — payload: `{ velocity }`
- `snare` — payload: `{ velocity }`
- `percussion_pattern_change` — payload: `{ element, old_interval, new_interval }`

**Melodic/harmonic cues** (from Tier 2):
- `arp_start` / `arp_note` / `arp_end` — payload: `{ note_index, interval_from_root, total_notes, pattern }`
- `riser` / `faller` — payload: `{ progress (0.0–1.0), curve_type }`
- `stab` — payload: `{ velocity }`

**Effect cues** (from Tier 2):
- `sweep` — payload: `{ parameter, value (0.0–1.0), direction }`
- `impact` — payload: `{ magnitude }` (composite: section_change + high energy + kick)

**Ambient cues** (from Tier 3):
- `mood_shift` — payload: `{ from_mood, to_mood }`
- `energy_level` — payload: `{ energy (0.0–1.0), trend (rising|falling|stable) }`

### Drop priority (lowest first, never drop section_change or impact)
`energy_level` → `mood_shift` → `section_progress` → `beat` → `sweep` → `arp_note`
→ `percussion_pattern_change` → everything else → `section_change` / `impact` (never dropped)

---

## Layer 3 → Layer 4: AbstractOutput

Layer 4 MUST NOT import anything from `scue.layer3` except `FixtureOutput`.

```python
# scue/layer3/models.py  (source of truth for this contract)

@dataclass
class FixtureOutput:
    fixture_name: str
    group: str
    channels: dict[str, float]             # channel_name → 0.0–1.0 normalized value

# Standard channel names:
#   brightness, color_r, color_g, color_b,
#   color_h, color_s, color_v,
#   position_x, position_y,
#   beam_width, strobe_rate, visual_trigger
```

---

## Change Protocol

Any change to these contracts requires:
1. A discussion with Brach (do not proceed unilaterally)
2. An entry in `docs/DECISIONS.md` explaining the why
3. Updates to both the producing and consuming layer's code
4. Updated tests on both sides that exercise the changed interface
5. Update this file to match
