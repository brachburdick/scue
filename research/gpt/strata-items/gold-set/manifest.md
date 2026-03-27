# Strata Gold Set — Electronic Music Structure Reference

## Purpose

A small, canonical set of 15-25 tracks with human-reviewed arrangement annotations.
Used as the standard evaluation benchmark for all Strata experiments.

## Selection Criteria

Tracks should cover:
- Mixed energy profiles (low-energy ambient → high-energy peak-time)
- Build, drop, breakdown, fakeout, and fill examples
- A subset with Pioneer metadata captures (phrase analysis, beat grid, waveform)
- At least 3 subgenres (e.g., house, techno, drum & bass, trance)
- Short (3-4 min) and long (7-10 min) tracks
- Simple (intro-drop-outro) and complex (multiple breakdowns, tempo changes) structures

## Annotation Format

Each track gets a JSON file in `annotations/` matching this schema:

```json
{
  "fingerprint": "sha256_of_audio",
  "sections": [
    {"label": "intro", "start": 0.0, "end": 32.5},
    {"label": "build", "start": 32.5, "end": 64.0}
  ],
  "transitions": [
    {"type": "energy_shift", "timestamp": 32.5},
    {"type": "drop_impact", "timestamp": 64.0}
  ],
  "active_layers_per_section": [
    ["drums"],
    ["drums", "bass", "other"]
  ],
  "notes": "Classic 4-on-the-floor house track, clean structure."
}
```

This matches the `GoldAnnotation` dataclass in `scue/layer1/strata/evaluation.py`.

## Section Label Vocabulary

Use these labels (matching Pioneer phrase kinds + SCUE extensions):
- `intro`, `verse`, `chorus`, `bridge`, `breakdown`, `build`, `drop`, `outro`

## Transition Type Vocabulary

Use TransitionType values:
- `layer_enter`, `layer_exit`, `pattern_change`, `fill`, `energy_shift`, `breakdown`, `drop_impact`

## Layer Vocabulary

Use stem names:
- `drums`, `bass`, `vocals`, `other` (standard tier stems)
- `mix` (live tier single-stem)

## Current Inventory

| # | Fingerprint | Title | Genre | Duration | Pioneer Data | Status |
|---|-------------|-------|-------|----------|--------------|--------|
| — | (to be populated) | | | | | |

## Versioning

- Created: 2026-03-26
- Last modified: 2026-03-26
- Annotation protocol version: 1.0
