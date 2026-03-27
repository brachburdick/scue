# Strata Musical Knowledge & Beat-Grid Fusion Proposal

**Date:** 2026-03-26
**Source:** Deep-research report — "Explicit Musical Knowledge and Beat-Grid Fusion as Strata Augmentation"
**Companion proposals:**
- `strata-research-migration.md` — algorithms & models (separation, MERT/CLAP, energy, ONNX)
- `strata-edm-priors-migration.md` — EDM structural grammar (HMM/HSMM, kick map, sub-genre, Pioneer-first)
- `strata-deep-research-evaluation-methodology.md` — eval harness, gold annotations, reproducibility

**Scope:** Beat-grid trust validation, musical-knowledge token streams for neural fusion, CRF decoding, rule-based pseudo-labeling, and three concrete experiment designs. Items here are *net-new* — not covered by companion proposals.

---

## What This Adds

The EDM priors proposal says "use the beat grid as primary coordinate" and "build an HSMM." This proposal asks: **what happens when the beat grid is wrong?** And: **how do you encode musical knowledge so a neural model can learn to weight it, rather than hard-coding rules?**

The key additions:
1. Beat-grid trust scoring and validation pipeline
2. Musical-knowledge token streams for transformer cross-attention fusion
3. CRF as alternative/complement to HSMM for global consistency
4. Rule detectors as weak supervisors (pseudo-labels for training)
5. Three experiment designs that isolate the value of each component

---

## 1. Beat-Grid Trust Scoring & Validation

**Gap:** The EDM priors proposal (item 8) makes Pioneer beat grid the primary coordinate system. But beat grids fail in predictable ways: wrong downbeat alignment, tempo octave errors (2x/0.5x), tempo drift on tracks with live-recorded elements, and accidental overwrites from re-analysis. A wrong grid silently corrupts every downstream computation.

**Action:**

### 1a. Trust Tier Classification
New module: `scue/layer1/strata/grid_trust.py`

Classify each track's beat grid into trust tiers:

| Tier | Source | Validation | Usage |
|------|--------|-----------|-------|
| A — Validated | Pioneer PQTZ + audio cross-check passes | Onset-alignment score > 0.8 | Hard coordinate system. Boundaries must land on bar lines. |
| B — Unvalidated | Pioneer PQTZ, no cross-check | None yet | Soft coordinate system. Boundaries *prefer* bar lines (regularization penalty). |
| C — Audio fallback | madmom or allin1-mlx estimated | N/A | Treat as noisy. Wider tolerance windows. No hard bar-line constraints. |

### 1b. Audio Cross-Validation Checks
For each beat position in the grid, compute:
- **Onset-alignment score:** spectral flux onset strength at the beat time. A correct beat grid should have high onset strength at most beat positions in EDM (especially downbeats with kicks).
- **Sub-bass periodicity check:** autocorrelation of 20-150 Hz energy should peak at the grid's beat period. If it peaks at 2x or 0.5x, flag tempo octave error.
- **Downbeat confidence:** compare spectral energy at beat_number=1 positions vs beat_number=2/3/4. In 4/4 EDM, beat 1 typically has distinct kick+bass emphasis. If beat 1 positions are indistinguishable from others, flag possible wrong downbeat alignment.

Output: `GridTrustResult(tier, onset_alignment_score, octave_error_flag, downbeat_confidence, issues[])`

### 1c. Cross-Source Agreement (when multiple sources available)
If both ANLZ and XML beat grids exist (e.g., from scanner + rekordbox export):
- Compare tempo curves: max divergence in BPM
- Compare downbeat times: cumulative drift over track duration
- Compare beat counts: total beats should match within ±1

Log disagreements to `eval_results/grid_disagreements.jsonl` for tracking.

### 1d. Degraded-Grid Sensitivity Testing
Add to eval harness (`tools/strata_eval.py --grid-sensitivity`):
- Run Strata analysis with correct grid, then with:
  - Downbeat shifted by +1 beat, +2 beats, +3 beats
  - Tempo doubled (octave error)
  - Random drift: ±10ms per beat accumulating over track
- Measure boundary F-measure and label accuracy degradation at each corruption level
- Defines the "grid error budget" — how wrong can the grid be before Strata breaks?

**Payoff:** Quantified trust in the most critical input. Prevents silent failures when Pioneer data is wrong. Informs whether to hard-constrain or soft-constrain based on measured grid quality.

---

## 2. Musical-Knowledge Token Streams

