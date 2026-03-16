# Interface Contracts

## Layer 0 → Layer 1: BridgeMessage

The bridge streams typed JSON messages over a local WebSocket. The adapter in `scue/bridge/adapter.py` normalizes these into Layer 1's internal types.

```python
@dataclass
class BridgeMessage:
    type: str               # "device_found" | "device_lost" | "bridge_status" |
                            # "player_status" | "track_metadata" | "beat_grid" |
                            # "waveform_detail" | "phrase_analysis" | "cue_points" | "beat"
    timestamp: float
    player_number: int | None
    payload: dict           # type-specific, see ARCHITECTURE.md for schemas
```

## Layer 1 → Layer 2: DeckMix

The DeckMix is the interface between Layer 1 and Layer 2.
Layer 2 MUST NOT import anything from layer1 except DeckMix, WeightedCursor, TrackCursor, and their contained types.

```python
@dataclass
class DeckMix:
    cursors: list[WeightedCursor]          # one per active deck

@dataclass
class WeightedCursor:
    cursor: TrackCursor
    weight: float                          # 0.0–1.0, how much this deck contributes
    source: str                            # "on_air" | "crossfader" | "manual"

@dataclass
class TrackCursor:
    player_number: int                     # physical deck (1, 2, 3, 4)
    current_section: SectionInfo
    next_section: SectionInfo | None
    upcoming_events: list[MusicalEvent]    # next N events, time-adjusted for current tempo
    current_features: TrackFeatures
    beat_position: BeatPosition
    playback_state: PlaybackState

@dataclass
class SectionInfo:
    label: str                             # intro, verse, build, drop, breakdown, outro
    start_time: float
    end_time: float
    bar_count: int
    expected_bar_count: int
    progress: float                        # 0.0–1.0
    confidence: float
    irregular_phrase: bool
    fakeout: bool
    source: str                            # "analysis" | "pioneer_enriched"

@dataclass
class BeatPosition:
    beat_in_bar: int                       # 1–4
    bar_in_section: int
    is_downbeat: bool
    bpm: float
    original_bpm: float
    timestamp: float
```

## Layer 2 → Layer 3: CueEvent stream

```python
@dataclass
class CueEvent:
    id: str
    type: str                              # see taxonomy in ARCHITECTURE.md
    timestamp: float
    duration: float | None
    intensity: float                       # 0.0–1.0
    musical_context: MusicalContext
    payload: dict                          # type-specific, schema per cue type
    priority: int                          # for drop decisions under load

@dataclass
class MusicalContext:
    section_label: str
    section_progress: float
    track_energy: float
    track_mood: str
```

## Layer 3 → Layer 4: AbstractOutput

```python
@dataclass
class FixtureOutput:
    fixture_name: str
    group: str
    channels: dict[str, float]             # channel_name → 0.0–1.0 normalized value
    # Standard channel names: brightness, color_r, color_g, color_b,
    # color_h, color_s, color_v, position, beam_width, strobe_rate
```

### Change Protocol
Any change to these contracts requires:
1. A discussion with Brach
2. An entry in docs/DECISIONS.md explaining why
3. Updates to both the producing and consuming layer
4. Updated tests on both sides
