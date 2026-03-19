# Spec: M3 Cue Stream (Layer 2, Section Cues Only)

## Summary

Layer 2 transforms the `DeckMix` produced by Layer 1 into a stream of semantic `CueEvent` objects that describe musical meaning — not hardware instructions. Milestone 3 implements the **section-level subset** of the full cue taxonomy: section boundaries, section type awareness, section progress, and energy trajectory. Beat-level cues (M8), event detection cues (M7), and multi-deck blending (Phase 2) are out of scope.

## User-Facing Behavior

Layer 2 runs as part of the real-time processing loop. When a DJ is playing a track and Layer 1 is producing `DeckMix` snapshots, Layer 2 continuously emits `CueEvent` messages that downstream layers (Layer 3 effect engine) consume. For M3, the observable effects are:

- A `section_change` cue fires at every section boundary (e.g., build to drop), driving the biggest visual transitions.
- A `section_anticipation` cue fires N bars before an upcoming section change, allowing Layer 3 to start building intensity before a drop.
- A `section_progress` cue fires every bar, reporting how far through the current section the playback is, enabling smooth ramping effects.
- An `energy_level` cue fires every bar, reporting the current energy and its trend (rising/falling/stable), enabling palette and brightness adjustments.

## Technical Requirements

- TR-01: Layer 2 SHALL consume `DeckMix` as its sole input from Layer 1.
- TR-02: Layer 2 SHALL produce a list of `CueEvent` objects per tick.
- TR-03: The processing loop SHALL run at 40 Hz (every 25 ms), consistent with ADR-002.
- TR-04: Layer 2 SHALL maintain per-deck state to detect section transitions.
- TR-05: Layer 2 SHALL NOT import from `scue.layer1` except the contract types: `DeckMix`, `WeightedCursor`, `TrackCursor`, `SectionInfo`, `BeatPosition`, `PlaybackState`, `TrackCursorFeatures`, `MusicalEvent`.
- TR-06: All tuning parameters (anticipation bars, intensity curves, thresholds) SHALL be loaded from `config/cues.yaml`.
- TR-07: Layer 2 SHALL handle empty `DeckMix` (no active decks) by emitting zero cues.
- TR-08: Layer 2 SHALL handle stale `DeckMix` (same timestamp as previous tick) by emitting only continuous cues (progress, energy) with no duplicate transition cues.
- TR-09: Layer 2 SHALL support 1-4 decks in its state model, even though M3 only exercises single-deck (Phase 1 master-only).
- TR-10: `section_change` and `section_anticipation` cues SHALL fire exactly once per transition (deduplication via state tracking).

## Interface Definitions

### Input — DeckMix (from CONTRACTS.md, no changes)

```python
# These types are imported from scue.layer1.models
# Layer 2 imports ONLY these types from layer1

@dataclass
class DeckMix:
    cursors: list[WeightedCursor]

@dataclass
class WeightedCursor:
    cursor: TrackCursor
    weight: float              # 0.0-1.0
    source: str                # "on_air" | "crossfader" | "manual"

@dataclass
class TrackCursor:
    current_section: SectionInfo
    next_section: SectionInfo | None
    upcoming_events: list[MusicalEvent]
    current_features: TrackCursorFeatures
    beat_position: BeatPosition
    playback_state: PlaybackState

@dataclass
class SectionInfo:
    label: str                 # intro | verse | build | drop | breakdown | fakeout | outro
    start_time: float
    end_time: float
    bar_count: int
    expected_bar_count: int
    progress: float            # 0.0-1.0
    confidence: float
    irregular_phrase: bool
    fakeout: bool
    source: str
```

### Output — CueEvent stream

The existing `CueEvent` contract in CONTRACTS.md is sufficient for M3. No changes needed.

