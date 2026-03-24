# Strata Pipeline: How It Works & How to Tune It

How each Strata tier analyzes track arrangement, and where every tunable constant lives.

---

## Quick Tier (~3-7s) — Full Mix, No Stem Separation

```
┌─────────────────────────────────────────────────────────────────────┐
│ INPUT: TrackAnalysis JSON + Audio File (22050 Hz mono)              │
└──────────┬──────────────────────────────────────┬───────────────────┘
           │                                      │
     ┌─────▼──────┐                        ┌──────▼──────────────────┐
     │ Stage A     │                        │ Stage B: ENERGY         │
     │ Read M7     │                        │ energy.py               │
     │ output      │                        │                         │
     │             │                        │ STFT on full mix        │
     │ drum_patterns                        │ → 3 bandpass filters:   │
     │ events      │                        │   LOW:  20–200 Hz       │
     │ sections    │                        │   MID:  200–2500 Hz     │
     │ downbeats   │                        │   HIGH: 2500–11025 Hz   │
     │ beats       │                        │                         │
     └──────┬──────┘                        │ Per-bar RMS energy in   │
            │                               │ each band               │
            │                               │                         │
            │                               │ Onset density per bar:  │
            │                               │   threshold = mean×0.5  │
            │                               │                         │
            │                               │ PSEUDO-ACTIVITY:        │
            │                               │  threshold_ratio = 0.15 │
            │                               │  min_span_bars = 2      │
            │                               │  Band→stem mapping:     │
            │                               │    low → bass           │
            │                               │    mid → other          │
            │                               │    high → other         │
            │                               └──────────┬──────────────┘
            │                                          │
     ┌──────▼──────────────────────┐                   │
     │ Stage C: PATTERN DISCOVERY  │                   │
     │ patterns.py                 │                   │
     │                             │                   │
     │ Extract per-bar 48-dim      │                   │
     │ vectors from M7 DrumPatterns│                   │
     │ (16 kick + 16 snare + 16   │                   │
     │  clap slots per bar)        │                   │
     │                             │                   │
     │ Greedy clustering:          │                   │
     │  cosine similarity          │                   │
     │  threshold = 0.85           │                   │
     │  min_repeats = 2            │                   │
     │                             │                   │
     │ Variation classification:   │                   │
     │  ≥0.99 sim → "exact"        │                   │
     │  ≥0.85 sim → "minor"        │                   │
     │  <0.85 sim → "major"        │                   │
     │                             │                   │
     │ Auto-naming from content:   │                   │
     │  "kick-4otf-snare-2+4" etc  │                   │
     └──────────┬──────────────────┘                   │
                │                                      │
                │                   ┌──────────────────▼──────────────┐
                │                   │ Stage D: TRANSITION DETECTION    │
                │                   │ transitions.py                   │
                │                   │                                  │
                │                   │ At each section boundary:        │
                │                   │  window = 2 bars before/after    │
                │                   │  energy_delta = after − before   │
                │                   │  normalized to max energy        │
                │                   │                                  │
                │                   │ Skip if |delta| < 0.15           │
                │                   │                                  │
                │                   │ Per-band deltas (lo/mid/hi):     │
                │                   │  band change > 0.1 → layer       │
                │                   │                                  │
                │                   │ Classification rules:            │
                │                   │  →"drop" + delta>0.2 = DROP      │
                │                   │  →"breakdown" + delta<-0.2       │
                │                   │    = BREAKDOWN                   │
                │                   │  → delta>0.15 + 2 layers =       │
                │                   │    LAYER_ENTER                   │
                │                   │  → else ENERGY_SHIFT             │
                │                   │                                  │
                │                   │ FILL DETECTION:                  │
                │                   │  spike_ratio > 1.8 of local      │
                │                   │  avg onset density               │
                │                   │  within 5.0s of boundary         │
                │                   │  confidence = (ratio−1)/2        │
                │                   └──────────────────┬───────────────┘
                │                                      │
                ▼                                      ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ Stage E: ASSEMBLY (engine.py::_assemble)                        │
     │                                                                 │
     │ Per section:                                                    │
     │  • active_layers from pseudo-activity spans overlapping section │
     │  • active_patterns from pattern instances overlapping section   │
     │  • energy_level + energy_trend per section                      │
     │    trend thresholds:                                            │
     │      |slope| < 0.05 = stable                                    │
     │      avg > overall × 1.3 = peak                                 │
     │      avg < overall × 0.7 = valley                               │
     │                                                                 │
     │ Complexity metric:                                              │
     │   pattern_variety × 0.3 + transition_density × 0.2              │
     │                                                                 │
     │ Auto-generated energy narrative (text summary)                  │
     └──────────────────────────────┬──────────────────────────────────┘
                                    │
                                    ▼
                    ArrangementFormula → strata/{fp}.quick.json
```

