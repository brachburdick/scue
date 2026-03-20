# Research Findings: Event Detection for Milestone 7 (Layer 1A, Tier 2)

**Request:** Operator request — M7 event detection research
**Date:** 2026-03-20
**Status:** Complete

---

## Executive Summary

| Event Type | Recommended Approach | Expected Accuracy | Additional Compute | Priority |
|---|---|---|---|---|
| **Kick** | Beat-synchronous sub-band energy classification | 90-95% | <100ms | HIGH |
| **Snare/Clap** | Features at beats 2+4 + temporal envelope | 80-85% | <50ms | HIGH |
| **Hi-hat** | High-band onset + decay time + pattern classification | 80-85% | ~200ms | MEDIUM |
| **Riser** | Spectral centroid slope + flatness + section prior | 85-90% | ~100ms | HIGH |
| **Faller** | Falling centroid + RMS decay + section prior | 70-80% | ~20ms | LOW |
| **Stab** | HPSS harmonic ratio + onset + centroid filter | 70-80% | ~100ms | MEDIUM |
| **Arp pattern** | Chroma autocorrelation + harmonic onset periodicity | 65-80% | ~100ms | LOW |

**Total additional compute: ~1.2s** (dominated by HPSS at ~500ms). Well within the 3-8s budget on M-series Mac.

**Key architectural decision: Beat-synchronous classification for percussion, signal-based detection for tonal events.** The known beatgrid transforms percussion detection from a hard continuous-audio problem into a tractable discrete-slot classification problem. Tonal events (risers, stabs, arps) require signal-level analysis but benefit enormously from section-type priors.

**Skip madmom.** Unmaintained, Apple Silicon issues, trained on acoustic drums (not EDM synths). The beatgrid prior + librosa + scikit-learn is faster, more maintainable, and better suited.

---

## Architecture: Two Parallel Pipelines

```
                    ┌─────────────────────────────────────┐
                    │  Existing Feature Extraction (Pass 0) │
                    │  RMS, onset strength, centroid,       │
                    │  chroma, MFCC, spectral contrast      │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────┐
                    │  New Features (Pass 1) ~600ms        │
                    │  • Spectral flatness (NEW, ~50ms)    │
                    │  • Spectral bandwidth (NEW, ~30ms)   │
                    │  • HPSS separation (NEW, ~500ms)     │
                    │  • Harmonic onset envelope (~20ms)   │
                    └──────┬──────────────────┬───────────┘
                           │                  │
              ┌────────────┴──┐      ┌────────┴────────────┐
              │  PERCUSSIVE   │      │  TONAL/SPECTRAL      │
              │  Pipeline     │      │  Pipeline            │
              │  (Pass 2a)    │      │  (Pass 2b)           │
              │  ~300ms       │      │  ~300ms              │
              ├───────────────┤      ├──────────────────────┤
              │ Beat-sync RF  │      │ Riser detector       │
              │ classifier:   │      │ Faller detector      │
              │ kick, snare,  │      │ Stab detector        │
              │ clap, hihat   │      │ Arp detector         │
              └──────┬────────┘      └────────┬────────────┘
                     │                        │
                     └────────┬───────────────┘
                              │
                    ┌─────────┴───────────────────────────┐
                    │  Post-Processing (Pass 3) ~20ms      │
                    │  • Section prior application          │
                    │  • Overlap resolution                 │
                    │  • Event merging/dedup                │
                    └──────────────────────────────────────┘
```

---

## Domain 1: Percussive Event Detection

### Primary Approach: Beat-Synchronous Slot Classification

Since we already have a beatgrid, the problem transforms from "find drum onsets in continuous audio" to "classify what's happening at each known beat subdivision." This is dramatically easier.

**Grid:** Subdivide each beat into 4 slots (16th-note resolution). A 5-minute track at 128 BPM has ~2,560 slots.

**Feature vector per slot (~14 dimensions):**

