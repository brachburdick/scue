# Findings: Arrangement Pipeline Paths

**Date:** 2026-03-29
**Area:** Layer 1 / Strata arrangement engine
**Status:** Active research

---

## Problem Statement

SCUE needs to produce a structured song arrangement formula (sections, energy curves, patterns, transitions) for every track. The arrangement formula feeds Layer 2 cue generation and the frontend Arrangement Page.

Three different starting points exist for building this formula:

1. Pioneer hardware data streamed over Pro DJ Link (phrases, waveform, beatgrid, cues)
2. Audio files analyzed offline via the DSP pipeline (energy bands, M7 drum patterns, transition detection)
3. Both sources combined

Each starting point has different availability constraints, pre-work requirements, compute cost, and quality characteristics. This document maps the three pipeline paths, their tradeoffs, and the execution plan.

---

## Three Pipeline Paths

| Dimension | Path A: Pioneer-Only | Path B: Audio-Only | Path C: Hybrid |
|---|---|---|---|
| **Tier name** | `live` | `quick` / `standard` | `hybrid` |
| **Inputs** | Pioneer phrase analysis, 3-band waveform, beat grid, cue points | Audio file (22050 Hz mono) + M7 detector output | Pioneer sidecar (`live_pioneer.json`) + audio file + M7 output |
| **Section source** | Pioneer phrase analysis (DJ-verified) | ML boundary detection + 8-bar snapping + EDM flow model | Pioneer phrases (DJ-verified) |
| **Energy source** | Real Pioneer 3-band waveform energy (with static heuristic fallback) | STFT-derived 3-band RMS per bar + onset density | STFT-derived 3-band RMS per bar + onset density |
| **Pattern source** | None (not yet implemented) | 48-dim drum pattern vectors, greedy cosine clustering | 48-dim drum pattern vectors, greedy cosine clustering |
| **Transition source** | Inferred from section boundary changes | Detected at section boundaries using energy delta | Detected at Pioneer section boundaries using energy delta |
| **Pre-work needed** | Track must be loaded on Pioneer hardware | Audio file on disk, M7 analysis complete | Both: Pioneer sidecar saved + audio analyzed |
| **Compute cost** | Near zero (data already parsed) | 3-7s (quick), 1-2 min (standard with stems) | ~5s (quick-tier DSP on pre-analyzed track) |
| **Section quality** | High -- Pioneer phrase analysis is reliable and DJ-verified | Medium -- ML models occasionally misplace boundaries by a few bars | High -- uses Pioneer sections |
| **Energy quality** | Low -- static lookup, no actual audio content awareness | High -- real frequency-band energy from audio | High -- real frequency-band energy from audio |
| **Pattern quality** | None | Medium-High -- depends on M7 detector accuracy | Medium-High -- same as audio-only |
| **Current status** | Implemented (`live_analyzer.py`), real waveform energy + activity spans (2026-03-29) | Implemented (`engine.py` quick/standard tiers), validated on 35 tracks | Implemented 2026-03-29 (`engine.py` `analyze_hybrid()`) |

### Path A: Pioneer-Only (Live Tier)

Built in `scue/layer1/strata/live_analyzer.py`. Constructs an `ArrangementFormula` entirely from Pro DJ Link data. Section boundaries come from Pioneer phrase analysis, which is high quality -- these are the boundaries Pioneer's own analysis engine computed from the rekordbox database.

**Improved 2026-03-29:** Now derives real energy from Pioneer's 3-band RGB waveform data via `_waveform_section_energy()` and `_waveform_activity_spans()`. Per-section energy is computed from actual low/mid/high frequency amplitudes at ~150 samples/second. Energy trends are derived from first-quarter vs last-quarter comparison within each section. Pseudo-activity spans (bass, other) are thresholded from per-bar band averages, populating `active_layers` per section. Falls back to static heuristic dict only when no waveform is available.

### Path B: Audio-Only (Quick/Standard Tiers)

The existing Strata pipeline documented in `docs/strata-pipeline.md`. Runs full DSP: STFT with 3 bandpass filters (20-200 Hz, 200-2500 Hz, 2500-11025 Hz), per-bar RMS energy, onset density, pseudo-activity spans, 48-dimensional drum pattern clustering, and transition detection.