```python
@dataclass
class CueEvent:
    id: str                    # unique per event, format: "{type}:{deck}:{monotonic_counter}"
    type: str                  # see M3 cue types below
    timestamp: float           # wall-clock time when this cue fires
    duration: float | None     # None for instantaneous, seconds for continuous
    intensity: float           # 0.0-1.0
    musical_context: MusicalContext
    payload: dict              # type-specific, schemas defined below
    priority: int              # for drop decisions under load

@dataclass
class MusicalContext:
    section_label: str
    section_progress: float
    track_energy: float
    track_mood: str
```

### [CONTRACT CHANGE] — CueEvent.deck_number field

The current CueEvent contract in CONTRACTS.md does not include a `deck_number` field. For multi-deck support (even in Phase 1 where only one deck is active), each CueEvent should identify which deck produced it. This enables Layer 3 to route cues to deck-specific effect chains in Phase 2.

**Proposed addition:**

```python
@dataclass
class CueEvent:
    # ... existing fields ...
    deck_number: int           # player_number from the originating deck (1-4)
```

This is a non-breaking additive change. Existing consumers can ignore the field.

### M3 Cue Types — Payloads and Behavior

#### `section_change` (instantaneous, priority 100)

Fires exactly once when playback crosses a section boundary.

```python
payload = {
    "from_label": str,         # previous section label (or "none" at track start)
    "to_label": str,           # new section label
    "is_fakeout": bool,        # True if the new section is a fakeout
    "confidence": float,       # section boundary confidence (0.0-1.0)
}
```

**Intensity mapping:** Derived from the transition type. See section "Intensity Mapping by Transition Type" below.

#### `section_anticipation` (instantaneous, priority 90)

Fires once when playback is N bars before an upcoming section boundary (N is configurable, default 4 bars). Only fires if `next_section` is not None.

```python
payload = {
    "upcoming_label": str,     # label of the section about to start
    "bars_until": int,         # bars remaining until section change
    "beats_until": int,        # beats remaining (bars_until * 4)
    "is_fakeout": bool,        # True if upcoming section is a fakeout
}
```

**Intensity mapping:** Same as the `section_change` intensity for the upcoming transition, scaled by `0.5` (anticipation is half the intensity of the actual change).

#### `section_progress` (continuous, priority 20)

Fires every bar (on downbeat). Reports how far through the current section playback has progressed.

```python
payload = {
    "bars_elapsed": int,       # bars played so far in this section
    "bars_total": int,         # total bars in this section (bar_count)
    "progress": float,         # 0.0-1.0 (same as SectionInfo.progress)
    "section_label": str,      # current section label
    "irregular_phrase": bool,  # True if this is a non-standard phrase length
}
```

**Intensity mapping:** Varies by section type. See "Section Progress Intensity Curves" below.

#### `energy_level` (continuous, priority 10)

Fires every bar (on downbeat). Reports the current energy level and its trajectory.

```python
payload = {
    "energy": float,           # 0.0-1.0 from TrackCursorFeatures.energy
    "trend": str,              # "rising" | "falling" | "stable"
    "mood": str,               # from TrackCursorFeatures.mood
}
```

**Intensity mapping:** Directly equal to the `energy` value.

**Trend calculation:** Compare current energy to the energy N bars ago (configurable, default 4 bars). If delta > +0.05: "rising". If delta < -0.05: "falling". Else: "stable". The threshold is configurable.

### Intensity Mapping by Transition Type

Section transitions have different visual significance. The `section_change` intensity is determined by the transition pair:

| From \ To   | intro | verse | build | drop | breakdown | fakeout | outro |
|-------------|-------|-------|-------|------|-----------|---------|-------|
| (start)     | 0.3   | 0.5   | 0.6   | 0.9  | 0.4       | 0.7     | 0.3   |
| intro       | 0.2   | 0.5   | 0.6   | 0.9  | 0.4       | 0.7     | 0.3   |
| verse       | 0.3   | 0.2   | 0.7   | 0.9  | 0.5       | 0.7     | 0.3   |
| build       | 0.3   | 0.4   | 0.5   | 1.0  | 0.6       | 0.8     | 0.3   |
| drop        | 0.3   | 0.5   | 0.6   | 0.7  | 0.8       | 0.7     | 0.5   |
| breakdown   | 0.3   | 0.5   | 0.7   | 0.9  | 0.3       | 0.7     | 0.4   |
| fakeout     | 0.3   | 0.4   | 0.8   | 1.0  | 0.5       | 0.5     | 0.3   |
| outro       | 0.3   | 0.3   | 0.4   | 0.6  | 0.3       | 0.4     | 0.1   |

