# Strata Research Migration Proposal

**Date:** 2026-03-26
**Source:** STRATA_migration research document (comprehensive technical blueprint)
**Scope:** Gaps between research findings and current SCUE Strata implementation

---

## Current State Summary

SCUE Strata already has a solid foundation:
- 3 analysis tiers (quick/standard/deep) + 2 live tiers
- HTDemucs stem separation in standard tier
- Energy analysis, pattern discovery, transition detection
- Pioneer integration via beat-link bridge with live strata
- Heuristic + Random Forest percussion detectors
- Full REST + WS API, frontend with comparison/editing/batch

This proposal identifies **what the research unlocks that we don't have yet**, organized as concrete work items with priorities.

---

## P0 — High-Impact, Low-Effort (leverage existing infrastructure)

### 1. Tiered Stem Separation Model Selection
**Gap:** Standard tier uses only HTDemucs. Research shows SCNet achieves 9.0 dB SDR at 48% CPU time with 25% parameters.
**Action:**
- Add SCNet as the standard-tier separator (faster library processing)
- Keep HTDemucs for deep tier
- Add ensemble mode for deep tier: Mel-Band RoFormer for vocals, HTDemucs for drums/bass/other
- Config in `scue/layer1/strata/separation.py` — model selection by tier

**Payoff:** 2x faster standard-tier analysis. Deep tier jumps from ~9 dB to ~12 dB SDR.

### 2. Sub-Stem Drum Separation (Kick/Snare/HiHat)
**Gap:** Current percussion detectors use heuristic spectral analysis on the drum stem. Research identifies DrumSep models (HTDemucs/MDX23C/SCNet XL variants on MVSEP) that physically separate kick/snare/hats/cymbals.
**Action:**
- Add hierarchical separation: drums stem -> DrumSep -> kick/snare/hats/cymbals
- Replace or augment `percussion_heuristic.py` and `percussion_rf.py` with actual separated sub-stems
- Feed separated sub-stems into pattern discovery (`patterns.py`) for cleaner drum pattern fingerprints

**Payoff:** Pattern detection accuracy jumps significantly. Currently the weakest link in arrangement analysis.

### 3. Foote Novelty with Multi-Scale Kernels
**Gap:** Research emphasizes multi-kernel-size Foote novelty for capturing both fine (4-bar) and coarse (16-bar) phrase boundaries simultaneously. Current section detection uses a single scale.
**Action:**
- In `scue/layer1/analysis.py` section detection, add parallel Foote novelty at L=16, L=32, L=64 beats
- Combine novelty curves (weighted sum or peak union) before boundary picking
- Constrain all boundaries to bar lines (already partially done)

**Payoff:** Better phrase boundary detection, especially for EDM tracks with nested sub-phrases within larger sections.

### 4. ONNX Export for Separation Models
**Gap:** Research documents mature ONNX export path (`demucs.onnx`) with 1.3-2.9x CPU speedup and CUDA/WebGPU providers.
**Action:**
- Add ONNX Runtime inference path in `separation.py` alongside PyTorch
- Auto-detect GPU availability and select provider (CUDA > CPU)
- FP16 mixed precision for all non-STFT operations (<0.1 dB loss)

**Payoff:** 2-3x speedup on batch library processing. Moves toward Windows compatibility (ONNX is platform-agnostic).

---

## P1 — Medium Effort, Significant Quality Improvement

### 5. Real-Time Fusion Engine with Priority-Weighted Conflict Resolution
**Gap:** Research specifies a formal fusion hierarchy: User Edits > Hardware Beats > Offline Analysis > Real-Time Audio. Current `live_analyzer.py` builds from Pioneer data but doesn't formally merge with offline analysis results.
**Action:**
- New module `scue/layer1/strata/fusion.py`
- Inputs: cached ArrangementFormula (any tier), Pioneer PlayerState, real-time audio features, user edits
- Priority resolution: when Pioneer says phrase boundary at bar 64 but offline says bar 66, apply Bayesian fusion with confidence scores
- Tolerance window: <4 beats discrepancy -> snap to nearest shared downbeat; >4 beats -> flag for review
- Output: unified ArrangementFormula with source attribution per data point

