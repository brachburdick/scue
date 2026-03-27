# Strata EDM Priors Migration Proposal

**Date:** 2026-03-26
**Source:** STRATA_migration_augment research document (EDM knowledge + beat grid exploitation)
**Companion:** `strata-research-migration.md` (algorithms & models — P0-P3 roadmap)
**Scope:** Replacing heuristic scoring with formal probabilistic structure analysis

---

## The Core Thesis

The current Strata pipeline treats structure analysis as a continuous signal-processing problem (allin1-mlx boundaries -> ruptures change-points -> energy scoring -> flow model relabeling). The research demonstrates that for EDM, this should be a **discrete sequence-labeling problem** on beat-quantized features, with genre-specific duration priors and transition constraints.

The payoff is enormous: **73% accuracy improvement** (EDMFormer vs. pop-centric models), **3000x search space reduction** (phrase-quantized vs. continuous), and **65-75% compute savings** (selective stem separation).

---

## What Currently Exists (and what it gets wrong)

| Component | Current Implementation | Limitation |
|-----------|----------------------|------------|
| Boundaries | allin1-mlx + ruptures CPD | Pop-music model, not EDM-aware |
| Section labeling | `flow_model.py` — scoring-based | Soft heuristic, no global optimization |
| Beat grid | Pioneer PQTZ via bridge | Used for enrichment, NOT for driving analysis |
| Phrase detection | 8-bar snap heuristic | Fixed 8-bar, no 16/32-bar awareness |
| Transition constraints | `VALID_TRANSITIONS` dict | Local check only, no Viterbi global optimum |
| Sub-genre awareness | None | Same priors for house, techno, dubstep |
| Drum pattern role | Pattern fingerprinting | Not used for section classification |
| Stem separation | Full-track in standard tier | No selective deployment |

---

## Proposed Changes — Ordered by Impact

### 1. Beat-Synchronous Feature Pipeline
**Priority:** P0 — Foundation for everything else
**Replaces:** Frame-level STFT in `energy.py`

The beat grid (Pioneer or madmom) should be the coordinate system for ALL feature extraction, not just an enrichment afterthought.

**Action:**
- New module `scue/layer1/strata/beat_features.py`
- Compute all features beat-synchronously: MFCCs, chroma (CQT), spectral centroid, sub-band energies, onset density — one vector per beat
- Aggregate to bar-level (mean over 4 beats) and phrase-level (mean over 16/32 beats)
- Self-similarity matrix at bar resolution: 192x192 for a 6-min track at 128 BPM (vs. ~15600x15600 frame-level)
- When Pioneer beat grid available, use it as primary. When not, use madmom output.

**Impact:** All downstream analysis operates on musically-meaningful units. Direct cosine similarity between bars reveals exact repeats vs. variations. SSM computation becomes trivial (<10ms).

### 2. EDM Structural Grammar (HMM/HSMM)
**Priority:** P0 — The single highest-impact change
**Replaces:** `flow_model.py` scoring heuristic + `VALID_TRANSITIONS` dict

The current flow model applies local scoring to relabel sections. The research shows that **Viterbi decoding with EDM transition probabilities finds the globally optimal label sequence**, preventing locally plausible but globally nonsensical results.

**Action:**
- New module `scue/layer1/strata/structure_hmm.py`
- States: `{intro, verse, build, drop, breakdown, fakeout, outro}`
- Transition matrix encoding EDM grammar:
  ```
  P(drop|build) ≈ 0.85    P(breakdown|drop) ≈ 0.5
  P(build|breakdown) ≈ 0.6  P(outro|intro) ≈ 0.0
  ```
- Duration priors (HSMM extension): probability mass peaked at 8, 16, 32-bar durations
- Emission model: P(features|section_type) from beat-synchronous spectral features
  - drop: high sub-bass, high onset density, kick present
  - breakdown: low sub-bass, low onset density, kick absent
  - build: rising spectral centroid, accelerating onset rate
  - intro/outro: bookend positions, moderate energy
- Viterbi decoding produces globally optimal section labels
- Confidence = difference between best and second-best path scores

**Impact:** Eliminates the multi-phase heuristic in `flow_model.py`. Global optimization prevents impossible transitions at zero extra compute. Duration priors enforce power-of-2 phrase lengths naturally.

### 3. Kick Activity Map for Instant Macro-Structure
**Priority:** P0 — Cheap, high-value
**Extends:** `energy.py` sub-band analysis

Research shows kick presence/absence at phrase boundaries alone achieves ~80% section classification. This should be the FIRST thing computed, before any expensive analysis.