| Feature | Dims | Source |
|---|---|---|
| Sub-band energy (5 bands: 30-100, 100-400, 400-1k, 1k-5k, 5k-11k Hz) | 5 | Mel spectrogram (existing) |
| Multi-band onset strength (3 bands: low/mid/high) | 3 | `onset_strength_multi` (new call, cheap) |
| Spectral centroid | 1 | Existing |
| Spectral flatness | 1 | New (cheap) |
| Zero-crossing rate | 1 | New (cheap) |
| RMS energy | 1 | Existing |
| Beat position (cyclic sin/cos encoding of 0-15 within bar) | 2 | From beatgrid |

**Classifier:** Random Forest (100-200 trees) or Gradient Boosted Trees.
- Classes: `kick`, `snare`, `clap`, `hihat_closed`, `hihat_open`, `silence`, `combo`
- Training data needed: 5-10 manually labeled tracks, 4-8 bars each (~320-1,280 labeled slots)
- Model size: ~50KB serialized (joblib)
- Inference time: <10ms for a full track

**Beat position encoding is extremely powerful.** `sin(2π·pos/16)` and `cos(2π·pos/16)` let the classifier learn that kicks favor positions 0,4,8,12 and snares/claps favor positions 4,12 (beats 2,4 in 4/4).

### Per-Instrument Details

#### Kick Detection (90-95% accuracy)

Even without the RF classifier, kicks can be detected with high accuracy:

- At each beat position, check sub-band energy in 30-120 Hz range
- Kicks are broadband impulses (high spectral flatness in low band during attack) vs. bass synths which are tonal (low spectral flatness)
- Additional discriminator: attack envelope — kicks rise in <5ms, bass synth onsets are softer
- In 4-on-the-floor EDM, kicks land on every beat — the beatgrid alone gets you 80%+

#### Snare/Clap Detection (80-85% accuracy)

The strongest discriminator between snare and clap is **temporal envelope shape**:

| Feature | Snare | Clap |
|---|---|---|
| Attack profile | Single sharp impulse | Multiple micro-attacks ("rattle", 2-4 peaks in 20-40ms) |
| Spectral centroid | 2-5 kHz | 1-3 kHz |
| Spectral flatness | High (broadband noise) | Moderate |
| Duration | 50-150ms | 80-200ms |
| Low-freq content | Some body (100-300 Hz) | Minimal below 500 Hz |

In practice, many EDM producers layer snares WITH claps on beats 2 and 4. For lighting, detecting "backbeat percussive event" as a single category and only disambiguating when the spectral profile is clear may be sufficient.

#### Hi-Hat Detection (80-85% accuracy)

**Two-stage approach:**

1. **Individual hits:** Detect onsets in the 5-16 kHz band. Quantize to nearest 16th-note position.
2. **Open vs closed:** Measure spectral decay time after each hit. Closed: 20-60ms. Open: 100-300ms+.
3. **Pattern classification per bar:** Match the quantized hit pattern against known EDM patterns (8ths, 16ths, offbeat, shuffle). Correlation-based matching is simple and effective.

**Hi-hat rolls** (32nd notes in buildups): detect by onset density >16 events per bar. Flag the section as a buildup indicator. Intensity typically ramps — track the onset strength slope.

### Fallback Heuristics

If the RF classifier is not yet trained, use rule-based detection as a bootstrap:

```
At each beat (0, 4, 8, 12 in 16th grid):
  if low_band_energy > threshold → kick
At beats 2, 4 (positions 4, 12):
  if mid_band_energy > threshold AND centroid > 500 Hz → snare_or_clap
At each 16th position:
  if high_band_energy > threshold AND centroid > 5000 Hz → hihat
```

This gets ~75% accuracy and provides the initial labeled data to train the RF.

---

## Domain 2: Tonal/Spectral Event Detection

### New Features Required

| Feature | Cost | Used By |
|---|---|---|
| Spectral flatness | ~50ms | Riser (noise vs tonal), Faller (cymbal discrimination) |
| Spectral bandwidth | ~30ms | Riser (bandwidth expansion detection) |
| HPSS (harmonic/percussive separation) | ~500ms | Stab (harmonic ratio), Arp (harmonic onsets) |

HPSS is the single most expensive new computation but unlocks multiple detectors. Run once, reuse everywhere.

