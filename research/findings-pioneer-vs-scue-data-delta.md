# Pioneer-Only vs. SCUE-Analysis Data Quality Delta

**Date:** 2026-03-21
**Status:** Research complete
**Depends on:** M7 Event Detection (framework done, tuning pending), FE-Live-Deck-Monitor (in progress)

---

## 1. Feature Delta Table

### Pioneer ANLZ Waveform Tags (USB + Network)

| Tag | File | Entries | Bytes/Entry | Color Model | Hardware | Temporal Res |
|-----|------|---------|-------------|------------|----------|--------------|
| PWAV | .DAT | 400 fixed | 1 | Mono blue (5-bit height + 3-bit intensity) | CDJ-900+ | ~1.3/sec |
| PWV2 | .DAT | 100 fixed | 1 | Mono (4-bit height) | CDJ-900 | ~0.33/sec |
| PWV3 | .EXT | 150/sec | 1 | Mono blue (5-bit height + 3-bit intensity) | NXS+ | 150/sec |
| PWV4 | .EXT | 1,200 fixed | 6 | RGB + blue dual-layer | NXS2+ | ~4/sec |
| PWV5 | .EXT | 150/sec | 2 | 3-bit RGB (512 colors) + 5-bit height | NXS2+ | 150/sec |
| PWV6 | .2EX | 1,200 fixed | 3 | Low/mid/high 3-band frequency | CDJ-3000+ | ~4/sec |
| PWV7 | .2EX | 150/sec | 3 | Low/mid/high 3-band frequency | CDJ-3000+ | 150/sec |

### L1→L2 Contract Field Coverage

| Field | Pioneer Source | SCUE Source | Pioneer Available? | SCUE Advantage |
|-------|---------------|-------------|-------------------|----------------|
| **Waveform (visual)** | PWV5/PWV7: 3-bit RGB, 150/sec | RGB float32, 60/sec | YES, instant | 1000x color depth; continuous spectral decomposition |
| **Beat grid** | ANLZ beatgrid (USB) | Librosa beat tracking | YES, instant | Pioneer is ground truth — use it |
| **Downbeats** | Embedded in ANLZ | Librosa detection | YES, instant | Pioneer is ground truth |
| **BPM** | Exact from beatgrid | Librosa estimate (±5%) | YES, instant | Pioneer is ground truth |
| **Sections** | PSSI tags (.2EX, CDJ-3000+ only) | allin1-mlx + ruptures + EDM flow model | MAYBE — hardware-limited, untested | Consistent EDM taxonomy (intro/verse/build/drop/fakeout) |
| **Percussion events** | NOT available | Beat-sync RF classifier + heuristics | NO | Complete value-add: kick/snare/clap/hi-hat at 16th-note resolution |
| **Tonal events (riser/faller/stab)** | NOT available | Spectral slope + HPSS harmonic ratio | NO | Complete value-add |
| **Energy curve** | PWV height is a rough proxy | Per-band RMS @ ~2Hz | PARTIAL — height correlates | Explicit band-separated energy with float precision |
| **Key** | Camelot wheel (if in metadata) | Chroma-based analysis | MAYBE | Numeric + confidence score |
| **Mood / danceability** | NOT available | Placeholder (neutral) | NO | Future: richer descriptors via Tier 3 |

### Resolution Comparison (Key Dimensions)

| Dimension | Pioneer | SCUE | Ratio |
|-----------|---------|------|-------|
| Waveform temporal | 150 entries/sec | 60 fps | Pioneer 2.5x higher |
| Waveform color depth | 3-bit per channel (8 levels) | float32 per channel | SCUE ~1000x higher |
| Waveform bands | 3 (low/mid/high in PWV7) | N (configurable) | Comparable at default |
| Beat position precision | Sample-accurate | ±5% BPM tolerance | Pioneer wins |
| Section granularity | Phrase boundaries (PSSI) | Bar-snapped boundaries | Comparable |
| Event detection | None | 16th-note resolution | SCUE only |

---

## 2. Cue-Type Dependency Map

### Planned Cue Types and Their Input Requirements

