# Layer 2 — Cue Generation

## What this layer does
Transforms `TrackCursor` snapshots from Layer 1 into a typed stream of `CueEvent` objects.
This layer knows everything about music. It knows **nothing** about lights, lasers, hardware, or visuals.

This is a **pure function**: `(TrackCursor) → list[CueEvent]`. No side effects.
No state beyond the current input. This makes it trivially testable.

## Key files
| File | Purpose |
|---|---|
| `cue_engine.py` | Main loop: receives TrackCursor ticks, calls all generators, merges output |
| `cue_types.py` | CueEvent + MusicalContext dataclasses (the Layer 2→3 contract) |
| `generators/section_cues.py` | section_change, section_anticipation, section_progress |
| `generators/rhythmic_cues.py` | beat, kick, snare, percussion_pattern_change |
| `generators/melodic_cues.py` | arp_*, riser, faller, stab |
| `generators/ambient_cues.py` | mood_shift, energy_level, impact (composite) |

## Implementation rules
- **NEVER import from layer3 or layer4.** This layer has zero knowledge of effects or hardware.
- Only import from layer1: the `TrackCursor` type and its contained types (from `scue.layer1.cursor`). Nothing else from layer1.
- Each generator in `generators/` handles one category of cues. Called independently; outputs are merged by `cue_engine.py`.
- `section_anticipation` fires N beats before an upcoming section change — uses `TrackCursor.next_section`.
- `impact` is a heuristic composite: fire when `section_change` to `drop` coincides with high-velocity `kick` + high `track_energy`.
- Cue priority determines drop order under load. See `docs/CONTRACTS.md` → CueEvent priority table.

## Tick rate
Layer 2 runs every beat (fed by the cursor's beat event injection) plus every 25ms tick.
Beat-synced cues fire on the beat event; continuous cues (energy_level, section_progress) fire on ticks.

## Testing
- Feed recorded TrackCursor sequences (from Layer 1 test fixtures) through Layer 2 and snapshot cue output.
- Validate cue timing against hand-annotated expected cue files.
- Use `tools/cue_visualizer.py` to visually inspect output against known tracks.
- Run: `python -m pytest tests/test_layer2/ -v`

## Input/output contracts
- Input: `docs/CONTRACTS.md` → "Layer 1 → Layer 2: TrackCursor"
- Output: `docs/CONTRACTS.md` → "Layer 2 → Layer 3: CueEvent stream"