### Riser Detection (85-90% with section priors)

**Acoustic signature:** Sustained rising spectral centroid over 2-8 bars. Two subtypes:
- **Tonal risers:** pitched synth sweep (low spectral flatness, clear centroid slope)
- **Noise risers:** white noise with high-pass sweep (high spectral flatness >0.4, rising centroid)

**Algorithm:**
1. Restrict search to final 2-16 bars before section boundaries labeled "build→drop" or "intro→drop"
2. Compute linear regression of spectral centroid over this window
3. Flag if: positive slope > threshold AND R² > 0.7 AND sustained over ≥ 2 bars
4. Classify subtype via spectral flatness at the detected region
5. Refine start time by walking backward until slope flattens

**Why section priors matter here:** Risers terminate at section boundaries. Restricting search to pre-boundary windows eliminates most false positives from melodic content with rising pitch. Precision jumps from ~70% to ~90%+ with this prior.

**Duration output:** Quantized to beat boundaries. Typical: 4, 8, or 16 beats.

### Faller Detection (70-80% with section priors)

Mirror of riser detection with key differences:
- **Falling spectral centroid** over 1-4 bars (shorter than risers)
- **Decaying RMS envelope** (fallers accompany energy decay)
- **Section context:** search in first 1-4 bars after drop→breakdown transitions
- **Cymbal discrimination:** crash cymbal decay has high spectral flatness throughout AND follows exponential centroid decay. Deliberate faller synths have lower flatness OR linear (not exponential) centroid sweep.

Essentially free once riser detection is built — same features, inverted thresholds, different search windows.

### Stab Detection (70-80% accuracy)

**Three-stage pipeline:**

1. **Onset filtering:** Select high-confidence onsets from existing onset strength
2. **Harmonic classification via HPSS:** For each onset, compare energy in harmonic vs percussive separation. Stabs have harmonic_ratio > 0.3 (unlike kicks/snares which are primarily percussive)
3. **Spectral profile check:** Centroid > 500 Hz (rejects kicks), duration 50-200ms (rejects sustained pads), high spectral contrast in mid/high bands

**Individual stabs vs patterns:** Detect individuals first, then group by rhythmic regularity. If stabs repeat at consistent beat subdivisions, emit both individual `stab` events and a parent annotation in the payload.

### Arpeggio Pattern Detection (65-80% accuracy)

Most algorithmically involved. Use chroma autocorrelation:

1. **Beat-synchronous chroma:** Quantize existing chroma to 16th-note resolution using `librosa.util.sync()`
2. **Chroma flux:** Frame-to-frame chroma difference (trivial: `np.diff`)
3. **Autocorrelation:** Peaks at musically meaningful lags (2, 4, 6, 8 sixteenths) indicate periodic melodic motion
4. **Validate with harmonic onset density:** Arpeggios have 2-4 notes per beat. Use onset detection on HPSS harmonic component.

**Output:** `arp_pattern` events (start, duration, rate) rather than individual notes. Individual `arp_note` events can be derived at playback time from pattern + beatgrid, keeping storage compact.

**Accuracy varies by mix density:** Breakdowns (sparse): ~85%. Drops (dense): ~60%.

---

## Section-Aware Prior System

Use section labels to weight detection confidence, not to gate detectors:

| Detector | build | drop | breakdown | intro | verse | outro |
|---|---|---|---|---|---|---|
| riser | **1.5** | 0.3 | 0.5 | 1.2 | 0.5 | 0.3 |
| faller | 0.2 | 1.2 | **1.5** | 0.5 | 0.5 | 1.0 |
| stab | 0.8 | **1.5** | 0.5 | 0.3 | 0.5 | 0.3 |
| arp | 1.2 | 0.6 | **1.5** | 0.8 | 1.0 | 0.5 |
| hihat_roll | **1.5** | 0.3 | 0.5 | 0.3 | 0.5 | 0.3 |

Multiply detected event intensity by section prior. Drop events below `min_confidence` threshold. This is a ~5ms operation that eliminates 15-25% of false positives.

---

## Storage Impact