**Action:**
- In `beat_features.py`: compute sub-bass energy (20-150 Hz) at each beat position
- Binary "kick map": 1 if sub-bass energy at beat exceeds threshold, 0 otherwise
- Aggregate to bar level: kick_ratio = fraction of beats with kick present
- At phrase boundaries: kick_ratio transition (present->absent = breakdown onset, absent->present = drop onset)
- Feed kick map as primary emission feature into HMM

**Impact:** Macro-structure is visible in <0.5s, before any ML models run. Provides strong prior for the HSMM even without stem separation.

### 4. Sub-Genre Classification & Template Selection
**Priority:** P1 — Sharpens all priors
**Currently:** No sub-genre awareness

BPM alone provides ~60% sub-genre classification. Combined with spectral features from Tier 0/1, this selects the right structural template.

**Action:**
- New module `scue/layer1/strata/genre.py`
- BPM-based initial narrowing (174 BPM = drum & bass, 125 = house, 140 half-time = dubstep)
- Feature-based refinement: beat-sync loudness, band ratios, spectral descriptors
- Output: sub-genre tag + corresponding structural template:
  - House/Techno: 4-on-the-floor, 16-32 bar phrases, gradual layering
  - Trance: 4-on-the-floor, extended breakdowns (32+ bars), long arcs
  - Dubstep: half-time drums, drop at ~bar 32, wobble bass
  - D&B: breakbeat (not 4-on-the-floor), shorter intense sections
  - Hardstyle: distorted kick, ABCDBCD format
- Template adjusts HSMM duration priors and transition matrix per sub-genre

**Impact:** Techno tracks get gradual-evolution priors (fewer discrete boundaries, longer segments). Dubstep tracks get half-time drum templates. Eliminates one-size-fits-all structural assumptions.

### 5. Conditional Event Detection
**Priority:** P1 — Upgrades transition detection
**Replaces:** Energy-delta-only classification in `transitions.py`

Current transition detection uses energy deltas across boundaries. The research formalizes high-confidence conditional detections.

**Action:**
- Extend `transitions.py` with conditional probability rules:
  - **Riser -> Drop**: Rising spectral centroid over 4-8 bars + phrase boundary = drop with P > 0.95
  - **Kick absence at phrase boundary**: Sub-bass below threshold = breakdown onset
  - **Kick return + energy spike at phrase boundary**: Drop with P > 0.9
  - **Increasing onset density at bars N-2..N of N-bar phrase**: Fill
  - **1-2 beat silence before energy max**: Drop impact point
- Each rule outputs a confidence score that feeds into the HMM emission model
- Rules are cheap (spectral features only, no stem separation needed)

**Impact:** Transition classification moves from "energy went up/down" to "buildup-to-drop confirmed by riser + kick return + energy spike." Much higher precision.

### 6. Selective Stem Separation (Knowledge-Guided)
**Priority:** P1 — Major compute savings
**Modifies:** `engine.py` standard tier orchestration

Current standard tier runs full-track HTDemucs. Research shows that with coarse structure from the HMM, stems are only needed at transition windows.

**Action:**
- After HMM produces section hypotheses from quick-tier features:
  1. Identify transition regions (4-6 per track, ~15s each)
  2. Run stem separation ONLY on those windows (~75s total vs. ~300s full track)
  3. Use separated stems to confirm/refine ambiguous transitions
  4. For unambiguous sections (confident HMM label), skip separation entirely
- For breakdown sections: only need kick-absence confirmation -> sub-bass check, no separation
- For buildups: spectral centroid trend suffices -> no separation
- Full-track separation reserved for deep tier only

**Impact:** Standard tier drops from ~60s to ~15-20s. Same quality at transition points where it matters. 65-75% compute reduction.

### 7. Phrase-Level Quantization Pipeline
**Priority:** P1 — Tightens search space
**Modifies:** `snap.py` 8-bar snapping

Current snapping is fixed at 8 bars. Research shows EDM phrases cluster at 8, 16, and 32-bar lengths, and the right quantization depends on sub-genre and section type.

**Action:**
- Replace fixed 8-bar snap with multi-resolution phrase quantization:
  - Candidate boundaries at 4, 8, 16, 32-bar positions from first downbeat
  - Score each candidate by audio evidence (Foote novelty at that position)
  - Bias by HSMM duration prior (intros prefer 16-32, builds prefer 4-16, etc.)
  - Select boundaries that minimize combined content cost + regularity cost (Sargent et al. approach)
- From bar-level SSM: detect repeating blocks to confirm phrase lengths

**Impact:** 32-bar sections (common in trance and techno) no longer get incorrectly split at bar 8. 4-bar fills no longer get merged into adjacent sections.

