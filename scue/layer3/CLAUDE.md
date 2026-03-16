# Layer 3 — Effect Engine

## What this layer does
Maps CueEvents to abstract visual output (brightness, color, position, etc.).
This layer knows about visual concepts. It knows nothing about specific hardware or protocols.

## Implementation rules
- Effects are parameterized generators: (time, parameters) → channel values. Defined in YAML (config/effects/) and implemented in effects/.
- The routing table (config/routing/) maps cue types to effect instances on target groups. It is user-editable YAML.
- Blending: HTP for brightness, LTP for color/position. Implemented in blender.py.
- Palettes are in config/palettes/. The mood engine in palette.py selects/interpolates palettes based on ambient cues.
- Output is per-fixture-group abstract channel values. NEVER output DMX values, protocol bytes, or hardware-specific data.
- NEVER import from layer4. This layer does not know about DMX, OSC, or venue configuration.
- New effects should be YAML-first. Only add Python effect implementations for behaviors that can't be expressed as parameterized built-in types.

## Testing
- Run: `python -m pytest tests/test_layer3/ -v`
- Use the 2D preview grid (tools/venue_preview.py) to visualize output without hardware.

## Input/output contracts
- Input: docs/CONTRACTS.md → "Layer 2 → Layer 3: CueEvent stream"
- Output: docs/CONTRACTS.md → "Layer 3 → Layer 4: AbstractOutput"

## Domain knowledge
For DMX/Art-Net/sACN, see docs/domains/dmx-artnet-sacn.md
For laser safety and ILDA, see docs/domains/laser-safety.md