---

## Standard Tier (~1-2 min) — Real Stem Separation

```
┌─────────────────────────────────────────────────────────────────────┐
│ INPUT: TrackAnalysis JSON + Audio File                              │
└──────────┬──────────────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────────────────┐
     │ Stage B: STEM SEPARATION (separation.py)                       │
     │                                                                │
     │ Model: htdemucs                                                │
     │   (alternatives: htdemucs_ft, mdx_extra, mdx_extra_q)         │
     │                                                                │
     │ Produces 4 stems:                                              │
     │   drums.wav │ bass.wav │ vocals.wav │ other.wav                │
     │                                                                │
     │ Cached at strata/{fp}/stems/ (re-separation only if deleted)   │
     └────────┬───────────────────────────────────────────────────────┘
              │
              │  FOR EACH STEM:
              ▼
     ┌────────────────────────────────────────────────────────────────┐
     │ Stage C: PER-STEM ANALYSIS (per_stem.py)                       │
     │                                                                │
     │ ┌──────────────────────────────────────────────────────┐       │
     │ │ 1. Same energy analysis as quick tier (3 bands)      │       │
     │ │    but on the ISOLATED stem (much cleaner signal)    │       │
     │ └──────────────────────────────────────────────────────┘       │
     │                                                                │
     │ ┌──────────────────────────────────────────────────────┐       │
     │ │ 2. ACTIVITY DETECTION                                │       │
     │ │    ACTIVITY_THRESHOLD = 0.08 (8% of max)             │       │
     │ │    MIN_ACTIVITY_BARS = 2                             │       │
     │ │    confidence = 0.85 (fixed, higher than quick)      │       │
     │ └──────────────────────────────────────────────────────┘       │
     │                                                                │
     │ ┌──────────────────────────────────────────────────────┐       │
     │ │ 3. PER-STEM EVENT DETECTION (varies by stem type)    │       │
     │ │                                                      │       │
     │ │ DRUMS: PercussionHeuristicDetector on isolated stem   │       │
     │ │   kick_low_band_threshold = 0.4                      │       │
     │ │   snare_mid_band_threshold = 0.35                    │       │
     │ │   hihat_high_band_threshold = 0.3                    │       │
     │ │   (lower than full-mix M7 — less interference)       │       │
     │ │                                                      │       │
     │ │ BASS: librosa onset_detect (backtrack=True)           │       │
     │ │   hop_length=512, default sensitivity                │       │
     │ │                                                      │       │
     │ │ VOCALS: RMS energy phrase detection                   │       │
     │ │   threshold = max_rms × 0.10                         │       │
     │ │   (inactive→active transitions = phrase onsets)       │       │
     │ │                                                      │       │
     │ │ OTHER: librosa onset_detect                           │       │
     │ │   delta = 0.15 (higher to reduce FX/reverb noise)    │       │
     │ └──────────────────────────────────────────────────────┘       │
     │                                                                │
     │ ┌──────────────────────────────────────────────────────┐       │
     │ │ 4. PATTERN DISCOVERY (drums stem only)                │       │
     │ │    Same as quick tier (cosine sim on 48-dim vectors)  │       │
     │ │    but using re-detected patterns from clean stem     │       │
     │ └──────────────────────────────────────────────────────┘       │
     └────────┬───────────────────────────────────────────────────────┘
              │
              ▼
     ┌────────────────────────────────────────────────────────────────┐
     │ Stage D: CROSS-STEM TRANSITIONS (per_stem.py)                  │
     │                                                                │
     │ Every activity span start → LAYER_ENTER transition             │
     │ Every activity span end   → LAYER_EXIT transition              │
     │ (no threshold — every stem presence change is a transition)    │
     │                                                                │
     │ MERGED with energy-based transitions from quick pipeline:      │
     │   merge_window = 2.0 seconds                                   │
     │   (cross-stem wins when timestamps overlap)                    │
     └────────┬───────────────────────────────────────────────────────┘
              │
              ▼
     ┌────────────────────────────────────────────────────────────────┐
     │ Stage E: ASSEMBLY (engine.py::_assemble_standard)              │
     │                                                                │
     │ Same structure as quick but:                                   │
     │  • active_layers from REAL stem activity (not pseudo)          │
     │  • patterns from per-stem analysis (not just M7 drums)         │
     │                                                                │
     │ Complexity metric (different weights):                         │
     │   pattern_variety × 0.2                                        │
     │   + stem_variety × 0.2                                         │
     │   + transition_density × 0.15                                  │
     └────────┬───────────────────────────────────────────────────────┘
              │
              ▼
            ArrangementFormula → strata/{fp}.standard.json
```