For a typical 6-minute EDM track:

| Event Type | Count Range | JSON Size |
|---|---|---|
| Kick | 200-800 | 20-80 KB |
| Snare/Clap | 100-400 | 10-40 KB |
| Hi-hat (individual) | 400-1600 | 40-160 KB |
| Riser | 2-6 | <1 KB |
| Faller | 2-6 | <1 KB |
| Stab | 50-500 | 5-50 KB |
| Arp pattern | 2-10 | <1 KB |

**Worst case total: ~330 KB.** Acceptable for JSON storage.

**Optimization for high-count events:** Store percussion as beat-synchronous pattern arrays rather than individual events:

```json
{
  "drum_pattern": {
    "bar_range": [0, 16],
    "pattern": {
      "kick":  [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
      "snare": [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
      "hihat": [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0]
    }
  }
}
```

This reduces percussion storage from ~300 KB to ~5-10 KB by storing per-bar patterns with bar ranges where they apply. Individual `MusicalEvent` objects are expanded from patterns at runtime.

---

## Integration Plan

### Pipeline Changes

**`detectors/features.py` — add 3 new features to `extract_all()`:**
- `spectral_flatness` (~50ms)
- `spectral_bandwidth` (~30ms)
- HPSS separation stored as `y_harmonic`, `y_percussive` (~500ms)

**New modules:**
- `detectors/drums.py` — beat-synchronous percussion classifier
- `detectors/tonal_events.py` — riser, faller, stab, arp detectors
- `detectors/section_priors.py` — prior weight application

**`analysis.py` — add step between current step 8 (confidence) and step 9 (waveform):**
```
Step 8.5/10: Detecting musical events...
  a. Percussion classification (beat-synchronous RF)
  b. Tonal event detection (riser, faller, stab, arp)
  c. Section prior application
```

### Model Training Workflow

1. Build the heuristic-based fallback detectors first (no ML needed)
2. Use heuristic output + manual correction on 5-10 reference tracks to create training set
3. Train Random Forest, serialize with joblib
4. Ship trained model as `models/drum_classifier.joblib` (~50KB)
5. Pipeline uses RF when available, falls back to heuristics

### MusicalEvent Model — Proposed Payload Schemas

```python
# Kick
MusicalEvent(type="kick", timestamp=1.25, duration=None, intensity=0.9,
             payload={"low_energy": 0.85, "beat_position": 0})

# Snare
MusicalEvent(type="snare", timestamp=1.72, duration=None, intensity=0.8,
             payload={"temporal_profile": "single_attack", "beat_position": 4})

# Clap
MusicalEvent(type="clap", timestamp=1.72, duration=None, intensity=0.75,
             payload={"temporal_profile": "rattle", "beat_position": 4})

# Hi-hat
MusicalEvent(type="hihat", timestamp=1.5, duration=None, intensity=0.6,
             payload={"subtype": "closed", "decay_ms": 45, "beat_position": 2})

# Riser
MusicalEvent(type="riser", timestamp=45.0, duration=8.0, intensity=0.9,
             payload={"subtype": "noise_sweep", "slope_hz_per_sec": 150.0})

# Faller
MusicalEvent(type="faller", timestamp=77.0, duration=4.0, intensity=0.7,
             payload={"slope_hz_per_sec": -200.0})

# Stab
MusicalEvent(type="stab", timestamp=33.5, duration=0.12, intensity=0.8,
             payload={"harmonic_ratio": 0.6, "centroid_hz": 1200.0})

# Arp pattern
MusicalEvent(type="arp_pattern", timestamp=90.0, duration=16.0, intensity=0.75,
             payload={"rate": "16th", "period_beats": 0.25})
```

### Dependency Changes

| Package | Current | Change |
|---|---|---|
| librosa | Already installed | No change (spectral_flatness, bandwidth, HPSS all built-in) |
| scikit-learn | Not installed | **Add** (RandomForestClassifier, ~15MB) |
| joblib | Comes with scikit-learn | Model serialization |
| scipy | Already installed | `scipy.stats.linregress` for riser/faller slope |