**Payoff:** The "Path 5 (Combination)" from the research — the target architecture for production use.

### 6. Foundation Model Feature Extraction (MERT)
**Gap:** MERT (330M params) achieves SOTA across 14 MIR tasks. Current feature extraction is hand-crafted (MFCCs, chroma, spectral features). MERT embeddings would improve event classification.
**Action:**
- Add MERT as optional feature extractor in deep tier
- Extract 1024-dim embeddings at 75 features/second
- Use different transformer layers for different tasks (early=timbre, late=structure)
- Feed MERT features into event classifier alongside existing hand-crafted features

**Payoff:** Better event classification (drops, breakdowns, buildups) without needing more labeled training data. Foundation model representations generalize better than hand-crafted features.

### 7. CLAP Zero-Shot Section Classification
**Gap:** CLAP enables zero-shot classification — compare audio segments to text descriptions like "EDM drop with heavy bass" or "atmospheric breakdown" without training data.
**Action:**
- Add CLAP-based section labeling as validation/supplement to rule-based classification
- Text prompts: "EDM drop", "breakdown section", "buildup with rising filter", "intro", "outro"
- Use T-CLAP or CoLLAP variants for temporal awareness over longer windows
- Confidence scores feed into fusion engine

**Payoff:** Semantic section labels without manual training data. Catches classification errors from rule-based system.

### 8. Composite Energy + Complexity Scoring
**Gap:** Research defines a formal composite complexity score and energy scoring model. Current `energy.py` does 3-band RMS + onset density. Missing: spectral entropy, syncopation, chord change rate, timbral variance.
**Action:**
- Extend `energy.py` with: spectral entropy, spectral flux, spectral rolloff, mel-bands crest/kurtosis
- New `complexity.py`: weighted combination of spectral entropy, syncopation (LHL model), onset density, chord change rate (HPCP entropy), timbral variance (MFCC variance)
- Map frame-level features to section-level aggregates, normalize to 1-10 scale
- Generate energy narrative: detect buildups (rising), drops (peak), plateaus (sustained), dips (troughs)

**Payoff:** Richer ArrangementFormula with per-section complexity and energy scores. Direct input for Layer 2 cue generation and lighting mapping.

---

## P2 — Larger Effort, Future Capabilities

### 9. Real-Time Causal Stem Separation (Band-SCNet)
**Gap:** Band-SCNet achieves 7.79 dB SDR at 92ms latency with only 2.59M parameters. Current live tier uses no stem separation.
**Action:**
- Integrate Band-SCNet for live mixer output monitoring
- Feed real-time separated stems into live strata for layer activity detection
- Use causal model output for validation against precomputed non-causal results

**Payoff:** Live tier upgrades from Pioneer-phrase-only to actual audio-informed arrangement tracking. Enables live layer activity visualization during DJ sets.

### 10. Harmonic Analysis Pipeline
**Gap:** Research details CQT chromagram, CENS features, Tonnetz, HCDF for harmonic tracking. Current analysis has basic key detection but no harmonic change tracking.
**Action:**
- Add `harmonic.py` to strata: CQT chroma, HCDF (harmonic change detection function), Tonnetz features
- Detect harmonic section transitions (HCDF peaks mark chord/key changes)
- Track harmonic content per section for the ArrangementFormula
- Key detection improvement: analyze each octave independently (Mixed In Key approach)

**Payoff:** Harmonic transitions become arrangement events. Critical for Layer 2 cue generation (color palette changes on key changes).

### 11. Syncopation & Groove Quantification
**Gap:** Research describes Longuet-Higgins & Lee syncopation model and microtiming groove analysis. Not implemented.
**Action:**
- Add syncopation scoring per bar using LHL metrical weight model
- Compare per-bar rhythmic fingerprints (onset positions on 1/16 grid) via cosine similarity for variation detection
- Feed into pattern discovery for distinguishing exact repeats vs. variations