---

## Tuning Knob Reference

Every tunable constant, where it lives, and what changing it does.

### Energy Analysis (`scue/layer1/strata/energy.py`)

| Knob | Location | Current | Effect |
|---|---|---|---|
| `LOW_BAND` | line 21 | `(20, 200)` Hz | Which frequencies count as "bass". Raise ceiling (e.g. 250) if bass detection is too narrow. |
| `MID_BAND` | line 22 | `(200, 2500)` Hz | Which frequencies count as "mids". Shift boundaries if mid-range instruments are misattributed. |
| `HIGH_BAND` | line 23 | `(2500, 11025)` Hz | Which frequencies count as "highs". Lower floor to catch more cymbal/hi-hat content. |
| `BAND_TO_STEM` | lines 26-30 | low→bass, mid→other, high→other | Controls which pseudo-layer each freq band maps to. Could map mid→vocals for vocal-heavy tracks. |
| `threshold_ratio` | line 183 (`_compute_pseudo_activity`) | `0.15` | Fraction of max band energy to count a bar as "active". Lower = more bars active (more false positives). Higher = only loud bars count. |
| `min_span_bars` | line 184 (`_compute_pseudo_activity`) | `2` | Minimum consecutive active bars to form an activity span. Raise to 4 if you get noisy 1-bar fragments. |
| onset threshold | line 150 | `mean(onset_strength) * 0.5` | What counts as an onset for density. Lower multiplier = more onsets detected per bar. |
| slope threshold (trend) | line 263 (`compute_energy_trend`) | `0.05` | Below this slope magnitude = "stable". Raise if too many sections show rising/falling when they shouldn't. |
| peak multiplier | line 264 | `1.3` | Section avg must exceed overall avg by this factor to be labeled "peak". Lower = more peaks. |
| valley multiplier | line 265 | `0.7` | Section avg must be below overall avg by this factor for "valley". Higher = more valleys. |

### Pattern Discovery (`scue/layer1/strata/patterns.py`)

| Knob | Location | Current | Effect |
|---|---|---|---|
| `similarity_threshold` | line 32 (`discover_patterns` param) | `0.85` | Cosine similarity threshold for grouping bars into the same pattern. Lower (0.7) = more bars grouped together, tolerates variation. Higher (0.95) = only near-identical bars match. |
| `min_repeats` | line 33 (`discover_patterns` param) | `2` | Minimum instances to call something a "pattern". Raise to 4+ to filter out patterns that only appear twice. |
| variation thresholds | lines 241-246 (`_make_instance`) | exact ≥ 0.99, minor ≥ 0.85 | Controls how pattern instances are classified as exact/minor/major variation. |

### Transition Detection (`scue/layer1/strata/transitions.py`)

| Knob | Location | Current | Effect |
|---|---|---|---|
| `energy_threshold` | line 24 (`detect_transitions` param) | `0.15` | Minimum normalized energy delta to register a transition. Lower = more transitions detected. Higher = only dramatic changes. |
| comparison window | line 57 | `2` bars before/after | How many bars on each side of a boundary to compare. Wider = smoother average but may miss sharp transitions. |
| band delta threshold | lines 140, 147 (`_classify_transition`) | `0.1` | Per-band energy change needed to flag a layer entering/exiting. |
| drop delta | line 161 | `> 0.2` | Energy increase magnitude to classify as `DROP_IMPACT`. |
| breakdown delta | line 165 | `< -0.2` | Energy decrease magnitude to classify as `BREAKDOWN`. |
| layer enter/exit delta | lines 169, 172 | `0.15` + 2 layers | Threshold and layer count for `LAYER_ENTER`/`LAYER_EXIT`. |
| spike_ratio (fills) | line 217 (`_detect_fills`) | `1.8` | How much louder a bar's onset density must be vs its preceding 3-bar average to count as a fill. |
| fill boundary proximity | line 225 | `5.0` seconds | How close to a section boundary a density spike must be to count as a fill (~2 bars at 120 BPM). |

### Per-Stem Analysis (`scue/layer1/strata/per_stem.py`)

