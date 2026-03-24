# Section: pipeline

## Purpose
Cue generation (Layer 2), effect engine (Layer 3), and hardware output (Layer 4). Currently skeleton code — these layers will be implemented in future milestones.

## Owned Paths
```
scue/layer2/            — cue generation (empty skeleton)
scue/layer2/generators/ — per-cue-type generators (empty)
scue/layer3/            — effect engine (empty skeleton)
scue/layer3/effects/    — effect implementations (empty)
scue/layer4/            — output adapters (empty skeleton)
scue/layer4/adapters/   — DMX/OSC/MIDI adapters (empty)
```

## Incoming Inputs
- **From analysis section:** `TrackCursor`, `MusicalEvent`, `Section`, `TrackAnalysis` (Layer 2 consumes)
- **From config:** Effects YAML, routing YAML, palette YAML, fixture profiles, venue config

## Outgoing Outputs
- **Layer 2 → Layer 3:** `CueEvent` stream (not yet defined)
- **Layer 3 → Layer 4:** `AbstractOutput` (not yet defined)
- **Layer 4 → hardware:** DMX frames, OSC packets, MIDI messages

## Invariants
- Layer N imports only from Layer N-1. No skipping, no reverse imports.
- Layer 2 has zero knowledge of effects or hardware.
- Layer 3 has zero knowledge of DMX, OSC, venues, or fixture addresses.
- Layer 4 never imports from Layer 1, 2, or 3 implementation details — only `AbstractOutput`.
- All configuration is YAML files in `config/`. No hardcoded values.

## Allowed Dependencies
- Each layer imports only from the layer directly below it
- `scue.config` for YAML-driven configuration
- Python stdlib + domain libraries (e.g., `python-rtmidi`, `sacn` for DMX)
- No `bridge`, `api`, or `frontend` imports

## How to Verify
```bash
# When tests exist:
.venv/bin/python -m pytest tests/test_layer2/ tests/test_layer3/ tests/test_layer4/ -v
```
Currently: verify only that skeleton files exist and no invalid imports are present.

## Split Criteria
This section splits into `cues`, `effects`, and `output` when:
- Each sub-layer has >500 LOC of implementation
- Each has its own test suite
- The CueEvent and AbstractOutput types are defined and stable
