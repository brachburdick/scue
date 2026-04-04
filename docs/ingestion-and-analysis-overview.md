# Ingestion & Analysis Overview

How data enters SCUE, what each source provides, which analysis tiers each source unlocks, and how they execute.

For per-tier internals and tuning knobs, see [strata-pipeline.md](strata-pipeline.md).

---

## Ingestion Methods

| Method | Source | Trigger | Data Provided |
|---|---|---|---|
| **Audio File Analysis** | Local audio files (WAV, MP3, FLAC, AIFF, M4A, OGG) | User: POST `/api/tracks/analyze` or `/api/tracks/scan` | SHA256 fingerprint, librosa features (RMS, spectral centroid, chroma, MFCC, spectral contrast, tempogram, flatness, bandwidth), structure (allin1-mlx), change-point boundaries (ruptures), sections, BPM, key, energy curve, RGB waveform |
| **USB/ANLZ Scan** | Mounted USB with Rekordbox export (ANLZ files; `exportLibrary.db` for DLP hardware) | User: trigger scan via API | Pioneer beatgrid, cue points, memory points, hot cues, waveform (PWV3/5/7), phrases, BPM, key, title/artist |
| **Bridge (Pro DJ Link)** | Ethernet connection to Pioneer hardware via beat-link JAR subprocess (`ws://localhost:17400`) | Automatic when hardware is connected and bridge is running | **Real-time:** BPM, pitch, beat position (1-4), play state, on-air status, rekordbox_id. **On track load:** phrases, beatgrid, cue points, waveform |
| **Pioneer Enrichment** | Combines bridge/USB Pioneer data with an existing base audio analysis | Automatic on first deck load of a previously-analyzed track | Replaces librosa beatgrid with Pioneer beatgrid, re-aligns section boundaries, adds Pioneer BPM/key, produces v2+ analysis |

---

## Analysis Tiers

| Tier | Speed | Required Ingestion | What It Produces |
|---|---|---|---|
| **Base (prerequisite)** | ~30-60s | Audio file | `TrackAnalysis` v1: sections, events, drum patterns, energy curve, RGB waveform, BPM/key |
| **Quick** | ~10s | Base analysis (no stems, no hardware) | `ArrangementFormula`: per-bar energy (3 bands), onset density, pattern discovery from drum repetition, transitions at section boundaries |
| **Standard** | ~1-2 min | Base analysis + audio file (for demucs stem separation) | `ArrangementFormula`: 4 separated stems (drums/bass/vocals/other), per-stem energy + events + patterns + activity, cross-stem transitions, arrangement complexity |
| **Deep** | TBD | Future | Not yet implemented |
| **Live** | Real-time | Pioneer hardware via bridge (no audio file needed) | `ArrangementFormula` from Pioneer phrase/section data, hardware-verified structure |
| **Live Offline** | Hybrid | Pioneer sections + existing offline analysis | Pioneer section boundaries combined with offline analysis detail |

---

## Data Dependency Map

```
Audio File ──→ Base Analysis ──→ Quick Tier (sections + energy, no stems)
                    │
                    └──→ Standard Tier (needs audio file for demucs stem separation)

Pioneer HW ──→ Live Tier (standalone, no audio file needed)
     │
     └──→ Enrichment ──→ Enriched Base Analysis (v2+) ──→ Quick / Standard (re-run with Pioneer grid)

USB/ANLZ ──→ Pioneer metadata cache (SQLite) ──→ Enrichment (same path as bridge)
```

---

## Step-by-Step: Base Audio Analysis

Orchestrated in `scue/layer1/analysis.py`. Must complete before Quick or Standard tiers.

1. **Fingerprint** — SHA256 hash of audio bytes (becomes primary key)
2. **Extract features** (librosa) — RMS, spectral centroid, onset strength, chroma, MFCC, spectral contrast, tempogram, flatness, bandwidth, HPSS. Cached to `tracks/{fingerprint}/features.npz`
3. **Analyze structure** — allin1-mlx ML model (or fallback)
4. **Detect boundaries** — ruptures change-point detection
5. **Merge boundaries** — combine structure + boundary results
6. **Snap to 8-bar grid** — EDM prior: candidates snap to nearest 8-bar multiple
7. **Classify sections** — EDM flow model labels (intro, verse, build, drop, breakdown, outro)
8. **Score confidence** — per-section confidence from grid fit + flow validity
9. **Compute RGB waveform** — 3-band visualization (bass/mids/highs)
10. **Store + index** — JSON to `tracks/{fingerprint}.json` (source of truth), index to SQLite (derived cache)