**Gap:** The EDM priors proposal encodes musical knowledge as HSMM transition/duration constraints — fixed rules. The research shows these can also be represented as **input features to a learned model**, letting the model learn *when* to trust each prior rather than always enforcing it.

**Action:**

### 2a. Knowledge Detectors (Rule-Based Feature Extractors)
New module: `scue/layer1/strata/knowledge_detectors.py`

Each detector operates on beat-synchronous features and outputs a per-bar score:

| Detector | Input | Output | Musical basis |
|----------|-------|--------|--------------|
| **Four-on-the-floor** | Sub-bass energy at each beat | Score 0-1: fraction of beats with kick | EDM loop convention — 4-beat kick pattern |
| **Snare-roll acceleration** | Onset density in 200-1000 Hz band, measured in windows of 4/2/1 bars | Score 0-1: normalized acceleration rate | Build-up signature — quarter→eighth→sixteenth snare |
| **Kick dropout** | Sub-bass energy drops to <15% of running average | Binary per bar + duration in bars | Breakdown/riser indicator — kick absent |
| **Bass reintroduction** | Sub-bass energy rises from <15% to >50% within 1 bar | Binary per bar | Drop indicator — full beat returns |
| **Filter sweep** | Spectral centroid slope over 4-8 bar window | Score: positive = opening, negative = closing | Build-up (rising) / breakdown entry (falling) |
| **Riser presence** | Spectral energy in 2-8 kHz, rising trend over 4+ bars | Score 0-1 | Build-up auxiliary indicator |
| **Layer count change** | Count of active stems (from quick-tier energy thresholds) | Delta per bar boundary | Arrangement transition — layers entering/exiting |

### 2b. Token Encoding for Neural Fusion
When feeding into a transformer model (deep tier / future work):
- Each bar gets a composite feature vector: `[audio_embedding, grid_features, knowledge_scores]`
  - `audio_embedding`: MERT or mel-spectrogram features (from companion P1.6)
  - `grid_features`: `[tempo, beat_in_bar, bar_in_phrase, grid_trust_tier, downbeat_confidence]`
  - `knowledge_scores`: the 7 detector outputs from 2a above
- Use **cross-attention** between the audio stream and the knowledge+grid stream
- The model learns to upweight knowledge detectors when they agree with audio evidence and downweight when they don't (e.g., four-on-the-floor detector is irrelevant for breakbeat D&B)

### 2c. Immediate Use Without Neural Model
Before any neural model exists, knowledge detectors feed directly into:
- The HSMM emission model (EDM priors proposal item 2) as additional emission features
- Transition detection (`transitions.py`) as weighted evidence alongside energy deltas
- Pattern discovery (`patterns.py`) as bar-level fingerprint components

**Payoff:** Musical knowledge becomes machine-readable, auditable, and gradable. Works as rule features today, becomes neural input tomorrow. No code thrown away when upgrading.

---

## 3. CRF Decoder as HSMM Alternative

**Gap:** The EDM priors proposal commits to HSMM (generative model). The research identifies CRFs (discriminative model) as a complementary option with different strengths.

**Action:**

### 3a. CRF Implementation
New module: `scue/layer1/strata/structure_crf.py`

- **Skip-chain CRF:** adds long-range edges between bars that have high self-similarity (repeating sections should get the same label). This enforces "if bar 16-32 sounds like bar 48-64, they're probably both drops."
- Feature functions:
  - Unary: knowledge detector scores + audio features per bar
  - Pairwise (adjacent): transition compatibility (same as HSMM transition matrix, but learned discriminatively)
  - Skip-chain: SSM-based similarity between distant bars → same-label bias
- Training: requires labeled data (gold set from eval proposal, or Pioneer phrases as weak labels)

### 3b. When to Use CRF vs HSMM
- **HSMM advantages:** works with zero labeled data (hand-tuned priors), explicit duration modeling, interpretable generative story
- **CRF advantages:** discriminative (directly optimizes labeling accuracy), handles overlapping features naturally, skip-chains capture global repetition structure
- **Recommended:** Start with HSMM (EDM priors proposal Phase B). Add CRF when gold annotation set exists (eval proposal item 2b). Compare on eval harness. Use whichever scores higher, or ensemble.

### 3c. Constrained Viterbi Wrapper
Whether using HSMM or CRF, wrap decoding in a constraint layer:
- Boundaries must be within ±1 beat of a downbeat (for Tier A grids)
- Boundaries must be within ±2 beats of a downbeat (for Tier B grids)
- No constraint for Tier C grids
- Section duration must be ≥4 bars (no micro-sections)
- No immediate label repetition (e.g., drop→drop without intervening breakdown)

