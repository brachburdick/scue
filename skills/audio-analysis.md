# Skill: Audio Analysis / Track Processing

> **When to use:** Any task involving Layer 1A (offline analysis), audio feature extraction, beat detection, section detection, or stem separation.

---

## Stack & Environment

- librosa for audio feature extraction and beat tracking
- allin1-mlx for structure analysis (intro/verse/chorus/outro detection)
- Demucs for stem separation (planned)
- Analysis results stored as JSON in `tracks/` (source of truth)
- SQLite in `cache/scue.db` is a derived cache only — never treat as authoritative

## Architecture

```
Audio file → librosa (features, beats) + allin1-mlx (sections) → TrackAnalysis → JSON file
```

## Common Patterns

### Analysis Pipeline
- Entry point: `scue/layer1/analysis.py`
- Feature detectors in `scue/layer1/detectors/`
- Models in `scue/layer1/models.py` — `TrackAnalysis`, `MusicalEvent`, etc.
- Path-based flow: user provides directory, system scans and analyzes (ADR-007)

### Data Storage
- JSON files keyed by audio fingerprint (SHA256)
- Pioneer data from USB/ANLZ enriches but never overwrites SCUE analysis
- Divergence between Pioneer and SCUE data is logged, not resolved automatically

## Known Gotchas

- **allin1-mlx weights:** Must be pre-converted; they are NOT auto-downloaded. Ensure weights exist before running analysis.
- **librosa beat tracking drift:** Beat tracking drifts on tempo-variable tracks. Pioneer beatgrid is used as source of truth (ADR-001).
- **Section boundary clamping:** Section boundaries must be clamped to track start/end to avoid out-of-range errors.
- **ruptures KernelCPD performance:** Needs 4x downsample for acceptable performance on full-length tracks.
- **pyrekordbox ANLZ panics:** rbox's Rust ANLZ parser can panic (uncatchable in Python) on Device Library Plus files. Pure Python parser (`scue/layer1/anlz_parser.py`) is the safe alternative (ADR-013).

## Anti-Patterns

- Overwriting Pioneer-sourced data with SCUE-derived data (log divergence instead)
- Treating SQLite cache as source of truth (JSON files are authoritative)
- Running analysis without checking if weights/models are available
- [TODO: Fill from project experience]