**Output:** `TrackAnalysis` dataclass (see `scue/layer1/models.py`)

---

## Step-by-Step: Quick Tier

Orchestrated in `scue/layer1/strata/engine.py::analyze_quick`.

1. Load existing `TrackAnalysis` (base analysis must be complete)
2. **Stage A** — Read M7 detector output (events + drum patterns)
3. **Stage B** — Compute per-bar energy in 3 frequency bands (low 20-200 Hz, mid 200-2500 Hz, high 2500-11025 Hz) + onset density per bar + pseudo-activity spans
4. **Stage C** — Discover patterns via greedy cosine-similarity clustering on 48-dim drum vectors (threshold 0.85, min 2 repeats), auto-name from content
5. **Stage D** — Detect transitions at section boundaries (energy deltas, band deltas, fill detection)
6. **Stage E** — Assemble `ArrangementFormula` (per-section layers, patterns, energy trends, complexity score)

**Output:** `strata/{fingerprint}.quick.analysis.json`

---

## Step-by-Step: Standard Tier

Orchestrated in `scue/layer1/strata/engine.py::analyze_standard`.

1. Load `TrackAnalysis` (runs base analysis if missing)
2. **Stage B** — Stem separation via htdemucs → 4 stems (drums, bass, vocals, other), cached to `strata/{fingerprint}/stems/`
3. **Stage C** — Per-stem analysis for each stem:
   - Energy analysis (same 3 bands, but on isolated stem)
   - Activity detection (8% of max threshold, min 2 bars)
   - Event detection (stem-specific: percussion heuristic for drums, onset detect for bass/other, RMS phrases for vocals)
   - Pattern discovery (drums stem only, re-detected from clean signal)
4. **Stage D** — Cross-stem transition detection (layer enter/exit at every activity span boundary), merged with energy-based transitions (2s merge window)
5. **Stage E** — Assemble `ArrangementFormula` with real stem data (active layers from actual stems, not pseudo-bands)

**Output:** `strata/{fingerprint}.standard.analysis.json`

---

## Step-by-Step: Live Tier

Orchestrated in `scue/layer1/strata/live_analyzer.py::LiveStrataAnalyzer.build_from_pioneer`.

1. Bridge adapter receives `player_status` with loaded track
2. Pioneer phrase / beatgrid / cue point data arrives from hardware
3. `build_from_pioneer()` constructs `ArrangementFormula` directly from Pioneer sections
4. No audio processing — entirely hardware-derived

**Output:** `ArrangementFormula` with `pipeline_tier="live"`

---

## Step-by-Step: Pioneer Enrichment

Orchestrated in `scue/layer1/enrichment.py`. Runs once per track on first deck load.

1. Match loaded track to existing `TrackAnalysis` via `(source_player, source_slot, rekordbox_id)` → fingerprint lookup
2. Replace librosa beatgrid with Pioneer beatgrid (DJ-verified in rekordbox)
3. Re-align all section boundaries + event timestamps to Pioneer grid
4. Add Pioneer BPM, key
5. Log divergences (SCUE vs Pioneer) for tuning
6. Save as new version (v2+) without overwriting v1

**Output:** `TrackAnalysis` v2 with `source="pioneer_enriched"`

Optional reanalysis pass (`scue/layer1/reanalysis.py`) goes further — re-runs section classification, event detection, and confidence scoring against the Pioneer grid to produce v3 (`source="pioneer_reanalyzed"`).

---

## Three Analysis Sources

