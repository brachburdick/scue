# Tasks: M3 Cue Stream (Layer 2, Section Cues Only)

## Dependency Graph

```
TASK-001 (Layer 2 models)
    |
    +---> TASK-002 (CueConfig + YAML loader)
    |         |
    |         +---> TASK-005 (DeckCueGenerator)
    |         |         |
    |         |         +---> TASK-006 (CueEngine orchestrator)
    |         |                   |
    |         |                   +---> TASK-008 (Integration tests)
    |         |
    |         +---> TASK-004 (Intensity evaluator)
    |                   |
    |                   +---> TASK-005
    |
    +---> TASK-003 (Test fixtures)
              |
              +---> TASK-005
              +---> TASK-006
              +---> TASK-008

TASK-007 (config/cues.yaml default file) — depends on TASK-002

TASK-009 (Layer 2 CLAUDE.md) — depends on TASK-006
```

**Parallel tracks:**
- Track A: TASK-001 -> TASK-002 -> TASK-004 -> TASK-005 -> TASK-006 -> TASK-008
- Track B: TASK-001 -> TASK-003 (can start as soon as TASK-001 is done)
- Track C: TASK-002 -> TASK-007 (config file, independent of code tasks)
- TASK-009 can be written after TASK-006

TASK-001 is the foundation. After it completes, TASK-002 and TASK-003 can run in parallel. After TASK-002, TASK-004 and TASK-007 can run in parallel. TASK-005 requires both TASK-003 and TASK-004.

## Tasks

### TASK-001: Define Layer 2 data models
- **Layer:** Layer 2
- **Estimated effort:** 15 min
- **Depends on:** none
- **Scope:**
  - `scue/layer2/__init__.py` (create)
  - `scue/layer2/models.py` (create)
- **Inputs:** CueEvent and MusicalContext contracts from `docs/CONTRACTS.md`; DeckState spec from `specs/feat-M3-cue-stream/spec.md`
- **Outputs:**
  - `scue/layer2/models.py` containing: `CueEvent`, `MusicalContext`, `DeckState` dataclasses
  - `scue/layer2/__init__.py` with public exports
- **Acceptance Criteria:**
  - [ ] `CueEvent` dataclass matches CONTRACTS.md plus `deck_number: int` field
  - [ ] `MusicalContext` dataclass matches CONTRACTS.md
  - [ ] `DeckState` dataclass matches spec (current_section_label, last_bar_in_section, anticipation_fired_for, energy_history, cue_counter)
  - [ ] All fields have type hints
  - [ ] Module imports successfully: `from scue.layer2.models import CueEvent, MusicalContext, DeckState`
  - [ ] All pre-existing tests pass
- **Context files:**
  - `docs/CONTRACTS.md` (CueEvent, MusicalContext definitions)
  - `specs/feat-M3-cue-stream/spec.md` (DeckState definition, CueEvent.deck_number addition)
  - `scue/layer1/models.py` (reference pattern for dataclass style)
- **Status:** [ ] Not started

### TASK-002: Implement CueConfig dataclass and YAML loader
- **Layer:** Layer 2
- **Estimated effort:** 20 min
- **Depends on:** TASK-001
- **Scope:**
  - `scue/layer2/config.py` (create)
  - `tests/test_layer2/__init__.py` (create)
  - `tests/test_layer2/test_cue_config.py` (create)
- **Inputs:** Configuration schema from spec; existing loader pattern in `scue/config/loader.py`
- **Outputs:**
  - `CueConfig`, `CurveConfig`, `AnticipationConfig`, `EnergyConfig` dataclasses
  - `load_cue_config(config_dir: Path) -> CueConfig` function
  - Test file validating loading, defaults, and override behavior
