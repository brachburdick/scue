# Section: analysis

## Purpose
Core audio analysis pipeline (section detection, beat tracking, waveform generation), live playback tracking, track storage, and enrichment. The central domain logic of SCUE — offline analysis orchestration and real-time cursor management.

## Owned Paths
```
scue/layer1/analysis.py       — run_analysis() pipeline orchestration
scue/layer1/models.py         — TrackAnalysis, Section, TrackCursor, RGBWaveform, MusicalEvent, etc.
scue/layer1/cursor.py         — TrackCursor construction from bridge state
scue/layer1/storage.py        — TrackStore, TrackCache, JSON persistence
scue/layer1/tracking.py       — PlaybackTracker, live cursor, strata integration
scue/layer1/waveform.py       — RGB waveform generation from audio
scue/layer1/enrichment.py     — Pioneer metadata enrichment
scue/layer1/divergence.py     — Pioneer vs SCUE divergence logging
scue/layer1/fingerprint.py    — audio fingerprint computation
scue/layer1/__init__.py
tests/test_layer1/test_analysis.py
tests/test_layer1/test_cursor.py
tests/test_layer1/test_enrichment.py
tests/test_layer1/test_tracking.py
tests/test_layer1/test_storage.py
tests/test_layer1/test_divergence.py
tests/test_layer1/test_fingerprint.py
tests/test_layer1/test_models.py
tests/test_layer1/test_analysis_edge_cases.py
```

**Excludes:**
- `scue/layer1/detectors/`, `scue/layer1/eval_detectors.py` → owned by **detectors** section
- `scue/layer1/strata/` → owned by **strata** section
- `scue/layer1/scanner.py`, `usb_scanner.py`, `anlz_parser.py`, `rekordbox_scanner.py`, `reanalysis.py` → owned by **ingestion** section

## Incoming Inputs
- **From bridge section:** `DeviceInfo`, `PlayerState` types (consumed by `tracking.py`)
- **From strata section:** `ArrangementFormula`, `LiveStrataAnalyzer` (consumed by `tracking.py` for live updates)
- **From detectors section:** `MusicalEvent`, `DrumPattern` (produced by detectors, stored in TrackAnalysis)
- **From ingestion section:** Tracks added to `TrackStore` by scanners
- **From config:** Analysis config from `scue/config/loader.py`
- **From filesystem:** Audio files (MP3, WAV, FLAC) for offline analysis

## Outgoing Outputs
- **Types:** `TrackAnalysis`, `TrackCursor`, `Section`, `RGBWaveform`, `MusicalEvent`
- **Storage:** JSON analysis files (source of truth), SQLite cache (derived)
- **Callbacks:** `PlaybackTracker` accepts `on_player_update` / `on_track_loaded` from bridge adapter
- **Functions:** `run_analysis()`, `compute_fingerprint()`

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
- `scue.layer1.detectors` — `run_detectors()`, event types (called by analysis.py)
- `scue.config` — analysis config
- Python stdlib, `librosa`, `allin1_mlx`, `ruptures`, `numpy`
- **NOT:** ingestion modules, layer2-4, api, main.py

## How to Verify
```bash
.venv/bin/python -m pytest tests/test_layer1/test_analysis.py tests/test_layer1/test_cursor.py tests/test_layer1/test_enrichment.py tests/test_layer1/test_tracking.py tests/test_layer1/test_storage.py tests/test_layer1/test_divergence.py tests/test_layer1/test_fingerprint.py tests/test_layer1/test_models.py tests/test_layer1/test_analysis_edge_cases.py -v
```
Tests use local audio fixtures (gitignored) and synthetic generators.