### 8. Pioneer Beat Grid as Primary Analysis Coordinate
**Priority:** P0 — Architectural shift
**Modifies:** The relationship between enrichment and analysis

Currently Pioneer data enriches AFTER analysis. The research argues it should drive analysis FROM THE START when available.

**Action:**
- When Pioneer PQTZ beat grid is available (from scanner or bridge):
  1. Use it as the coordinate system for ALL feature extraction (step 1 above)
  2. Skip madmom beat tracking entirely (Pioneer grid is near-perfect for EDM)
  3. Phase alignment from PQTZ `beat_number` field (1-4 position in bar)
  4. Only fall back to audio-derived grid when Pioneer data is unavailable
- Pioneer PSSI phrase data becomes the initial hypothesis for the HSMM, refined by audio features
- This inverts the current flow: Pioneer-first, audio-confirms (vs. audio-first, Pioneer-enriches)

**Impact:** Eliminates beat tracking errors. Phrase boundaries start from DJ-grade metadata. Analysis speed up from skipping madmom. This is the research document's central architectural insight.

---

## Research Datasets to Acquire

| Dataset | Size | Use |
|---------|------|-----|
| **EDM-CUE** | 4,710 tracks, 21,000 DJ-annotated cue points | Ground truth for phrase boundaries |
| **EDM-98** | 98 tracks, genre-specific taxonomy | Training/eval for section classification |
| **Harmonix Set** | 912 tracks | Beat/section evaluation benchmark |

These would enable training the HSMM emission model and evaluating against real DJ annotations.

---

## Models to Evaluate

| Model | Paper | Relevance |
|-------|-------|-----------|
| **EDMFormer** | Sajeer et al., arXiv 2603.08759, 2026 | EDM-specific transformer, 88.3% accuracy |
| **MuQ** | arXiv 2501.01108, 2025 | Foundation model, outperforms MERT on structure analysis |
| **SongFormer** | Hao et al., Oct 2025 | Current SOTA on SongFormBench, fine-tunable on EDM |
| **Beat This!** | Foscarin et al., ISMIR 2024 | SOTA beat/downbeat tracking |
| **DOSE** | 2025 | Transformer drum onset extraction |

---

## Implementation Sequencing

```
Phase A — Foundation (beat-sync + kick map + Pioneer-first):
  8 → Pioneer beat grid as primary coordinate
  1 → Beat-synchronous feature pipeline
  3 → Kick activity map

Phase B — Structure engine (the big win):
  2 → EDM structural grammar (HMM/HSMM)
  7 → Phrase-level quantization
  5 → Conditional event detection

Phase C — Optimization:
  4 → Sub-genre classification + template selection
  6 → Selective stem separation
```

Phase A can be done incrementally alongside existing code (feature pipeline runs in parallel, doesn't replace until validated). Phase B is the transformative change — the HSMM replaces `flow_model.py`. Phase C optimizes compute and sharpens priors.

---

## Relationship to Companion Proposal

`strata-research-migration.md` covers **algorithms and models** (stem separation quality, MERT/CLAP features, harmonic analysis, lighting output). This proposal covers **architectural paradigm** (beat-quantized discrete analysis, probabilistic structure inference, knowledge-guided computation).

They're complementary:
- Companion P0.3 (multi-scale Foote novelty) feeds into this proposal's item 7 (phrase quantization)
- Companion P1.5 (fusion engine) consumes this proposal's HSMM output as the offline analysis result
- Companion P0.2 (sub-stem drum separation) improves emission model quality for this proposal's item 2
- Companion P1.8 (energy + complexity scoring) provides richer emission features for the HSMM

Suggested combined ordering:
1. This proposal Phase A (foundation) — enables beat-sync features everywhere
2. Companion P0.1-P0.4 (model upgrades) — better raw analysis quality
3. This proposal Phase B (HSMM) — transforms classification accuracy
4. Companion P1 (fusion, foundation models) — enriches the pipeline
5. This proposal Phase C + Companion P2 — optimization and new capabilities

---

## Metrics for Success

| Metric | Current Baseline | Target | How to Measure |
|--------|-----------------|--------|----------------|
| Section boundary F-measure (3s tolerance) | ~0.65 (estimated) | 0.85+ | Evaluate on EDM-98 |
| Section label accuracy | ~45% (EDMFormer showed pop models get ~15%) | 80%+ | Per-frame accuracy on EDM-98 |
| Quick tier latency | ~3s | <1s | Timer in engine.py |
| Standard tier latency | ~60s | ~15s | Selective separation |
| Impossible transition rate | >0 (scoring allows them) | 0 | Count in test suite |
