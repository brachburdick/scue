# Section: strata

## Purpose
Arrangement analysis engine. Produces structured arrangement formulas (per-stem energy, patterns, transitions) from track analysis data. Supports three analysis tiers (quick/standard/deep) and live real-time formula construction during DJ playback.

## Owned Paths
```
scue/layer1/strata/           — engine, models, storage, per_stem, patterns, energy, transitions, separation, live_analyzer
tests/test_layer1/test_strata_sources.py   — storage + source qualification tests
tests/test_layer1/test_strata_standard.py  — tier routing, stem separation, cross-stem transition tests
tests/test_layer1/test_strata_priors.py    — beat-grid prior and trust scoring tests
```

## Incoming Inputs
- **From analysis section:** `TrackAnalysis`, `Section`, `RGBWaveform` (from `layer1.models`)
- **From analysis section:** `TrackStore` (from `layer1.storage`) — track data access
- **From analysis section:** `DrumPattern` (from `layer1.detectors.events`) — M7 drum event data
- **From bridge section:** `PlayerState` (from `bridge.adapter`) — live playback state for `LiveStrataAnalyzer`

## Outgoing Outputs
- **Types:** `ArrangementFormula`, `StrataFormula`, `StrataRow`, `StemType`, `PatternType`, `AtomicEvent`, `TierConfig`
- **Classes:** `StrataEngine` (analysis orchestration), `StrataStore` (persistence), `LiveStrataAnalyzer` (real-time)
- **Functions:** `formula_to_dict()`, `formula_from_dict()` (serialization)
- **Constants:** `VALID_TIERS`, `VALID_SOURCES`, `DEFAULT_SOURCE`

## Consumers
- **server section:** `api/strata.py` imports `StrataStore`, `StrataEngine`, serialization functions
- **analysis section:** `tracking.py` imports `ArrangementFormula`, `LiveStrataAnalyzer` for live updates
- **analysis section:** `detectors/percussion_stem.py` imports `AtomicEvent`, `StemType` for drum event output

## Invariants
- Strata never imports from `tracking`, `analysis`, `enrichment`, `cursor`, or other layer1 subsystems.
- Strata never imports from `layer2`, `layer3`, `layer4`, `api`, or `main.py`.
- `StrataStore` and `StrataEngine` are stateless beyond their constructor args — no singletons, no globals.
- All tier configurations (quick/standard/deep) are defined in `engine.py`, not in external config.
- Arrangement formulas are persisted as JSON per-tier per-source in the strata directory.
- `LiveStrataAnalyzer` is instantiated per-player by `tracking.py` — it does not manage its own lifecycle.

## Allowed Dependencies
- `scue.layer1.models` — `TrackAnalysis`, `Section`, `RGBWaveform` (read-only types)
- `scue.layer1.storage` — `TrackStore` (data access)
- `scue.layer1.detectors.events` — `DrumPattern` (read-only type)
- `scue.bridge.adapter` — `PlayerState` (read-only type)
- Python stdlib, `numpy`, `scipy`, `librosa`, `demucs` (optional)
- **NOT:** other layer1 subsystems, layer2-4, api, config, main.py

## How to Verify
```bash
.venv/bin/python -m pytest tests/test_layer1/test_strata_sources.py tests/test_layer1/test_strata_standard.py tests/test_layer1/test_strata_priors.py -v
```
All strata tests must pass. Tests mock demucs availability and use synthetic audio fixtures.