Sections come from ML models (allin1-mlx + ruptures + EDM flow model), which are generally accurate but occasionally misalign by a bar or two compared to Pioneer's phrase analysis.

**Next step:** Tune clustering and transition thresholds against a set of reference tracks with known-good arrangement annotations.

### Path C: Hybrid (New)

Takes the best of both: Pioneer's reliable DJ-verified section boundaries combined with audio-derived energy, patterns, and transitions. This gives high-quality sections (Path A's strength) with real energy and pattern data (Path B's strength).

Implemented 2026-03-29 as `StrataEngine.analyze_hybrid()`.

---

## Execution Order

**C first, then A and B in parallel.**

Path C establishes the quality baseline because it combines the strongest signals from both data sources. Once hybrid results exist for reference tracks, they serve as ground truth for:

- **Path A improvements:** Compare Pioneer-waveform-derived energy against hybrid's STFT energy to validate the waveform approach.
- **Path B tuning:** Compare ML-derived sections against hybrid's Pioneer sections to measure and reduce boundary error.

Paths A and B are independent of each other and can proceed in parallel once C provides reference data.

---

## What Was Built (Path C Implementation)

### Code

- **`StrataEngine.analyze_hybrid()`** in `scue/layer1/strata/engine.py` -- approximately 80 lines of orchestration across 6 stages (A-F). Introduces zero new algorithms; composes existing functions in a new order.

### Stages

| Stage | What it does | Reuses |
|---|---|---|
| A | Load Pioneer sidecar, convert phrases to `Section` objects via `PHRASE_KIND_MAP` | `live_analyzer.py` mappings |
| B | Load `TrackAnalysis` for audio features + M7 output | `_track_store.load_latest()` |
| C | Compute per-bar energy from audio | `compute_energy_analysis()` |
| D | Discover drum patterns | `discover_patterns()` |
| E | Detect transitions at Pioneer section boundaries | `detect_transitions()` |
| F | Assemble `ArrangementFormula` with Pioneer sections swapped in | `_assemble()` |

### Infrastructure changes

- `"hybrid"` added to `VALID_TIERS` -- automatically supported by existing API tier validation and strata store
- Saved with `source="pioneer_live"` metadata
- **CLI:** `tools/compare_tiers.py` for side-by-side tier comparison output
- **Tests:** 7 tests in `test_strata_hybrid.py` covering routing, validation, and storage roundtrip
- **Bug fix:** `_track_store._base_dir` corrected to `_track_store.tracks_dir` (latent bug also present in `live_offline` path)

---

## Validation Gap

No tracks currently have both a completed audio analysis and a Pioneer sidecar (`live_pioneer.json`) on disk simultaneously. To validate the hybrid path end-to-end:

1. **Hardware path:** Play analyzed tracks on Pioneer hardware so the bridge captures and saves phrase data as a sidecar.
2. **Manual path:** Construct sidecars from existing bridge test fixtures in `tests/fixtures/bridge/` for tracks that already have audio analysis.

Until one of these is done, hybrid analysis cannot run on real data.

---

## Path B: Quick Tier Validation (2026-03-29)

Ran quick tier on 3 reference tracks (Baddadan, Eon Immortal, Duel of Fates). Results:

- **Energy values are realistic:** drops at 0.84-0.99, breakdowns at 0.10-0.21, verses at 0.34-0.71
- **Patterns discovered:** 12-18 per track, auto-named (e.g., "kick-4otf", "snare-4.3-clap-3")
- **Transitions detected:** 2-10 per track, correctly identifying drop impacts and breakdowns
- **Active layers populated:** drums, bass, other from pseudo-activity energy bands

35 tracks total have analysis data on disk, most with audio files and drum patterns. Quick tier runs in 0.7-6.7s per track.

---

## Next Steps

| Path | Action | Depends on |
|---|---|---|
| C (Hybrid) | Create or capture real Pioneer sidecars for analyzed tracks | Hardware session or fixture construction |
| A (Pioneer-Only) | DONE: Real waveform energy + activity spans implemented | -- |
| B (Audio-Only) | Tune clustering threshold (0.85) and transition delta thresholds against reference tracks | Manual review of quick tier output on more tracks |
| All | Feed arrangement formulas into M3 cue stream (Layer 2) | M3 spec implementation |