| Source | Version | How Produced | Use Case |
|---|---|---|---|
| `analysis` | v1 | Offline pipeline (librosa + allin1-mlx) | Standalone, no hardware needed |
| `pioneer_enriched` | v2 | Enrichment pass (timestamps rescaled to Pioneer grid) | Better timing accuracy |
| `pioneer_reanalyzed` | v3 | Reanalysis pass (analytical steps re-run with Pioneer grid) | Best accuracy, re-detected events |

All versions are stored independently. Strata results are keyed by `(fingerprint, tier, source)`.

---

## Storage

| What | Format | Location | Role |
|---|---|---|---|
| Track analysis | JSON | `tracks/{fingerprint}.json` | Source of truth |
| Librosa features | NumPy `.npz` | `tracks/{fingerprint}/features.npz` | Cached, reused across tiers |
| Pioneer metadata | SQLite | `cache/scue.db` table `pioneer_metadata` | Composite key lookup |
| Track index | SQLite | `cache/scue.db` table `tracks` | Fast queries (derived cache) |
| Strata results | JSON | `strata/{fingerprint}.{tier}.analysis.json` | Per-tier arrangement formulas |
| Separated stems | WAV | `strata/{fingerprint}/stems/` | Cached demucs output |
| Live Pioneer sidecar | JSON | `tracks/{fingerprint}/live_pioneer.json` | Ground truth from hardware |

---

## Frontend: Analysis Status Display

The library table displays per-track analysis status via the `AnalysisStatusChips` component
(`frontend/src/components/shared/AnalysisStatusChips.tsx`). See ADR-023.

**Compact mode** (table rows): `♪◆ | B Q S D L LO` — colored single-letter chips
**Full mode** (expanded row): `♪ Audio ◆ Pioneer | Base ✓ Quick ✓ Std ○ Deep — Live — L-O —`

**Color states:**
- Green = complete
- Amber = available (prerequisites met, not yet run)
- Grey = unavailable (hover tooltip explains why)

**TierSummaryBar** above the table shows aggregate counts: `Quick: 2036/2879 | Standard: 4/2879 | ...`

---

## Key Files

| Area | File | Purpose |
|---|---|---|
| Base analysis | `scue/layer1/analysis.py` | 10-step analysis orchestrator |
| Models | `scue/layer1/models.py` | TrackAnalysis, Section, MusicalEvent, TrackCursor |
| Feature cache | `scue/layer1/feature_cache.py` | Librosa features → .npz caching |
| Enrichment | `scue/layer1/enrichment.py` | Pioneer enrichment pass |
| Reanalysis | `scue/layer1/reanalysis.py` | Full re-run with Pioneer grid |
| Storage | `scue/layer1/storage.py` | JSON + SQLite persistence |
| Strata engine | `scue/layer1/strata/engine.py` | Quick / Standard / Live tier orchestration |
| Strata models | `scue/layer1/strata/models.py` | ArrangementFormula, Pattern, StemAnalysis |
| Energy | `scue/layer1/strata/energy.py` | Per-bar energy computation |
| Patterns | `scue/layer1/strata/patterns.py` | Pattern discovery |
| Transitions | `scue/layer1/strata/transitions.py` | Transition detection |
| Per-stem | `scue/layer1/strata/per_stem.py` | Per-stem analysis (Standard tier) |
| Live analyzer | `scue/layer1/strata/live_analyzer.py` | Live tier from Pioneer data |
| Bridge adapter | `scue/bridge/adapter.py` | BridgeMessage → Layer 1 types |
| USB scanner | `scue/layer1/usb_scanner.py` | USB ANLZ file scanning |
| Rekordbox scanner | `scue/layer1/rekordbox_scanner.py` | DLP exportLibrary.db scanning |
| API: tracks | `scue/api/tracks.py` | Track CRUD + analysis endpoints |
| API: strata | `scue/api/strata.py` | Strata CRUD + analysis endpoints |
| FE types | `frontend/src/types/strata.ts` | TypeScript mirrors of strata models |
| FE analysis chips | `frontend/src/components/shared/AnalysisStatusChips.tsx` | Analysis status chip strip + tier summary bar |
| FE library table | `frontend/src/components/library/ScueLibraryTab.tsx` | Library table with analysis column |
| Config | `config/detectors.yaml` | M7 event detection strategies + parameters |