| Knob | Location | Current | Effect |
|---|---|---|---|
| `ACTIVITY_THRESHOLD` | line 31 | `0.08` (8% of max) | Stem energy fraction to count a bar as "active". Lower = catches quieter passages in isolated stems. |
| `MIN_ACTIVITY_BARS` | line 33 | `2` | Same as quick tier but for isolated stems. |
| `kick_low_band_threshold` | line 239 (in `_detect_drum_events`) | `0.4` | Percussion detector sensitivity for kicks on isolated drum stem. Lower = catches softer kicks. |
| `snare_mid_band_threshold` | line 240 | `0.35` | Percussion detector sensitivity for snares. Lower = catches ghost notes. |
| `hihat_high_band_threshold` | line 241 | `0.3` | Percussion detector sensitivity for hi-hats. Lower = catches open hats and rides. |
| vocal presence threshold | line 350 (`_detect_vocal_events`) | `max_rms * 0.10` | When vocals are "present". Lower = catches whispers/ad-libs. Higher = only clear vocal lines. |
| synth onset delta | line 389 (`_detect_other_events`) | `0.15` | librosa `onset_detect` delta for "other" stem. Higher = fewer onsets (less noise from FX/reverb). Lower = catches subtle synth attacks. |

### Assembly & Engine (`scue/layer1/strata/engine.py`)

| Knob | Location | Current | Effect |
|---|---|---|---|
| Quick complexity weights | line 316 | pattern_variety × 0.3 + transition_density × 0.2 | Relative importance in the 0-1 complexity score. |
| Standard complexity weights | lines 397-401 | pattern_variety × 0.2 + stem_variety × 0.2 + transition_density × 0.15 | Standard tier includes stem variety as a factor. |
| `merge_window` | line 424 (`_merge_transitions`) | `2.0` seconds | When merging cross-stem and energy-based transitions, how close two must be to deduplicate. Wider = more merging. |
| demucs model | separation.py (StemSeparator) | `htdemucs` | `htdemucs_ft` = better quality but slower. `mdx_extra` = different separation character. |

---

## Re-Analysis with Pioneer Beatgrid

The enrichment pass (Layer 1B) replaces the librosa beatgrid with Pioneer's but
only rescales/snaps timestamps. The **reanalysis pass** (`scue/layer1/reanalysis.py`)
goes further — it re-runs the actual analytical steps with the Pioneer grid:

```
Enriched TrackAnalysis (v2, Pioneer beats/downbeats)
        │
        ▼
  1. Extract AudioFeatures from audio file (~5-10s)
  2. Re-snap sections to Pioneer downbeat grid (snap_to_8bar_grid)
  3. Re-classify sections with EDM flow model (classify_sections)
  4. Re-score confidence (score_confidence)
  5. Re-detect events with Pioneer beats/downbeats (run_event_detection)
        │
        ▼
  Reanalyzed TrackAnalysis (v3, source="pioneer_reanalyzed")
```

**Why this matters:** The Pioneer beatgrid is hand-verified in rekordbox.
Percussion detectors align 16th-note slots to beats — a more accurate grid
means kicks/snares land precisely where expected. House music should have
four-on-the-floor kicks on beats 1-2-3-4. Dubstep should have kick on 1,
snare on 3. The reanalysis validates and improves this alignment.

### Three Analysis Sources

| Source | Version | How produced | What it contains |
|---|---|---|---|
| `analysis` | v1 | Offline pipeline (librosa + allin1-mlx) | Original sections, events, patterns |
| `pioneer_enriched` | v2 | Enrichment pass (timestamps rescaled) | Same analysis, Pioneer-aligned timestamps |
| `pioneer_reanalyzed` | v3 | Reanalysis pass (steps re-run) | Re-detected sections, events, patterns |

All three versions are stored independently and can be compared side-by-side
in the Strata UI. Strata results are keyed by `(fingerprint, tier, source)`:
`strata/{fp}.{tier}.{source}.json`.

---

## Quick vs Standard: What Changes

| Aspect | Quick | Standard |
|---|---|---|
| Audio input | Full mix | 4 isolated stems (demucs) |
| Layer detection | Pseudo-layers from freq bands | Real stem activity spans |
| Pattern source | M7 drum patterns from full mix | Re-detected from isolated drum stem |
| Event detection | M7 detectors on full mix | Per-stem detectors on isolated stems |
| Transition source | Energy deltas at section boundaries | Cross-stem enter/exit + energy deltas (merged) |
| Stem data | Pseudo-stems mapped from bands | Real StemAnalysis per stem |
| Confidence | 0.6 (pseudo-activity) | 0.85 (isolated stem) |
| Complexity factors | pattern_variety, transition_density | + stem_variety |