- **Acceptance Criteria:**
  - [ ] `load_cue_config()` loads from `config/cues.yaml` and returns a `CueConfig`
  - [ ] Missing file returns all defaults (no crash)
  - [ ] Partial YAML (e.g., only `anticipation` section) merges with defaults
  - [ ] `transition_intensity_overrides` parsed correctly from YAML nested dict
  - [ ] `section_intensity_curves` parsed into `CurveConfig` objects per section label
  - [ ] At least 6 tests covering: full load, missing file, partial config, bad values, curve parsing, intensity matrix parsing
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-M3-cue-stream/spec.md` (Configuration Schema section)
  - `scue/config/loader.py` (existing pattern to follow)
  - `config/bridge.yaml`, `config/server.yaml` (YAML structure examples)
- **Status:** [ ] Not started

### TASK-003: Create mock DeckMix test fixtures
- **Layer:** Layer 2 (test infrastructure)
- **Estimated effort:** 20 min
- **Depends on:** TASK-001
- **Scope:**
  - `tests/test_layer2/conftest.py` (create)
- **Inputs:** DeckMix/TrackCursor/SectionInfo types from `scue/layer1/models.py`
- **Outputs:** pytest fixtures and builder functions for creating synthetic DeckMix objects:
  - `make_section_info(label, start, end, progress, ...)` — factory with sensible defaults
  - `make_beat_position(beat_in_bar, bar_in_section, bpm, ...)` — factory
  - `make_cursor(section_label, progress, energy, ...)` — builds a complete TrackCursor
  - `make_deck_mix(cursors_with_weights)` — wraps cursors in WeightedCursor + DeckMix
  - `build_to_drop_sequence(n_ticks)` — returns a list of DeckMix snapshots progressing through a build->drop transition
  - `single_section_sequence(label, n_bars, bpm)` — returns a list of DeckMix snapshots for one section
- **Acceptance Criteria:**
  - [ ] `make_cursor()` produces a valid `TrackCursor` with all required fields
  - [ ] `make_deck_mix()` produces a valid `DeckMix` with correct weight structure
  - [ ] `build_to_drop_sequence()` returns a sequence where section changes at the correct tick
  - [ ] All factories are importable from `conftest.py` in test files
  - [ ] All pre-existing tests pass
- **Context files:**
  - `scue/layer1/models.py` (DeckMix, TrackCursor, SectionInfo, BeatPosition, PlaybackState, TrackCursorFeatures)
  - `specs/feat-M3-cue-stream/spec.md` (Testing Strategy section)
- **Status:** [ ] Not started

### TASK-004: Implement intensity evaluator (transition matrix + section curves)
- **Layer:** Layer 2
- **Estimated effort:** 20 min
- **Depends on:** TASK-002
- **Scope:**
  - `scue/layer2/intensity.py` (create)
  - `tests/test_layer2/test_intensity.py` (create)
- **Inputs:** `CueConfig` with transition intensity matrix and section curves
- **Outputs:**
  - `get_transition_intensity(config, from_label, to_label) -> float` — looks up the intensity matrix
  - `evaluate_section_curve(config, section_label, progress) -> float` — evaluates the intensity curve for a section type at a given progress
  - `compute_energy_trend(energy_history, lookback, threshold) -> str` — returns "rising" | "falling" | "stable"
- **Acceptance Criteria:**
  - [ ] `get_transition_intensity("build", "drop")` returns 1.0 with default config
  - [ ] `get_transition_intensity("unknown", "unknown")` returns the default (0.5)
  - [ ] `evaluate_section_curve("build", 0.0)` returns base value (~0.3)
  - [ ] `evaluate_section_curve("build", 1.0)` returns peak value (~1.0)
  - [ ] `evaluate_section_curve("drop", 0.5)` returns flat high (~0.9)
  - [ ] `compute_energy_trend([0.3, 0.4, 0.5, 0.6], 4, 0.05)` returns "rising"
  - [ ] `compute_energy_trend([0.6, 0.6, 0.6, 0.6], 4, 0.05)` returns "stable"
  - [ ] All curve types (flat, linear, exponential, inverse_exponential) tested
  - [ ] At least 10 tests
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-M3-cue-stream/spec.md` (Intensity Mapping, Section Progress Intensity Curves sections)
  - `scue/layer2/config.py` (CueConfig, CurveConfig)
- **Status:** [ ] Not started

### TASK-005: Implement DeckCueGenerator (per-deck cue generation)
- **Layer:** Layer 2
- **Estimated effort:** 30 min
- **Depends on:** TASK-003, TASK-004
- **Scope:**
  - `scue/layer2/generator.py` (create)
  - `tests/test_layer2/test_deck_generator.py` (create)
- **Inputs:** `TrackCursor`, `DeckState`, `CueConfig`, intensity evaluator functions
- **Outputs:**
  - `DeckCueGenerator` class with `process(cursor, wall_time) -> list[CueEvent]`
  - Handles: section_change detection, section_anticipation, section_progress on bar boundaries, energy_level on bar boundaries
  - State management: creates/resets/updates `DeckState`
