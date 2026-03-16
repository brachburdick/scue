# Layer 1 — Track Analysis & Live Tracking

## What this layer does
- **1A (offline):** Analyzes audio files → `TrackAnalysis` objects stored in SQLite.
  Runs ML boundary detection (allin1-mlx), 8-bar snapping, EDM flow model labeling, and (later) Tier 2 event detection.
- **1B (live):** Parses Pro DJ Link UDP packets → `PlaybackState` + `TrackCursor`.
  Maintains a real-time cursor into the stored TrackAnalysis, time-adjusted for current BPM.
  Triggers the Pioneer enrichment pass on first track load.

This layer's only public output to the rest of the app is the `TrackCursor` (→ Layer 2).
See `docs/CONTRACTS.md` for the exact shape.

## Key files
| File | Purpose |
|---|---|
| `analysis.py` | Offline pipeline orchestrator (Tier 1 + 2 + 3) |
| `models.py` | All dataclasses: TrackAnalysis, Section, MusicalEvent, DeckState, TrackCursor, etc. |
| `db.py` | SQLite storage — keyed by SHA256 track fingerprint, versioned analyses |
| `enrichment.py` | Pioneer enrichment pass: beatgrid swap, re-alignment, divergence logging |
| `divergence.py` | DivergenceRecord logging and query |
| `prodjlink.py` | Pro DJ Link UDP parser (ports 50000/50001) + network interface discovery |
| `tracking.py` | Live playback tracking: PlaybackState from Pioneer packets |
| `cursor.py` | TrackCursor logic: maps playback position → section, scales timestamps |
| `waveform.py` | RGB waveform data (R=bass, G=mids, B=highs) for frontend visualization |
| `detectors/sections.py` | ML boundary detection (allin1-mlx) + ruptures change-point + 8-bar snapping |
| `detectors/flow_model.py` | EDM arrangement scorer/labeler (drop, build, fakeout, etc.) |
| `detectors/features.py` | librosa feature extraction (RMS, centroid, flux, chroma, MFCCs, etc.) |
| `detectors/percussion.py` | Tier 2: kick, snare, hihat onset detection (stub) |
| `detectors/melodic.py` | Tier 2: arp, riser, faller, stab detection (stub) |
| `detectors/effects.py` | Tier 2: filter sweep, panning sweep detection (stub) |

## Key dependencies
- `librosa`, `allin1_mlx`, `ruptures` (audio analysis)
- Pro DJ Link UDP protocol (ports 50000/50001)
- `netifaces` (interface discovery)
- `sqlite3` (standard library)

## Implementation rules
- Track fingerprint = SHA256 of the audio file bytes. This is the database primary key.
- **NEVER overwrite Pioneer data with SCUE data.** When Pioneer provides beatgrid/BPM/key, store a new versioned `TrackAnalysis` entry tagged `source: "pioneer_enriched"`. Keep the original `source: "analysis"` entry.
- All timestamps in `TrackAnalysis` are in seconds relative to track start, at the **original BPM**. The cursor scales them at read time using `(original_bpm / current_bpm)`.
- Every divergence between SCUE and Pioneer data → `DivergenceRecord` via `divergence.py`.
- Analysis pipeline stages run in order: `detectors/features.py` → `detectors/sections.py` (ML + 8-bar snap) → `detectors/flow_model.py` (EDM labeler) → `db.py` (store).

## macOS Pioneer socket quirk (critical)
Binding to a unicast IP silently prevents broadcast UDP reception on macOS.
Always use `IP_BOUND_IF=25` (see `prodjlink.py::_make_udp_socket()`).
See LEARNINGS.md for full details.

## Testing
- Test audio fixtures: `tests/fixtures/audio/`
- Pro DJ Link packet captures: `tests/fixtures/prodjlink/`
- Run: `python -m pytest tests/test_layer1/ -v`

## This layer's output contract
See `docs/CONTRACTS.md` → "Layer 1 → Layer 2: TrackCursor"
Do NOT change the TrackCursor shape without updating CONTRACTS.md and getting Brach's approval.
