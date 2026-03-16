# Layer 2 — Cue Generation

## What this layer does
Transforms a DeckMix (weighted TrackCursors, one per active deck) into a single blended stream of CueEvent objects.
This layer knows about music. It knows nothing about lights, lasers, or visuals.

## Implementation rules
- Entry point signature: (DeckMix) → list[CueEvent]. Internally: per-cursor generation → cue mixer.
- Per-cursor generation is a pure function: (TrackCursor) → list[CueEvent]. No side effects, no state.
- Cue mixer is a pure function: merges per-deck cue streams using deck weights from the DeckMix.
- Instantaneous cues (kick, snare, etc.): intensity scaled by deck weight. Drop below threshold (0.1).
- Continuous cues (riser, energy_level, etc.): values interpolated between decks by weight.
- Section cues: fire from the higher-weighted deck only. No duplicate transitions during blends.
- Phase 1 (master-only): DeckMix has one cursor at weight 1.0, mixer passes through unchanged.
- Cue type taxonomy is defined in cue_types.py. Adding a new cue type requires updating CONTRACTS.md.
- Each generator in generators/ handles one category of cues. They are called independently per cursor.
- The `impact` cue is a composite heuristic, not a raw detector output.
- NEVER import from layer3 or layer4. This layer has zero knowledge of effects or hardware.

## Testing
- Run: `python -m pytest tests/test_layer2/ -v`
- Single-deck tests: DeckMix with one cursor at weight 1.0
- Multi-deck blend tests: two cursors at varying weights (1.0/0.0, 0.5/0.5, 0.0/1.0)
- Use tools/cue_visualizer.py to visually inspect cue output against known tracks.

## Input/output contracts
- Input: docs/CONTRACTS.md → "Layer 1 → Layer 2: DeckMix"
- Output: docs/CONTRACTS.md → "Layer 2 → Layer 3: CueEvent stream"