Key rationale:
- `build -> drop` is the highest intensity transition (1.0) because this is THE moment in EDM.
- `fakeout -> build` is high (0.8) because the re-build after a fakeout creates tension.
- `drop -> breakdown` is high (0.8) because the energy release is dramatic.
- Same-label transitions are low (0.1-0.3) because they indicate continuation.

This table is stored in `config/cues.yaml` under `transition_intensity` and is fully user-configurable.

`[DECISION OPPORTUNITY]`: The intensity values above are reasonable defaults based on EDM conventions. Brach may want to tune them after hearing the system in action.

### Section Progress Intensity Curves

Different section types should have different intensity curves as playback progresses through them:

| Section Type | Curve       | Formula                           | Rationale                                      |
|-------------|-------------|-----------------------------------|-------------------------------------------------|
| intro       | flat_low    | `0.3`                             | Intros are calm, steady state                    |
| verse       | flat_mid    | `0.5`                             | Verses maintain moderate energy                  |
| build       | exponential | `0.3 + 0.7 * progress^2`         | Builds ramp up exponentially toward the drop     |
| drop        | flat_high   | `0.9`                             | Drops sustain peak energy                        |
| breakdown   | inverse_exp | `0.7 - 0.4 * progress^2`         | Breakdowns wind down from moderate to low        |
| fakeout     | spike       | `0.8 * (1.0 - progress)`         | Fakeouts spike then quickly fade                 |
| outro       | ramp_down   | `0.4 * (1.0 - progress)`         | Outros fade toward silence                       |

These curves are defined in `config/cues.yaml` under `section_intensity_curves`. Each curve is specified as a `type` (flat, linear, exponential, inverse_exp, spike) with parameters, not as a formula string.

`[DECISION OPPORTUNITY]`: These curve shapes are educated guesses. Brach may want to tune them after testing.

## Layer Boundaries

- **Layer 1** is responsible for: producing `DeckMix` (with `WeightedCursor`/`TrackCursor` per active deck). Layer 1 provides section info, beat position, playback state, and features. Layer 2 does NOT re-analyze audio or compute sections.
- **Layer 2** is responsible for: interpreting `DeckMix` and generating semantic `CueEvent` objects. Layer 2 knows about music structure (what a build-to-drop transition means) but knows nothing about lights, colors, or hardware.
- **Layer 3** is responsible for: consuming `CueEvent` objects and mapping them to abstract visual output. Layer 3 does not understand music structure — it only reacts to cue types and intensities.
- Interface between Layer 1 and Layer 2: `DeckMix` (defined in `docs/CONTRACTS.md`)
- Interface between Layer 2 and Layer 3: `CueEvent` stream (defined in `docs/CONTRACTS.md`)

## Processing Model

### Tick-Based at 40 Hz (ADR-002)

Layer 2 operates on a fixed 40 Hz tick loop (25 ms per tick). On each tick, the cue engine:

1. Receives the current `DeckMix` snapshot from Layer 1.
2. For each `WeightedCursor` with `weight > 0`:
   a. Compares the cursor's state against the stored per-deck state to detect transitions.
   b. Generates any instantaneous cues (section_change, section_anticipation) triggered by state changes.
   c. Generates continuous cues (section_progress, energy_level) if a bar boundary has been crossed since the last tick.