| Cue Type | Input Features | Pioneer-Only Viable? | Quality Without Audio |
|----------|---------------|---------------------|----------------------|
| **section_change** | SectionInfo boundaries | YES if PSSI available (CDJ-3000+); NO on older hardware | Depends entirely on PSSI quality/availability |
| **section_anticipation** (N bars before boundary) | SectionInfo + BeatPosition | Same as above | Same as above |
| **section_progress** (25/50/75%) | SectionInfo + current position | Same as above | Same as above |
| **energy_level** (threshold crossing) | energy_curve (per-band RMS) | PARTIAL — PWV height as proxy | Degraded: no band separation, integer quantization |
| **drop_anticipation** (build→drop detection) | Riser detector + section labels | NO — riser detection requires spectral centroid slope | Impossible |
| **breakdown_detection** | Energy drop + percussion silence + section context | NO — requires percussion pattern analysis | Impossible |
| **beat-locked effects** | BeatPosition + MusicalEvents | PARTIAL — beats yes, events no | Beat sync works; event-reactive effects impossible |
| **percussion_pattern_cues** | DrumPattern (kick/snare/clap slots) | NO | Impossible |
| **intensity_tracking** | Multi-band energy + event density | NO — event density requires detector output | Severely degraded |

### Verdict: Cue Types by Data Source

- **Pioneer-only viable (3):** section_change, section_anticipation, section_progress — but ONLY with PSSI on CDJ-3000+
- **Partially viable (2):** energy_level (degraded), beat-locked effects (basic only)
- **Impossible without audio (4):** drop_anticipation, breakdown_detection, percussion_pattern_cues, intensity_tracking

---

## 3. PSSI Coverage Assessment

### What PSSI Provides
- Phrase boundaries (start/end times)
- Phrase labels (taxonomy: likely euphoria, build, break, etc. — exact labels need verification)
- Stored in `.2EX` ANLZ files

### Hardware Availability

| Hardware | PSSI Available? | Access Method |
|----------|----------------|---------------|
| CDJ-3000 / CDJ-3000X | YES | USB ANLZ (.2EX) + dbserver (AnalysisTagFinder) |
| XDJ-AZ | LIKELY YES | dbserver via beat-link v8.1.0+ (untested) |
| Opus Quad | LIKELY YES | USB ANLZ (.2EX) |
| CDJ-2000NXS2 | NO | No .2EX files |
| CDJ-2000NXS | NO | No .2EX files |
| XDJ-XZ | UNKNOWN | Needs testing |

### Network vs USB Access
- **dbserver:** AnalysisTagFinder queries work on CDJ-3000/XDJ-AZ per beat-link v8.1.0-SNAPSHOT
- **USB:** pyrekordbox can parse .2EX files directly (untested but straightforward)
- **Latency:** Both are instant once ANLZ files are loaded

### PSSI vs SCUE Sections Comparison

| Dimension | PSSI | SCUE (allin1-mlx + EDM flow) |
|-----------|------|------------------------------|
| Taxonomy | Pioneer's labels (needs verification) | EDM-specific: intro/verse/build/drop/breakdown/fakeout/outro |
| Consistency | Depends on rekordbox analysis version | Deterministic given same audio + params |
| Confidence scoring | Unknown | Yes, per-section confidence float |
| EDM optimization | General-purpose | Purpose-built for EDM structure |
| Fallback when unavailable | None | Always available (requires audio file) |

### Fallback When PSSI Unavailable
On older hardware without PSSI, section detection falls back entirely to SCUE's analysis pipeline. This means:
- NXS2-era hardware: no Pioneer sections at all → SCUE sections are the only option
- CDJ-3000: could use PSSI as validation/comparison against SCUE sections
- **Risk:** If SCUE sections diverge from PSSI, the DJ sees different boundaries than their hardware shows

---

## 4. Proposed Test Design

### Test Corpus Requirements

| Track Category | Count | Purpose |
|----------------|-------|---------|
| EDM (house/techno/trance) | 5 | Core use case: clear builds, drops, breakdowns |
| Bass music (dubstep/DnB) | 3 | Stress-test: complex percussion, irregular sections |
| Pop/crossover | 2 | Edge case: less predictable structure |
| Long tracks (>8 min) | 2 | Section count stress test |
| Tracks with Pioneer PSSI | 3+ | Required for PSSI comparison |

**Minimum viable corpus:** 10 tracks with both Pioneer ANLZ exports (from USB) and raw audio files.

### Comparison Pipeline

```
For each track:
  1. Export ANLZ from rekordbox USB → parse with pyrekordbox
  2. Run SCUE full analysis pipeline on raw audio
  3. Extract comparable features from both
  4. Compute delta metrics
  5. Generate comparison report (JSON)
```

### Metrics

| Comparison | Metric | Pass Threshold |
|------------|--------|----------------|
| Section boundary alignment | Offset in seconds between matched boundaries | <0.5s |
| Section boundary count | |Pioneer_count - SCUE_count| | ≤1 per track |
| Section label agreement | Confusion matrix (Pioneer label → SCUE label) | >70% agreement |
| Beat grid alignment | RMS jitter across all beats | <10ms |
| Waveform energy correlation | Pearson r between Pioneer height and SCUE RMS | >0.85 |
| Event coverage gap | Count of SCUE events with no Pioneer equivalent | Report only (expected: 100% gap) |