**Payoff:** Quantified "groove" metric per section. Variation classification becomes precise rather than heuristic.

### 12. Lighting/OSC Output Bridge
**Gap:** Research maps ArrangementFormula features directly to lighting parameters. SCUE has Layer 3/4 stubbed but not connected.
**Action:**
- Define OSC message schema mapping: section boundaries -> scene changes, energy level -> intensity, frequency content -> color (bass=warm, treble=cool), onsets -> flash triggers
- Implement `scue/layer4/osc_bridge.py` using python-osc
- Support ArtNet/sACN output via OLA (Open Lighting Architecture)
- Connect ArrangementFormula events to real-time OSC stream during playback

**Payoff:** First end-to-end path from track analysis to lighting output. Validates the entire SCUE pipeline.

---

## P3 — Research Track (Watch / Prototype)

### 13. Graph Neural Networks for Structure Analysis
**Status:** AnalysisGNN and GraphMuse are symbolic-only but the paradigm could extend to audio features. Monitor for audio-domain implementations.

### 14. Multi-Source Diffusion Models for Separation
**Status:** Not yet competitive with discriminative models on SDR. Watch for improvements. Potential for conditional re-synthesis (generating missing stems).

### 15. SAM Audio (Meta)
**Status:** Foundation model for general audio separation with text/visual/temporal prompting. If it matures, could replace the entire model-selection complexity in separation.py.

### 16. Knowledge Distillation for Mel-Band RoFormer
**Status:** 2025 paper demonstrates windowed sparse attention student model. Could bring RoFormer quality to near-real-time speeds. Prototype when weights are available.

---

## Implementation Sequencing

```
Phase 1 (P0 items — immediate value):
  1 → Tiered model selection
  2 → Sub-stem drum separation
  3 → Multi-scale Foote novelty
  4 → ONNX export

Phase 2 (P1 items — quality leap):
  5 → Fusion engine
  8 → Energy + complexity scoring
  6 → MERT feature extraction
  7 → CLAP zero-shot classification

Phase 3 (P2 items — new capabilities):
  9  → Real-time causal separation
  10 → Harmonic analysis
  11 → Syncopation/groove
  12 → Lighting/OSC bridge (Layer 3/4 activation)

Ongoing: Monitor P3 research items, prototype when practical.
```

---

## Dependencies & Risks

| Item | Key Dependency | Risk |
|------|---------------|------|
| 1 (SCNet) | Model weights availability | Low — published, MVSEP hosted |
| 2 (DrumSep) | MVSEP model access | Low — multiple architectures available |
| 4 (ONNX) | STFT op rewriting | Medium — demucs.onnx project solved this but may need updates |
| 6 (MERT) | HuggingFace model, GPU memory | Medium — 330M params, needs ~2GB VRAM |
| 7 (CLAP) | Model selection, prompt engineering | Low — LAION-CLAP well-documented |
| 9 (Band-SCNet) | Causal model weights, real-time audio input | Medium — integration with existing audio pipeline |
| 12 (OSC/Lighting) | Layer 3/4 architecture decisions | High — requires Layer 2 cue stream first |

---

## Windows Compatibility Notes

Items that improve Windows story:
- **ONNX export (#4)** — platform-agnostic inference, replaces PyTorch dependency
- **SCNet (#1)** — lighter model, lower GPU requirements
- **MERT (#6)** — standard HuggingFace, works on Windows

Items that add macOS risk:
- **None** — all proposed items use cross-platform libraries

---

## Metrics for Success

Each item should be validated by:
1. **SDR improvement** (for separation items): A/B test on 10-track test set
2. **Boundary F-measure** (for structure items): compare against human-labeled phrase boundaries
3. **Event classification accuracy** (for detection items): precision/recall on labeled EDM sections
4. **Latency** (for real-time items): end-to-end measurement under load
5. **Subjective quality** (for all): Brach's evaluation on real DJ library tracks