3. Applies weight scaling to all generated cues (Phase 1: master at 1.0, this is a no-op).
4. Returns the merged list of `CueEvent` objects.

**Why tick-based, not event-driven:** ADR-002 established the 40 Hz fixed loop. Tick-based processing is simpler, produces smoother continuous output, and avoids variable-rate complications. Beat events from the cursor are consumed within the tick when the tick detects a beat boundary crossing — there is no separate beat callback in M3 (beat-level cues are M8).

**Bar boundary detection:** On each tick, the cue engine checks `beat_position.is_downbeat` and `beat_position.bar_in_section` against the previous tick's values. If `bar_in_section` has incremented (or wrapped due to section change), a bar boundary has been crossed and continuous cues fire. This avoids duplicate emissions when multiple ticks fall within the same bar.

### Entry Point Signature

```python
class CueEngine:
    """Stateful cue generator. Maintains per-deck state between ticks."""

    def __init__(self, config: CueConfig) -> None: ...

    def tick(self, deck_mix: DeckMix, wall_time: float) -> list[CueEvent]:
        """Process one tick. Returns cue events generated during this tick.

        Args:
            deck_mix: Current DeckMix from Layer 1.
            wall_time: Monotonic wall-clock time for this tick (time.monotonic()).

        Returns:
            List of CueEvent objects (may be empty).
        """
```

### Per-Deck Generator (Pure Function with State Delta)

```python
class DeckCueGenerator:
    """Per-deck cue generator. Tracks state for one deck across ticks."""

    def __init__(self, player_number: int, config: CueConfig) -> None: ...

    def process(self, cursor: TrackCursor, wall_time: float) -> list[CueEvent]:
        """Generate cues from a single cursor, comparing against previous state.

        Detects section transitions, bar boundaries, and energy changes.
        Updates internal state. Returns generated cues.
        """
```

## Configuration Schema

All configuration lives in `config/cues.yaml`. The following schema uses the same YAML-top-level-key pattern as existing config files.

```yaml
cues:
  # --- Section Change ---
  transition_intensity:
    # Matrix of from_label -> to_label -> intensity (0.0-1.0)
    # Only non-default pairs need to be listed; missing pairs default to 0.5
    default: 0.5
    overrides:
      build:
        drop: 1.0
        breakdown: 0.6
        fakeout: 0.8
      drop:
        breakdown: 0.8
      fakeout:
        build: 0.8
        drop: 1.0
      breakdown:
        build: 0.7
        drop: 0.9
      intro:
        verse: 0.5
        build: 0.6
      verse:
        build: 0.7
      # ... full matrix shipped in default config

  # --- Section Anticipation ---
  anticipation:
    bars_before: 4             # How many bars before a section change to fire
    intensity_scale: 0.5       # Multiplier on the transition intensity

  # --- Section Progress ---
  section_intensity_curves:
    intro:
      type: flat
      value: 0.3
    verse:
      type: flat
      value: 0.5
    build:
      type: exponential
      base: 0.3
      peak: 1.0
      exponent: 2.0
    drop:
      type: flat
      value: 0.9
    breakdown:
      type: inverse_exponential
      base: 0.7
      floor: 0.3
      exponent: 2.0
    fakeout:
      type: linear
      start: 0.8
      end: 0.1
    outro:
      type: linear
      start: 0.4
      end: 0.0

  # --- Energy Level ---
  energy:
    trend_lookback_bars: 4     # Bars to compare for trend detection
    trend_threshold: 0.05      # Delta below which trend is "stable"

  # --- General ---
  min_cue_intensity: 0.05      # Cues below this intensity are dropped
  id_prefix: "cue"             # Prefix for CueEvent.id generation
```

### CueConfig Dataclass