- **Acceptance Criteria:**
  - [ ] Section change detection: fires `section_change` exactly once when `current_section.label` differs from stored state
  - [ ] Section anticipation: fires `section_anticipation` exactly once when `bar_in_section >= bars_total - anticipation.bars_before` and `next_section` is not None
  - [ ] Section progress: fires `section_progress` on each new bar boundary (bar_in_section incremented)
  - [ ] Energy level: fires `energy_level` on each new bar boundary with correct trend
  - [ ] Track change detection: state resets when `section_start_time` jumps backward
  - [ ] No cues emitted when `playback_state.is_playing` is False
  - [ ] No cues emitted when BPM is 0
  - [ ] Fakeout sections produce correct `is_fakeout` flag in payloads
  - [ ] CueEvent IDs are unique and monotonically increasing per deck
  - [ ] At least 12 tests covering all cue types and edge cases
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-M3-cue-stream/spec.md` (Processing Model, State Management, Error Handling, Edge Cases)
  - `scue/layer2/models.py` (CueEvent, DeckState)
  - `scue/layer2/intensity.py` (intensity evaluator functions)
  - `scue/layer2/config.py` (CueConfig)
  - `tests/test_layer2/conftest.py` (mock DeckMix builders)
- **Status:** [ ] Not started

### TASK-006: Implement CueEngine orchestrator
- **Layer:** Layer 2
- **Estimated effort:** 20 min
- **Depends on:** TASK-005
- **Scope:**
  - `scue/layer2/engine.py` (create)
  - `tests/test_layer2/test_cue_engine.py` (create)
- **Inputs:** `DeckMix`, `CueConfig`, `DeckCueGenerator`
- **Outputs:**
  - `CueEngine` class with `tick(deck_mix, wall_time) -> list[CueEvent]`
  - Manages per-deck `DeckCueGenerator` instances (create, route, cleanup)
  - Weight scaling of cue intensities
  - Cue filtering (drop cues below `min_cue_intensity`)
- **Acceptance Criteria:**
  - [ ] Creates a `DeckCueGenerator` for each new deck in the DeckMix
  - [ ] Routes each `WeightedCursor` to the correct per-deck generator
  - [ ] Scales cue intensity by deck weight (intensity * weight)
  - [ ] Drops cues with intensity < `min_cue_intensity` after weight scaling
  - [ ] Returns empty list for empty DeckMix
  - [ ] Returns empty list when all weights are 0.0
  - [ ] Cleans up generators for decks that have been absent for N ticks
  - [ ] Multi-deck: two cursors, one at weight 1.0 and one at 0.0, only active deck produces cues
  - [ ] At least 8 tests
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-M3-cue-stream/spec.md` (Processing Model, Entry Point Signature)
  - `scue/layer2/generator.py` (DeckCueGenerator)
  - `scue/layer2/config.py` (CueConfig)
  - `tests/test_layer2/conftest.py` (mock DeckMix builders)
- **Status:** [ ] Not started

### TASK-007: Create default config/cues.yaml
- **Layer:** Configuration
- **Estimated effort:** 10 min
- **Depends on:** TASK-002
- **Scope:**
  - `config/cues.yaml` (create)
- **Inputs:** Configuration schema from spec
- **Outputs:** Complete `cues.yaml` with all default values filled in (full transition intensity matrix, all section curves, all thresholds)
- **Acceptance Criteria:**
  - [ ] File is valid YAML (parseable by `yaml.safe_load`)
  - [ ] Contains complete `transition_intensity` section with all 8x7 label pair overrides from spec
  - [ ] Contains all 7 `section_intensity_curves` entries (intro, verse, build, drop, breakdown, fakeout, outro)
  - [ ] Contains `anticipation`, `energy`, and general settings
  - [ ] `load_cue_config("config")` successfully loads this file and produces correct `CueConfig`
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-M3-cue-stream/spec.md` (Configuration Schema, Intensity Mapping tables)
  - `config/bridge.yaml`, `config/server.yaml` (YAML format examples)
- **Status:** [ ] Not started

### TASK-008: Integration tests — full CueEngine with realistic sequences
- **Layer:** Layer 2 (test)
- **Estimated effort:** 25 min
- **Depends on:** TASK-006
- **Scope:**
  - `tests/test_layer2/test_integration.py` (create)
- **Inputs:** `CueEngine`, mock DeckMix sequences from conftest
- **Outputs:** Integration tests that exercise full multi-bar sequences through the engine
- **Acceptance Criteria:**
  - [ ] Test: Full build->drop transition sequence (8 bars build + 8 bars drop). Verify: 1 anticipation cue, 1 section_change cue, N section_progress cues, N energy_level cues. Correct timing.
  - [ ] Test: Full track playback (intro->verse->build->drop->breakdown->build->drop->outro). Verify: correct number of section_change cues (7), no duplicates.
  - [ ] Test: Track change mid-playback. Verify: state reset, fresh section_change with from_label "none".
  - [ ] Test: Paused then resumed playback. Verify: no cues during pause, correct resume.
  - [ ] Test: Fakeout section in sequence. Verify: is_fakeout flag propagated.
  - [ ] Test: Custom config overrides change output intensity values.
  - [ ] At least 6 integration tests
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-M3-cue-stream/spec.md` (Testing Strategy)
  - `scue/layer2/engine.py` (CueEngine)
  - `tests/test_layer2/conftest.py` (sequence builders)
- **Status:** [ ] Not started

### TASK-009: Write Layer 2 CLAUDE.md
- **Layer:** Documentation
- **Estimated effort:** 10 min
- **Depends on:** TASK-006
- **Scope:**
  - `scue/layer2/CLAUDE.md` (create)
- **Inputs:** Final implementation structure from previous tasks
- **Outputs:** Layer-specific CLAUDE.md following the pattern of `scue/layer1/CLAUDE.md`
- **Acceptance Criteria:**
  - [ ] Describes what Layer 2 does
  - [ ] Lists key files and their purposes
  - [ ] Documents input contract (DeckMix) and output contract (CueEvent)
  - [ ] Lists testing commands
  - [ ] References domain knowledge and config files
  - [ ] All pre-existing tests pass
- **Context files:**
  - `scue/layer1/CLAUDE.md` (pattern to follow)
  - `specs/feat-M3-cue-stream/spec.md`
- **Status:** [ ] Not started
