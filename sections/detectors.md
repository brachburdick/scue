# Section: detectors

## Purpose
Pluggable musical event detection (percussion, tonal, flow-model, section boundaries, snap correction). Produces `MusicalEvent` and `DrumPattern` data from audio analysis features. Includes the eval harness for detector accuracy measurement.

## Owned Paths
```
scue/layer1/detectors/             — events, percussion_heuristic, percussion_rf, percussion_stem,
                                     tonal, features, flow_model, sections, snap
scue/layer1/eval_detectors.py      — detector eval harness
config/detectors.yaml              — detector strategy selection, parameters, section priors
tests/test_layer1/test_flow_model.py
tests/test_layer1/test_snap.py
tests/test_layer1/test_percussion_stem.py
```

## Incoming Inputs
- **From analysis section:** `TrackAnalysis`, `Section`, `RGBWaveform` (consumed by feature extraction and section-aware detectors)
- **From strata section:** `AtomicEvent`, `StemType` (type definitions reused by percussion_stem detector output)
- **From config:** `config/detectors.yaml` (strategy selection, thresholds, priors)
- **From audio:** Librosa feature arrays (chromagram, onset strength, spectral features)

## Outgoing Outputs
- **Types:** `MusicalEvent`, `DrumPattern`, `EventType`, `DetectorResult`
- **Functions:** `run_detectors()`, `eval_detector_accuracy()`
- **Data:** `events.py` defines the canonical event taxonomy consumed by Layer 2

## Consumers
- **analysis section:** `analysis.py` calls `run_detectors()` during offline analysis
- **strata section:** `percussion_stem.py` output types align with strata's `AtomicEvent`
- **server section:** `api/tracks.py` serves detector results via REST
- **pipeline section:** Layer 2 will consume `MusicalEvent` stream (future)

## Invariants
- Detectors never import from `tracking`, `storage`, `cursor`, `enrichment`, or other layer1 subsystems.
- Detectors never import from `layer2`, `layer3`, `layer4`, `api`, or `main.py`.
- Each detector is a standalone module — no detector imports another detector (except via `events.py` types).
- Strategy selection is config-driven (`detectors.yaml`), not hardcoded.
- `eval_detectors.py` is the only file that imports multiple detectors — it's the eval harness, not production code.

## Allowed Dependencies
- `scue.layer1.models` — `TrackAnalysis`, `Section`, `RGBWaveform` (read-only types)
- `scue.layer1.strata.models` — `AtomicEvent`, `StemType` (type definitions only)
- `scue.config` — detector config loading
- Python stdlib, `numpy`, `librosa`, `scipy`, `sklearn`
- **NOT:** other layer1 subsystems, layer2-4, api, bridge, main.py

## How to Verify
```bash
.venv/bin/python -m pytest tests/test_layer1/test_flow_model.py tests/test_layer1/test_snap.py tests/test_layer1/test_percussion_stem.py -v
```
Tests use synthetic audio fixtures and mock feature arrays — no real audio files required.