```python
@dataclass
class CurveConfig:
    type: str                  # "flat" | "linear" | "exponential" | "inverse_exponential"
    value: float = 0.5         # for flat curves
    start: float = 0.0         # for linear curves
    end: float = 1.0           # for linear curves
    base: float = 0.0          # for exponential curves
    peak: float = 1.0          # for exponential curves
    floor: float = 0.0         # for inverse_exponential curves
    exponent: float = 2.0      # for exponential/inverse_exponential

@dataclass
class AnticipationConfig:
    bars_before: int = 4
    intensity_scale: float = 0.5

@dataclass
class EnergyConfig:
    trend_lookback_bars: int = 4
    trend_threshold: float = 0.05

@dataclass
class CueConfig:
    transition_intensity_default: float = 0.5
    transition_intensity_overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    anticipation: AnticipationConfig = field(default_factory=AnticipationConfig)
    section_intensity_curves: dict[str, CurveConfig] = field(default_factory=dict)
    energy: EnergyConfig = field(default_factory=EnergyConfig)
    min_cue_intensity: float = 0.05
    id_prefix: str = "cue"
```

## State Management

Layer 2 maintains per-deck state between ticks. The `DeckCueGenerator` holds:

```python
@dataclass
class DeckState:
    player_number: int
    # Section tracking
    current_section_label: str | None = None    # label of the section we are currently in
    current_section_start: float | None = None  # start_time of the current section
    # Bar tracking (for continuous cue firing)
    last_bar_in_section: int = -1               # bar_in_section from previous tick
    last_downbeat_seen: bool = False             # was previous tick a downbeat?
    # Anticipation tracking (fire-once guard)
    anticipation_fired_for: str | None = None   # section start_time we already fired anticipation for
    # Energy tracking (for trend calculation)
    energy_history: list[float] = field(default_factory=list)  # last N energy values (one per bar)
    # Cue ID counter
    cue_counter: int = 0
```

**State lifecycle:**
- State is created when a new deck appears in the `DeckMix` (a `WeightedCursor` with a player_number not seen before).
- State is reset when the track changes on a deck (detected via section_start_time jumping backward or label sequence breaking continuity).
- State is removed when a deck disappears from the `DeckMix` for a configurable number of consecutive ticks (default: 40 ticks = 1 second).

**Track change detection:** Layer 2 detects track changes by monitoring `current_section.start_time`. If the start_time jumps backward (new track loaded, playback restarted), all per-deck state is reset and an initial `section_change` cue fires with `from_label: "none"`.

## Error Handling

| Condition | Behavior |
|-----------|----------|
| Empty DeckMix (no cursors) | Return empty list. No state changes. |
| DeckMix with all weights 0.0 | Return empty list. Per-deck state is preserved (decks still tracked, just muted). |
| Cursor with no current_section | Skip this cursor. Log a warning (once per deck, not per tick). |
| Stale DeckMix (identical to previous) | Emit only continuous cues if a new bar was detected. No duplicate transition cues. |
| Section with bar_count = 0 | Use `expected_bar_count` for progress calculation. If both are 0, use time-based progress (SectionInfo.progress). |
| next_section is None | Do not fire `section_anticipation`. Only fire `section_change` when section label actually changes. |
| BPM = 0 | Skip bar-boundary detection for this tick. Emit no cues. Log warning. |
| Playback not playing | Emit no cues. Preserve state so cues resume correctly when playback restarts. |

## Testing Strategy

### Mock DeckMix Fixtures

Tests feed synthetic `DeckMix` objects to the `CueEngine` and assert on the output `CueEvent` list. No real audio, no bridge, no Layer 1 code.

**Fixture categories:**

1. **Single-section playback:** One section, progress 0.0 to 1.0 over N ticks. Verify `section_progress` fires on each bar boundary, `section_change` fires once at the start.

2. **Section transition:** Two sections (build -> drop). Ticks progress through the boundary. Verify exactly one `section_change` fires at the boundary with correct payload and intensity.

3. **Section anticipation:** A cursor with `next_section` set. Verify `section_anticipation` fires at the correct number of bars before the boundary, fires exactly once, and has the correct `upcoming_label`.