### Statistical Requirements
- **10 tracks minimum** for directional findings
- **30+ tracks** for genre-stratified statistical significance
- **Ground truth:** Human annotation of section boundaries and event onsets (at least 5 tracks)

---

## 5. Timing Recommendation

### The Key Distinction

There are two fundamentally different categories of findings in this comparison:

**Category A: Information-theoretic gaps (DURABLE — test anytime)**
These are facts about what data exists or doesn't exist, regardless of how well SCUE uses it:

| Finding | Why Durable |
|---------|-------------|
| Pioneer provides no percussion event data | Architectural fact of ANLZ format |
| Pioneer provides no tonal event data (riser/faller/stab) | Architectural fact of ANLZ format |
| PSSI is CDJ-3000+ only | Hardware generation constraint |
| PWV5 color depth is 3-bit per channel | ANLZ format spec, won't change |
| Pioneer beatgrid is sample-accurate; SCUE is ±5% | Algorithm property |
| Energy curve from Pioneer is height-only, no band separation | ANLZ format spec |

These findings are **true today and will be true after any amount of SCUE parameter tuning.** They define the ceiling of what Pioneer-only mode can achieve.

**Category B: Algorithmic quality gaps (PARAMETER-SENSITIVE — results shift with tuning)**
These measure how well SCUE exploits the data it has access to:

| Finding | Why Sensitive |
|---------|---------------|
| SCUE riser detection recall is X% | Changes with `min_slope`, `min_r_squared` tuning |
| SCUE section boundaries agree with PSSI at Y% | Changes with `ruptures_penalty`, flow model thresholds |
| SCUE percussion classification accuracy is Z% | Changes with RF training data, feature selection |
| SCUE energy curve correlates with Pioneer at r=N | Changes with band crossover frequencies, smoothing |

These numbers **will change as M7 event detection parameters are tuned.** Testing them now produces a snapshot, not a durable finding.

### Recommendation: Test the Durable Subset NOW

**Test now (Category A):**
1. Build the feature delta table (already done above — verify with actual ANLZ exports)
2. Confirm PSSI availability on your XDJ-AZ hardware
3. Verify which Pioneer data is accessible via dbserver vs USB-only
4. Document the information-theoretic ceiling for Pioneer-only mode

**Wait on (Category B):**
1. Riser/faller/stab detection accuracy comparisons — wait until M7 tuning is complete
2. Section boundary agreement percentages — wait until ruptures_penalty is dialed in
3. Percussion classification precision/recall — wait until RF classifier has real training data
4. Any "SCUE outperforms Pioneer by X%" claims

**Build now, populate later:**
1. Create the comparison harness/eval infrastructure (`tools/compare_pioneer_scue.py`)
2. Define the metrics and pass thresholds (they're stable)
3. Collect the test corpus (audio files + ANLZ exports)
4. Build human annotation tooling for ground truth

This way the test infrastructure is ready when M7 tuning completes, but you're not generating misleading baseline numbers that will be invalidated.

### Risk Assessment: Building Test Infrastructure Now

| Risk | Severity | Mitigation |
|------|----------|------------|
| Parameter changes invalidate baseline numbers | LOW | Baselines are cheap to regenerate; just re-run |
| Parameter changes invalidate test harness | VERY LOW | Harness compares features, not specific values |
| Parameter changes invalidate metric definitions | NEGLIGIBLE | Metrics (boundary offset, correlation, P/R) are algorithm-agnostic |
| Over-investing in comparison before core quality is proven | MEDIUM | Keep harness lightweight; don't build dashboards yet |

**Bottom line:** The test harness and corpus are durable investments. The numbers are cheap to regenerate. Build the infrastructure now; defer the benchmarking runs until M7 tuning is done.

---

## Summary

Pioneer and SCUE are **complementary, not competitive:**
- **Pioneer** provides instant visual fidelity (waveforms, beat grid) with zero latency
- **SCUE** provides semantic understanding (events, percussion patterns, EDM-aware sections) that enables intelligent cue generation
- **4 of 9 planned cue types are impossible** without SCUE's audio analysis
- **3 cue types work Pioneer-only** but only on CDJ-3000+ hardware with PSSI
- The information-theoretic gap (Category A) is testable and durable right now
- The algorithmic quality gap (Category B) should wait for M7 tuning completion
