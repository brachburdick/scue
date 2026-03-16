# Layer 3 — Effect Engine

## What this layer does
Maps `CueEvent` objects from Layer 2 to abstract visual/lighting instructions (`FixtureOutput`).
This layer knows about visual concepts (color, brightness, movement, speed).
It knows **nothing** about specific hardware, DMX channels, pixel addresses, or laser ILDA frames.

## Sub-components
| Sub-layer | File | Purpose |
|---|---|---|
| 3A — Effect Library | `effects/` | Parameterized generator functions: (time, params) → channel values |
| 3B — Routing Table | `routing.py` | Maps cue types + conditions to effect instances on fixture groups |
| 3C — Blending System | `blender.py` | HTP/LTP priority merging of overlapping effects |
| 3D — Palette Engine | `palette.py` | Current color palette, updated by mood_shift / energy_level cues |

## Key files
| File | Purpose |
|---|---|
| `effect_engine.py` | Main loop: receives CueEvents, matches routes, runs effects, blends, outputs |
| `models.py` | FixtureOutput dataclass (the Layer 3→4 contract) |
| `routing.py` | Loads routing YAML from `config/routing/`; matches CueEvents to routes |
| `blender.py` | HTP (brightness), LTP (color/position) blending; effect lifetime/fade-out |
| `palette.py` | Palette management; resolves `"palette.accent"` bindings at render time |
| `effects/base.py` | Abstract base effect class |
| `effects/pulse.py` | Beat-reactive brightness pulse (attack/sustain/decay) |
| `effects/chase.py` | Sequential activation across fixture positions |
| `effects/static.py` | Solid color/brightness (baseline) |

## Implementation rules
- **NEVER import from layer4.** This layer does not know about DMX, OSC, MIDI, or venue layout.
- Only import from layer2: the `CueEvent` type (from `scue.layer2.cue_types`). Nothing else from layer2.
- Effects are **generators**: `(time: float, params: dict) → dict[str, float]` (channel name → 0.0–1.0).
- Effect definitions are in YAML (`config/effects/`). Python implementations in `effects/`. YAML-first — only add Python for behaviors that can't be parameterized.
- The routing table references fixture groups by name (e.g. `"pars_all"`). Never by hardware address.
- HTP for brightness/intensity. LTP for color and position.
- A `section_change` cue can flush all active effects (configurable per route).

## Abstract channel names
`brightness`, `color_r`, `color_g`, `color_b`, `color_h`, `color_s`, `color_v`,
`position_x`, `position_y`, `beam_width`, `strobe_rate`, `visual_trigger`

## Testing
- Unit test each effect generator with synthetic time sequences.
- Unit test blending system with overlapping effects at known priorities.
- Integration: feed Layer 2 cue streams in, capture abstract output.
- Use `tools/venue_preview.py` for 2D visual QA without hardware.
- Run: `python -m pytest tests/test_layer3/ -v`

## Input/output contracts
- Input: `docs/CONTRACTS.md` → "Layer 2 → Layer 3: CueEvent stream"
- Output: `docs/CONTRACTS.md` → "Layer 3 → Layer 4: AbstractOutput"