4. **Energy trajectory:** A cursor whose `current_features.energy` ramps from 0.3 to 0.9 over N bars. Verify `energy_level` cues report correct trend ("rising").

5. **Track change (state reset):** Simulate a track change by jumping section_start_time backward. Verify state is reset and a fresh `section_change` cue fires.

6. **Empty DeckMix:** Verify zero cues emitted, no errors.

7. **Paused playback:** Verify zero cues emitted while paused, state preserved, cues resume on play.

8. **Multi-deck preparation:** Two cursors in DeckMix, one at weight 1.0 and one at weight 0.0. Verify only the active deck produces cues. (Prepares for Phase 2 testing without implementing blend logic.)

9. **Fakeout handling:** A fakeout section followed by a build. Verify `section_change` carries `is_fakeout: true` and intensity follows the fakeout column.

10. **Configuration override:** Load a custom `cues.yaml` with different intensity values. Verify the cue engine uses the configured values, not hardcoded defaults.

### Test File Organization

```
tests/test_layer2/
    __init__.py
    conftest.py                # Shared fixtures: mock DeckMix builders, mock config
    test_cue_engine.py         # CueEngine.tick() integration tests
    test_deck_generator.py     # DeckCueGenerator.process() unit tests
    test_cue_config.py         # CueConfig loading and defaults
    test_intensity.py          # Transition intensity matrix and curve evaluation
```

## Design Decisions

### DD-01: Tick-based cue emission on bar boundaries (not every tick)

**Decision:** Continuous cues (`section_progress`, `energy_level`) fire once per bar (on downbeat), not on every tick.

**Rationale:** Firing 40 times per second would overwhelm Layer 3 with redundant data. Section progress and energy change meaningfully at bar boundaries, not at 25 ms granularity. Layer 3 can interpolate between bar-rate updates for smooth output.

**Alternative rejected:** Firing on every tick — rejected because it creates unnecessary processing load and the data doesn't change meaningfully at that rate for section-level cues. Beat-level cues (M8) will fire at higher rates when implemented.

### DD-02: Per-deck state model from day one

**Decision:** `CueEngine` maintains a `DeckCueGenerator` per deck, even though M3 only exercises single-deck.

**Rationale:** ADR-006 established that multi-deck infrastructure should exist from day one. Adding per-deck state later would require restructuring the entire state model. The overhead of tracking 1-4 deck states is negligible.

**Alternative rejected:** Single global state — rejected because it would need a full rewrite for Phase 2 multi-deck blending.

### DD-03: Stateful CueEngine class, not a pure function

**Decision:** The cue engine is a stateful class (`CueEngine`) rather than a pure function `(DeckMix) -> [CueEvent]`.

**Rationale:** Detecting transitions (section changes, bar boundaries) requires comparing the current tick's input to the previous tick's input. Storing this state explicitly in the engine is cleaner than threading previous-state through function arguments. The per-deck generators are also stateful for the same reason.

**Alternative rejected:** Pure function with external state — rejected because it complicates the API and pushes state management to the caller, violating Layer 2's encapsulation.

### DD-04: Intensity matrix in YAML config, not hardcoded

**Decision:** The transition intensity matrix is loaded from `config/cues.yaml`, not embedded in code.

**Rationale:** ADR-003 mandates all configuration in YAML. Intensity values are subjective and will need tuning after real-world testing. Making them data rather than code enables rapid iteration without code changes.

### DD-05: Anticipation fires once, not continuously

**Decision:** `section_anticipation` fires a single cue when the "N bars before" threshold is crossed, rather than firing on every bar during the anticipation window.

**Rationale:** Anticipation is a signal to Layer 3 to start a build-up effect. A single trigger is cleaner than a stream of "still anticipating" messages. Layer 3 can sustain the build-up effect for the configured duration internally. If Layer 3 needs progress within the anticipation window, it can derive it from `section_progress`.