**Payoff:** CRF captures "this section sounds like that section" globally — something HSMM alone cannot express. Constrained Viterbi wrapper works with either decoder.

---

## 4. Rule Detectors as Weak Supervisors

**Gap:** The companion proposals use Pioneer phrases as weak supervision and knowledge detectors as features. But knowledge detectors can also generate **pseudo-labels for training neural models**, reducing the need for hand-annotated data.

**Action:**

### 4a. Pseudo-Label Generation Pipeline
New script: `tools/strata_pseudo_labels.py`

For each track in Brach's library:
1. Run knowledge detectors (item 2a) on beat-sync features
2. Apply deterministic rules to generate section hypotheses:
   - Bars with kick dropout + riser presence → "build" label
   - Bars immediately after bass reintroduction + high energy → "drop" label
   - Bars with kick present + stable layer count → "verse" or "drop" (disambiguate by energy level)
   - First/last 16 bars → "intro"/"outro"
3. Run HSMM decoder over these pseudo-emissions to get globally consistent labels
4. Assign confidence: high where multiple detectors agree, low where ambiguous
5. Output: `pseudo_labels/{fingerprint}.pseudo.json` — same format as gold annotations but with confidence scores

### 4b. Training with Pseudo-Labels
When training any neural component (transformer emissions, CRF features, etc.):
- Use pseudo-labels as auxiliary training signal with label smoothing proportional to (1 - confidence)
- Co-teaching variant: train two models, each filters the other's noisy pseudo-labels
- Validate only against gold set — never against pseudo-labels

### 4c. Pseudo-Label Quality Tracking
As gold annotations grow (eval proposal item 2b), measure pseudo-label quality:
- Compare pseudo-labels against gold for annotated tracks
- Track boundary offset distribution and label confusion matrix
- If pseudo-label F1 > 0.7 against gold, they're useful for training. Below that, investigate which detectors are failing.

**Payoff:** Turns an unlabeled DJ library into a weakly labeled training set. Scales annotation effort from 20 gold tracks to hundreds of pseudo-labeled tracks.

---

## 5. Three Experiment Designs

These follow the experiment template from the eval methodology proposal. They're designed to isolate the value of each new component.

### Experiment A: Beat-Grid Value Quantification

**Goal:** How much does a correct beat grid improve Strata vs. no grid / noisy grid?

**Dataset:** 20-track gold set (eval proposal) + degraded grid variants (item 1d above)

**Conditions:**
1. No grid — frame-based features, seconds-based boundaries
2. Correct grid — beat-sync features, bar-aligned boundaries
3. Shifted downbeat (+1 beat) — tests downbeat sensitivity
4. Tempo octave error (2x) — tests tempo sensitivity
5. Accumulated drift (±10ms/beat) — tests stability under gradual error

**Metrics:** Boundary HR@0.5s, HR@3s, label accuracy, stability (flip-rate), boundary jitter

**Hypothesis:** Condition 2 >> Condition 1 for all metrics. Conditions 3-5 degrade gracefully if grid trust scoring routes to soft constraints.

**Decision:** If correct grid improves HR@0.5s by >10% over no-grid baseline, Pioneer-first architecture (EDM priors item 8) is validated. If degraded grids cause >20% regression, trust scoring (item 1) is essential.

### Experiment B: Knowledge Detectors as Emission Features

**Goal:** Do explicit musical-knowledge features improve section labeling beyond raw audio features alone?

**Dataset:** 20-track gold set

**Conditions:**
1. Audio features only → HSMM decoder
2. Audio + knowledge detector scores → HSMM decoder
3. Knowledge detectors only → HSMM decoder (no audio — how far do rules alone get?)
4. Audio + knowledge → CRF decoder (if implemented)

**Metrics:** Per-beat label accuracy, per-section-type F1 (especially build/drop/breakdown), false positive events/min

**Hypothesis:** Condition 2 > Condition 1, especially for build-up and drop detection. Condition 3 alone achieves >60% accuracy (proving detectors carry real information).

**Decision:** If knowledge detectors improve drop/build F1 by >15%, encode them as standard emission features in all tiers. If Condition 3 alone exceeds 70%, the quick tier can rely primarily on detectors without ML models.

### Experiment C: Pseudo-Label Utility

**Goal:** Can pseudo-labels from rule detectors improve a trained model vs. gold-only training?

**Dataset:** 20 gold tracks + 200 pseudo-labeled tracks from Brach's library

**Conditions:**
1. Train on 20 gold tracks only
2. Pretrain on 200 pseudo-labeled tracks → fine-tune on 20 gold tracks
3. Train on 20 gold + 200 pseudo-labeled (joint, with confidence weighting)