Single new dependency: **scikit-learn**. Well-maintained, works on Apple Silicon natively.

---

## Revised Build Order (post-decisions)

| Phase | What | Effort | Dependencies |
|---|---|---|---|
| **Phase A** | Detector framework: interfaces, DetectorConfig, eval harness | 2-3 hours | None |
| **Phase B** | Add spectral_flatness + bandwidth + HPSS to feature extraction | 1-2 hours | None |
| **Phase C** | Heuristic drum detection (rule-based, no ML) | 2-3 hours | Phase A, B |
| **Phase D** | Riser + faller detection (centroid slope + section priors) | 2-3 hours | Phase A, B |
| **Phase E** | Stab detection (HPSS harmonic ratio) | 2-3 hours | Phase A, B |
| **Phase F** | Compact pattern storage + runtime expansion | 2 hours | Phase C |
| **Phase G** | RF classifier (alternative to Phase C heuristics) | 3-4 hours | Phase C (for seed labels), Phase A (eval framework) |
| **Phase H** | Training data pipeline: ENST-drums adapter, manual label tool | 2-3 hours | Phase A (eval framework) |

**Phase A is now first.** The detector framework + eval harness enables iterative tuning from day one. Without it, we'd build detectors with no way to measure or compare them.

**Phases C and D can run in parallel** once A+B are done. Phase G is the RF classifier that competes with Phase C's heuristics — both run through the eval framework for A/B comparison.

**Arp detection deferred to M8.** HPSS still included (Phase B) because it unlocks stab detection and may improve percussion accuracy.

---

## Decisions (Resolved 2026-03-20)

1. **Compact storage: YES.** Percussion stored as per-bar pattern arrays, not individual events. Runtime expansion to MusicalEvent objects when needed by downstream layers.

2. **Hi-hat granularity: Pattern-level only.** Open/closed classification, density, pattern type (8ths/16ths/roll) — not individual hit events. Keeps storage minimal, matches lighting use case.

3. **Training data: Test all approaches individually and in tandem.** Build heuristic, ENST-drums, and manual-label pipelines as separate strategies. Compare and optimize. This implies a **detector eval framework** is a first-class deliverable — not an afterthought.

4. **Arp detection: DEFERRED to M8.** Excluded from M7 scope.

5. **HPSS: YES, and explore pushing further.** ~500ms is acceptable. Brach wants to see cost/benefit analysis of extended HPSS usage beyond stab detection.

## Architectural Implication: Tunability

Brach's primary concern is that detection accuracy will require iteration. The system must be designed as a **detector workbench**, not a static pipeline:

- **Pluggable detector strategies** behind a common interface (e.g., heuristic kick detector vs RF kick detector can be swapped/A-B tested)
- **DetectorConfig** dataclass parameterizing thresholds, algorithm choice, and feature selection per event type
- **Eval framework** that scores detector output against ground truth labels, producing precision/recall/F1 per event type
- **Multiple training data sources** testable individually and in combination
- This is a research-grade system where the user (Brach) actively tunes algorithms — not a fire-and-forget feature

---

## Confidence Levels

| Finding | Confidence |
|---|---|
| Beat-synchronous classification is superior to continuous onset detection for SCUE | **HIGH** — fundamental advantage of known beatgrid |
| Skip madmom, use librosa + scikit-learn | **HIGH** — dependency risk, training data mismatch, cost |
| Riser detection via centroid slope + section priors | **HIGH** — well-characterized acoustic signature |
| RF classifier accuracy 85-92% for percussion | **MEDIUM-HIGH** — depends on training data quality/quantity |
| Stab detection via HPSS harmonic ratio | **MEDIUM** — untested on EDM-specific synth stabs |
| Arp detection via chroma autocorrelation | **MEDIUM** — accuracy varies significantly with mix density |
| Faller detection accuracy | **MEDIUM** — less distinctive signature than risers |
| Compact pattern storage feasibility | **HIGH** — standard data compression technique |
| Total compute budget ~1.2s on M-series | **MEDIUM-HIGH** — HPSS cost is librosa-benchmarked but not tested on SCUE tracks |