**Alternative rejected:** Continuous anticipation cues — rejected because it adds complexity with little benefit. Layer 3 already has `section_progress` for ramping.

`[DECISION OPPORTUNITY]`: If Brach finds that a single anticipation trigger is insufficient for Layer 3, this could be changed to fire every bar within the anticipation window. My recommendation is to start with single-fire and revisit based on Layer 3's needs.

### DD-06: Track change detection via section_start_time regression

**Decision:** Layer 2 detects track changes by monitoring whether `current_section.start_time` jumps backward, rather than tracking a separate "track ID" field.

**Rationale:** The `TrackCursor` contract does not include a track identifier (fingerprint or rekordbox ID). Adding one would be a contract change with Layer 1. Instead, a backward jump in section start_time is a reliable proxy: it only happens when a new track loads (or the DJ loops back, which is rare for full section-level tracking). If the DJ seeks backward within a track, the section labels will still be consistent, so the state reset is harmless.

**Alternative rejected:** Adding a `track_id` field to `TrackCursor` — rejected because it's a contract change to Layer 1 and not needed for M3. Can be revisited if track change detection proves unreliable.

`[DECISION OPPORTUNITY]`: If Brach wants more robust track change detection, we could add `track_fingerprint: str` to `TrackCursor`. This would be a `[CONTRACT CHANGE]` to the L1->L2 contract. My recommendation is to defer this and see if the start_time heuristic is sufficient.

## Constraints

- Layer 2 MUST NOT import from `scue.layer1` except the contract types listed in TR-05.
- Layer 2 MUST NOT import from Layer 0 (bridge) or Layer 3 (effects).
- All configuration MUST live in `config/cues.yaml`. No hardcoded tuning values.
- CueEvent output MUST conform to the CueEvent contract in CONTRACTS.md (plus the proposed `deck_number` field).
- Section labels consumed from SectionInfo are: `intro`, `verse`, `build`, `drop`, `breakdown`, `fakeout`, `outro`. Unknown labels are treated as `verse` (mid-energy default) with a warning log.

## Out of Scope

- Beat-level cues (`beat`, `kick`, `snare`, `percussion_pattern_change`) — Milestone 8.
- Melodic/harmonic cues (`arp_start`, `arp_note`, `arp_end`, `riser`, `faller`, `stab`) — Milestone 8.
- Effect cues (`sweep`, `impact`) — Milestone 8 (impact requires beat-level coincidence detection).
- Mood cues (`mood_shift`) — Milestone 8 (needs cross-section mood comparison).
- Multi-deck blending (Phase 2 crossfade) — weight scaling infrastructure exists but blend logic is deferred.
- WebSocket broadcasting of cue events to the frontend — separate task after M3 core.
- REST API for cue configuration — can use YAML editing for M3.

## Edge Cases

- **Fakeout section:** `section_change` fires with `is_fakeout: true`. Intensity uses the fakeout column. `section_anticipation` also carries `is_fakeout: true` so Layer 3 can choose not to fully commit to a drop build.
- **Irregular phrase (bar_count != expected_bar_count):** `section_progress` reports actual `bars_total` (not expected). The `irregular_phrase` flag is passed through in the payload so Layer 3 can adjust pacing.
- **Very short section (< 2 bars):** Anticipation may not fire if the section is shorter than `bars_before`. This is correct behavior — there is nothing to anticipate.
- **DJ loops within a section:** Bar count may exceed `bars_total`. Progress is clamped to 1.0. No additional section_change fires.
- **Simultaneous section changes on multiple decks:** In Phase 1, only one deck has weight > 0, so this cannot occur. Infrastructure is prepared: in Phase 2, the higher-weighted deck's section_change takes priority.
- **First tick after engine creation:** All decks are "new." Each fires a `section_change` with `from_label: "none"`. This bootstraps the state correctly.

## Open Questions

No blocking open questions. All ambiguities are resolved with reasonable defaults flagged as `[DECISION OPPORTUNITY]` above.