**Metrics:** Label accuracy and boundary F on a held-out 5-track gold subset

**Hypothesis:** Conditions 2 and 3 > Condition 1, because pseudo-labels provide genre-relevant distributional coverage even if individual labels are noisy.

**Decision:** If pseudo-labels improve metrics, roll into standard training pipeline. If not, they're still useful as initialization for the HSMM (already planned) — just not for neural training.

---

## Implementation Sequencing

```
Phase 1 — Grid Trust (before EDM priors Phase A):
  1a → Grid trust classification module
  1b → Audio cross-validation checks
  1d → Degraded-grid sensitivity test (Experiment A)

Phase 2 — Knowledge Detectors (alongside EDM priors Phase B):
  2a → Seven knowledge detectors
  2c → Feed into HSMM emissions immediately
  Experiment B → Measure detector value

Phase 3 — Pseudo-Labels (after eval proposal Phase 2):
  4a → Pseudo-label generation pipeline
  4c → Quality tracking against gold set
  Experiment C → Measure pseudo-label utility

Phase 4 — Neural Fusion (when deep tier work begins):
  2b → Token encoding for transformer cross-attention
  3a → CRF decoder implementation
  3b → HSMM vs CRF comparison
  1c → Cross-source agreement (when multiple grid sources exist)
```

**Critical dependency:** Phase 1 must complete before the EDM priors proposal makes Pioneer grid the hard coordinate system. Without trust scoring, a wrong grid silently corrupts everything.

---

## Relationship to Companion Proposals

| This proposal | Feeds into / validates... | In companion proposal... |
|--------------|--------------------------|-------------------------|
| Grid trust scoring (1a-1b) | Safety net for Pioneer-first architecture | EDM priors item 8 |
| Grid sensitivity test (1d) | Quantifies risk of hard grid constraints | EDM priors items 1-2 |
| Knowledge detectors (2a) | Additional emission features for HSMM | EDM priors item 2 |
| Knowledge detectors (2c) | Better transition classification | EDM priors item 5 |
| Token streams (2b) | Input for MERT-based deep tier | Research migration item 6 |
| CRF decoder (3a) | Alternative to HSMM, uses same features | EDM priors item 2 |
| Constrained Viterbi (3c) | Shared decoding wrapper | EDM priors items 2, 7 |
| Pseudo-labels (4a) | Training data for any learned component | Eval methodology item 2 |
| Experiments A-C | Validation via eval harness | Eval methodology item 1c |

---

## New Files Created

| File | Purpose |
|------|---------|
| `scue/layer1/strata/grid_trust.py` | Beat-grid trust scoring and validation |
| `scue/layer1/strata/knowledge_detectors.py` | Seven rule-based musical-knowledge feature extractors |
| `scue/layer1/strata/structure_crf.py` | CRF decoder for section labeling (Phase 4) |
| `tools/strata_pseudo_labels.py` | Pseudo-label generation from rule detectors |
| `eval_results/grid_disagreements.jsonl` | Cross-source grid agreement tracking |
| `pseudo_labels/` | Per-track pseudo-label annotations |

---

## Dependencies

| Item | Dependency | Risk |
|------|-----------|------|
| 1b (audio cross-validation) | librosa onset detection | Low — already in stack |
| 1d (sensitivity test) | Eval harness (eval methodology proposal Phase 1) | Medium — must build eval first |
| 2a (knowledge detectors) | Beat-sync features (EDM priors item 1) | Medium — build together |
| 3a (CRF) | Gold annotation set (eval methodology item 2b) | Medium — needs training data |
| 4a (pseudo-labels) | Knowledge detectors (2a) + HSMM (EDM priors item 2) | Depends on both — Phase 3 timing |

---

## Open Questions for Brach

1. **Meter assumption:** Can we assume 4/4 for all tracks, or must the system handle 3/4, 6/8, etc.? (Affects bar-level feature computation and HSMM duration priors.)
2. **Grid sources in practice:** Which grid sources are actually available? Pioneer PQTZ via bridge only? Or also ANLZ files from scanner? Rekordbox XML exports? This determines whether cross-source agreement (1c) is feasible.
3. **Acceptable flicker rate:** What's the maximum label-flip-rate (changes per minute) that's tolerable for lighting? This defines the stability constraint for all decoders.
4. **Pseudo-label library size:** How many tracks in the DJ library could be pseudo-labeled? 200? 500? More data = better pseudo-labels, but diminishing returns.
