# Section: analysis

## Purpose
Offline audio analysis (section detection, beat tracking, waveform generation, event detection), live playback tracking, track storage, and USB scanning. The core domain logic of SCUE, excluding arrangement analysis (see `strata` section).

## Owned Paths
```
scue/layer1/            — models, storage, tracking, analysis, enrichment, fingerprint, etc.
scue/layer1/detectors/  — pluggable M7 event detectors (percussion, tonal, features, etc.)
tests/test_layer1/      — all analysis + detector tests (excluding test_strata_*)
```

**Excludes:** `scue/layer1/strata/` and `tests/test_layer1/test_strata_*` (owned by `strata` section).

## Incoming Inputs
- **From bridge section:** `DeviceInfo`, `PlayerState` types (consumed by `tracking.py`)
- **From strata section:** `ArrangementFormula`, `LiveStrataAnalyzer` (consumed by `tracking.py` for live updates)
- **From config:** `UsbConfig` from `scue/config/loader.py`
- **From filesystem:** Audio files (MP3, WAV, FLAC), Pioneer USB exports (ANLZ files, exportLibrary.db)

## Outgoing Outputs
- **Types:** `TrackAnalysis`, `TrackCursor`, `Section`, `RGBWaveform`, `MusicalEvent`, `DrumPattern`
- **Storage:** JSON analysis files (source of truth), SQLite cache (derived)
- **Callbacks:** `PlaybackTracker` accepts `on_player_update` / `on_track_loaded` from bridge adapter
- **Functions:** `run_analysis()`, `run_reanalysis_pass()`, `compute_fingerprint()`

## Invariants
- JSON analysis files are the source of truth. SQLite is a derived cache only.
- Pioneer-sourced data is never overwritten by SCUE-derived data; divergence is logged.
- Analysis never imports from `layer2`, `layer3`, `layer4`, or `api`.
- `TrackStore` and `TrackCache` are passed in (dependency injection), not created internally.
- Section boundaries are always clamped to [0, track_duration].
- Beat counting uses half-open intervals (downbeat count = bar count + 1).

## Allowed Dependencies
- `scue.bridge.adapter` — types only (DeviceInfo, PlayerState)
- `scue.layer1.strata` — `ArrangementFormula`, `LiveStrataAnalyzer` (consumed by tracking.py)
- `scue.config` — UsbConfig
- Python stdlib, `librosa`, `allin1_mlx`, `ruptures`, `numpy`, `rbox`, `pyrekordbox`
- No `layer2`, `layer3`, `layer4`, `api` imports

## How to Verify
```bash
.venv/bin/python -m pytest tests/test_layer1/ --ignore-glob='*strata*' -v
```
Tests use local audio fixtures (gitignored) and synthetic generators.
