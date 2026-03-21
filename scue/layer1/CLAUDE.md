# Layer 1 — Track Analysis & Live Tracking

## What this layer does
Analyzes audio files offline (1A) and tracks live DJ playback (1B).
Produces TrackAnalysis objects and a real-time TrackCursor.
Receives live data from the beat-link bridge (Layer 0) via the bridge adapter.

## Key dependencies
- librosa, allin1-mlx, ruptures (audio analysis)
- Bridge adapter (scue/bridge/adapter.py) for live Pro DJ Link data

## Implementation rules
- Track analysis stored as JSON files in the project's tracks/ directory. SQLite in cache/ is a derived index only.
- Track fingerprint = SHA256 of audio file. This is the primary key and the JSON filename.
- The Pioneer enrichment pass (enrichment.py) runs once per track on first deck load. It NEVER overwrites the original analysis — it creates a new versioned entry.
- Divergence between SCUE and Pioneer data is ALWAYS logged via divergence.py.
- Section segmentation pipeline order: ML boundary detection → 8-bar snapping → EDM flow model labeling.
- Event detection (M7) runs after section scoring as step 9/10 in the pipeline. See `detectors/` subpackage.
- Detectors are pluggable via `DetectorProtocol`. Config in `config/detectors.yaml`. Active strategies: percussion (heuristic or RF), riser, faller, stab.
- Percussion uses compact `DrumPattern` storage (16th-note slot arrays per bar). Use `expand_patterns()` to convert to individual `MusicalEvent` objects at runtime.
- All timestamps in TrackAnalysis are in seconds relative to track start, at the original BPM.

## Testing
- Test tracks in tests/fixtures/audio/
- Mock bridge data in tests/fixtures/bridge/
- Run: `python -m pytest tests/test_layer1/ -v`

## This layer's output contract
See docs/CONTRACTS.md → "Layer 1 → Layer 2: DeckMix"
Do NOT change the TrackCursor shape without updating CONTRACTS.md and getting approval.

## Domain knowledge
For audio analysis with librosa, see docs/domains/audio-analysis.md
For EDM track structure conventions, see docs/domains/edm-arrangement.md
