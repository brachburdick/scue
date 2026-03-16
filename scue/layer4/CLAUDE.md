# Layer 4 — Output & Hardware

## What this layer does
Translates abstract channel values into hardware-specific signals (DMX, OSC, MIDI).
Manages venue configuration (fixture profiles, spatial positions, group assignments).

## Implementation rules
- Fixture profiles are YAML (config/fixtures/). They map abstract channel names to protocol-specific channel offsets and value ranges.
- Venue files are YAML (config/venues/). They define fixture instances, DMX addresses, positions, and group memberships.
- Protocol adapters in adapters/ are independent. Adding a new protocol requires zero changes to Layers 0–3.
- DMX output via OLA or python-sacn. Refresh at ~44Hz.
- OSC output via python-osc. Address mapping is per-target-software config.
- User overrides (override.py) inject at highest priority in the blending system. They always win.
- NEVER import from layer1, layer2, or layer3 implementation details. This layer only consumes AbstractOutput objects.

## Testing
- Run: `python -m pytest tests/test_layer4/ -v`
- Virtual venue visualizer: tools/venue_preview.py
- Test with mock protocol receivers before real hardware.

## Input contract
- Input: docs/CONTRACTS.md → "Layer 3 → Layer 4: AbstractOutput"

## Domain knowledge
For DMX/Art-Net/sACN, see docs/domains/dmx-artnet-sacn.md
For OSC and MIDI, see docs/domains/osc-midi.md
For laser safety and ILDA, see docs/domains/laser-safety.md
For network topology, see docs/domains/live-networking.md
