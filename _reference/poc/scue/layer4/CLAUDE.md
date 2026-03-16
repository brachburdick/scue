# Layer 4 — Output & Hardware

## What this layer does
Translates abstract `FixtureOutput` channel values from Layer 3 into hardware-specific
control signals (DMX, OSC, MIDI), and manages venue/fixture configuration.

## Sub-components
| Sub-layer | Purpose |
|---|---|
| 4A — Venue Config | Fixture definitions, instances, DMX addresses, positions, groups |
| 4B — Protocol Adapters | DMX/Art-Net/sACN, OSC, MIDI, ILDA (future) |
| 4C — User Override UI | Real-time mute/solo/manual triggers from browser or MIDI controller |

## Key files
| File | Purpose |
|---|---|
| `venue.py` | Load and validate venue YAML files from `config/venues/` |
| `fixture_profile.py` | Fixture definitions: abstract channels → protocol-specific offsets and value ranges |
| `output_manager.py` | Coordinates all adapters; routes per-fixture values to the right adapter |
| `override.py` | User override state: muted routes, solo groups, manual cues, master faders |
| `adapters/base.py` | Abstract adapter interface |
| `adapters/dmx.py` | DMX512 via OLA or python-sacn; packs universe frames at ~44Hz |
| `adapters/osc.py` | OSC output to Resolume, TouchDesigner, VDMX, etc. |
| `adapters/midi.py` | MIDI CC / note-on output |

## Implementation rules
- **NEVER import from layer1, layer2, or layer3 internals.** Only consume `FixtureOutput` objects.
- Fixture profiles map abstract channel names to protocol-specific offsets and byte ranges.
- Venue files are YAML (`config/venues/`). Groups are defined by the user based on physical layout.
- Protocol adapters are independent — adding a new protocol requires zero changes to Layers 1–3.
- User overrides are injected at the highest priority in Layer 3's blending system. They always win.
- DMX output at ~44Hz (DMX refresh rate). OSC as triggered by cues.

## Fixture position model
Each fixture has a normalized `position: { x: 0.0–1.0, y: 0.0–1.0 }` in the venue.
Layer 3 effects that use the `position` abstract channel (e.g. chase) sweep across
fixture positions in order. Layer 4 translates the 0.0–1.0 position to
hardware-specific pan/tilt values via the fixture profile.

## Testing
- Unit test fixture profile translation: abstract channels → correct DMX byte values.
- Unit test protocol adapters against mock receivers (local listener socket).
- Use `tools/venue_preview.py` for 2D venue visualization without real hardware.
- Test with real hardware only after virtual venue tests pass.
- Run: `python -m pytest tests/test_layer4/ -v`

## Input contract
- Input: `docs/CONTRACTS.md` → "Layer 3 → Layer 4: AbstractOutput"
