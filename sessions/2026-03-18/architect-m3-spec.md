# Session Summary: TASK-M3-SPEC

## Role
Architect

## Objective
Produce a complete feature spec and atomized task breakdown for Milestone 3 — Cue Stream (Layer 2, section cues only). Define the transformation of DeckMix (Layer 1 output) into a CueEvent stream (Layer 2 output).

## Status
COMPLETE

## Work Performed
- Read all required context: AGENT_BOOTSTRAP, COMMON_RULES, ARCHITECT preamble, LEARNINGS, handoff packet, ARCHITECTURE (Layer 2 section), CONTRACTS, DECISIONS, MILESTONES, Layer 1 models/cursor/tracking source, config YAML files, config loader pattern
- Designed the Layer 2 processing model: tick-based at 40 Hz (ADR-002), with continuous cues firing on bar boundaries
- Defined 4 M3 cue types: `section_change`, `section_anticipation`, `section_progress`, `energy_level`
- Designed the transition intensity matrix (8x7 from/to label pairs) with EDM-informed defaults
- Designed section progress intensity curves (7 section types with appropriate curve shapes)
- Designed per-deck state model (`DeckState`) for transition detection and deduplication
- Designed `CueEngine` + `DeckCueGenerator` class architecture
- Specified complete YAML configuration schema (`config/cues.yaml`)
- Defined error handling for 8 edge cases
- Designed testing strategy with 10 fixture categories
- Atomized implementation into 9 tasks with dependency graph and parallel tracks
- Wrote `specs/feat-M3-cue-stream/spec.md` and `specs/feat-M3-cue-stream/tasks.md`

## Files Changed
- `specs/feat-M3-cue-stream/spec.md` — Created. Full feature spec for M3 Cue Stream.
- `specs/feat-M3-cue-stream/tasks.md` — Created. 9 atomized tasks with dependency graph.

## Interfaces Added or Modified
- Proposed `[CONTRACT CHANGE]`: Add `deck_number: int` field to `CueEvent` dataclass (non-breaking, additive). Enables Layer 3 to route cues per deck in Phase 2.
- New interface: `CueEngine.tick(deck_mix: DeckMix, wall_time: float) -> list[CueEvent]`
- New interface: `DeckCueGenerator.process(cursor: TrackCursor, wall_time: float) -> list[CueEvent]`
- New interface: `load_cue_config(config_dir: Path) -> CueConfig`
- New interface: `get_transition_intensity(config: CueConfig, from_label: str, to_label: str) -> float`
- New interface: `evaluate_section_curve(config: CueConfig, section_label: str, progress: float) -> float`
- New interface: `compute_energy_trend(energy_history: list[float], lookback: int, threshold: float) -> str`

## Decisions Made
- **DD-01: Bar-rate continuous cues (not tick-rate):** Section_progress and energy_level fire once per bar on downbeat, not every tick. Reduces Layer 3 load; data doesn't change meaningfully at 40 Hz for section-level info. Alternative: per-tick firing — rejected for excessive redundancy.
- **DD-02: Per-deck state from day one:** CueEngine maintains a DeckCueGenerator per deck even in Phase 1. Follows ADR-006. Alternative: single global state — rejected because it requires full rewrite for Phase 2.
- **DD-03: Stateful CueEngine class:** State for transition detection stored in the engine, not threaded through function args. Alternative: pure function with external state — rejected for complexity.
- **DD-04: Intensity matrix in YAML:** All transition intensities are configurable data, not code. Follows ADR-003.
- **DD-05: Single-fire anticipation:** section_anticipation fires once at the N-bars-before threshold, not continuously. Layer 3 can use section_progress for ramping.
- **DD-06: Track change via start_time regression:** No new contract field needed. Backward jump in section start_time indicates track change. Alternative: add track_fingerprint to TrackCursor — deferred as a contract change.

## Scope Violations
None. All work was within the specified scope (creating spec and tasks files, reading existing source code).

## Remaining Work
None. All acceptance criteria met.

## Blocked On
None.

## Missteps
None. All context files were found at expected paths and read successfully.

## Learnings
None specific to Layer 2 yet — this was a design session, no implementation surprises.
