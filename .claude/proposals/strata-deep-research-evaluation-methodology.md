# Strata Evaluation & Methodology Proposal

**Date:** 2026-03-26
**Source:** Deep-research report on Strata problems and experiments
**Companion proposals:**
- `strata-research-migration.md` — algorithms & models (P0-P3 roadmap)
- `strata-edm-priors-migration.md` — EDM priors & architectural paradigm (HMM/HSMM)

**Scope:** What the deep-research report adds that the companion proposals don't cover — evaluation harness, reproducibility, weak-label robustness, dataset strategy, and experiment design methodology.

---

## Why This Matters

The companion proposals answer *what* to build. This proposal answers *how to know if it's working*. Without a formal evaluation harness, every Strata improvement will be judged by Brach eyeballing results on a handful of tracks — slow, non-reproducible, and biased toward tracks he knows well. The deep-research report provides a rigorous framework for measuring progress.

---

## 1. Formal Evaluation Harness

**Gap:** Strata has 399 passing tests but zero structured quality metrics. No boundary F-measure, no label accuracy, no per-tier regression tracking. The test suite checks "does it run" not "is it good."

**Action:**

### 1a. Evaluation Metrics Module
New module: `scue/layer1/strata/eval_metrics.py`

Implement (using `mir_eval` where possible):
- **Boundary hit-rate F-measure** at 0.5s and 3s tolerances (MIREX standard)
- **Section label accuracy** — frame-level and segment-level agreement
- **Hierarchical boundary/label metrics** via `mir_eval.hierarchy` (for multi-level structure when deep tier ships)
- **Layer activity F1** — per-stem multi-label classification (micro and macro F1)
- **Pattern match precision/recall** — do discovered patterns correspond to annotated repeats?
- **Transition detection precision/recall** — at 0.5s and 3s tolerances

### 1b. Show-Control-Specific Metrics
Standard MIR metrics miss what matters for lighting. Add:
- **Stability / anti-flicker** — count label changes within a 2-bar sliding window; penalize rapid oscillation
- **Boundary jitter** — standard deviation of boundary timing error across repeated analyses of the same track
- **Worst-case latency** — max time between a real transition and the system reporting it (critical for live tier)
- **Mistake cost asymmetry** — weight false-positive transitions higher than false-negatives (a phantom "drop" fires every fixture; a missed "drop" just means static lighting continues)

### 1c. Evaluation Runner
New script: `tools/strata_eval.py`
- Takes a manifest of tracks + gold annotations
- Runs specified tier(s) on each track
- Outputs per-track and aggregate metrics with bootstrap 95% CIs
- Saves results to `eval_results/{run_id}.json` for regression tracking
- Supports `--compare` flag to run paired Wilcoxon signed-rank tests between two result sets

**Payoff:** Every future Strata change can be measured against a baseline. Regression detection becomes automated.

---

## 2. Gold Annotation Set

**Gap:** No human-verified reference annotations exist for Strata outputs. All evaluation is informal.

**Action:**

### 2a. Annotation Format
Define in `docs/strata-annotation-format.md`:
- Beat-synchronous section boundaries (bar index + beat offset)
- Section labels from Strata vocabulary: `{intro, verse, build, drop, breakdown, fakeout, outro}`
- Per-bar layer activity bitmap: `[kick, snare, hats, bass, vocals, synth_lead, synth_pad, fx]`
- Transition type at each boundary
- Energy level (1-5 scale) per section
- Hierarchical annotations optional (phrase-level and section-level boundaries)

### 2b. Annotation Workflow
- Start with 20 tracks from Brach's DJ library spanning sub-genres (house, techno, trance, D&B, dubstep)
- Use Pioneer phrase analysis + Strata quick-tier output as initial draft
- Brach corrects to gold standard (the existing edit mode in StrataPage can export corrections)
- Store in `tests/fixtures/strata_gold/{fingerprint}.gold.json`
- Track annotation provenance: `{annotator, date, source_tier, corrections_made}`

### 2c. Public Dataset Acquisition
For benchmarking against published results (not for replacing Brach's annotations):

| Dataset | Tracks | What it provides | License | Priority |
|---------|--------|-----------------|---------|----------|
| Harmonix Set | 912 | Beats, downbeats, functional sections | Features only (no audio) | P0 — structure baseline |
| SALAMI | 1,359 | Hierarchical structural annotations | Annotations only | P1 — hierarchical eval |
| MedleyDB | 122 | Multitrack + instrument activations | CC-BY-NC-SA | P1 — layer detection |
| MUSDB18 | 150 | 4-stem separation ground truth | Research use | P0 — separation quality |
| EDM-CUE | 4,710 | DJ-annotated cue points | Check license | P1 — EDM boundaries |

**Payoff:** Reproducible evaluation. Enables comparing Strata against published systems.

---

## 3. Weak-Label Robustness for Pioneer Phrase Analysis

**Gap:** The EDM priors proposal (item 8) uses Pioneer PSSI phrase data as initial hypothesis for the HSMM. But the deep-research report warns that phrase analysis can be inconsistent and treating it as truth bakes in systematic errors.

**Action:**

### 3a. Quantify Phrase Analysis Noise
- Compare Pioneer phrase boundaries against gold annotations for the 20-track set
- Measure: boundary offset distribution, label confusion matrix, missing/extra boundary rates
- Document in `docs/pioneer-phrase-noise-profile.md`

### 3b. Noise-Robust Training
When training the HSMM emission model (EDM priors proposal item 2):
- Treat Pioneer phrases as **weak supervision**, not ground truth
- Use **label smoothing** on Pioneer-derived section labels (e.g., 0.8 confidence instead of 1.0)
- Implement **co-teaching** if training any neural components: two networks filter each other's noisy labels
- Validate all trained models against the gold set, never against Pioneer-only labels

### 3c. Disagreement Tracking
- When Pioneer phrase boundaries disagree with audio-derived boundaries by >2 bars, log to `eval_results/disagreements.jsonl`
- Track disagreement rate over time as a pipeline health metric
- High disagreement rate on a track = flag for manual review

**Payoff:** Prevents the HSMM from learning Pioneer's mistakes. Builds a calibrated understanding of when to trust hardware metadata.

---

## 4. Reproducibility Framework

**Gap:** Strata analysis results aren't fully reproducible. Different runs can produce different results due to floating-point non-determinism in stem separation, uncontrolled library versions, and no fixed preprocessing definitions.

**Action:**

### 4a. Analysis Manifest
Every Strata run should record in the ArrangementFormula metadata:
- `librosa_version`, `demucs_version`, `torch_version` (already have `stem_separation_model`)
- `sample_rate`, `hop_length`, `beat_sync_method` (Pioneer grid vs. madmom vs. allin1)
- `random_seed` (if any stochastic component is used)
- `config_hash` — SHA256 of the YAML config used for tunable parameters

### 4b. Config-as-Code for Pipeline Parameters
Currently tunable parameters are scattered across modules. Consolidate:
- Move all thresholds from `docs/strata-pipeline.md` into `config/strata.yaml`
- Engine reads config at init, stores config hash in output
- Changing a threshold = changing config, which changes the hash, which makes old/new results distinguishable

### 4c. Deterministic Preprocessing Script
New: `tools/strata_preprocess.py`
- Given a track, produces a deterministic feature bundle (mel, CQT, chroma, beat-sync features)
- Saves to `cache/features/{fingerprint}.features.npz`
- If features exist and config hash matches, skip recomputation
- Ensures two runs with same config produce byte-identical features

**Payoff:** "It worked on my machine" becomes impossible. Every result is traceable to inputs + config.

---

## 5. Experiment Design Template

**Gap:** The companion proposals list 20+ work items but don't specify how to evaluate each one in isolation. The deep-research report provides a per-experiment structure.

**Action:**

Create `docs/strata-experiment-template.md` with this structure (to be copied per experiment):

```markdown
# Experiment: [ID] — [Short Name]

## Goal
What capability does this isolate?

## Hypothesis
What do we expect to happen and why?

## Dataset
- Tracks: [subset of gold set / specific public benchmark]
- Split: [train/val/test if training involved]

## Baselines
- Current Strata [tier]: run eval harness, record metrics
- No-learning baseline: [e.g., novelty on SSM for structure]

## Method
- [Specific implementation changes]

## Evaluation
- Primary metric: [e.g., boundary F@3s]
- Secondary metrics: [stability, latency, cross-genre]
- Statistical test: [paired Wilcoxon on per-track scores, bootstrap 95% CI]

## Ablations
- [Remove component X, measure delta]

## Decision Criteria
- Ship if: [metric threshold + passes regression]
- Iterate if: [promising but below threshold]
- Pivot if: [fails critical constraint]

## Results
[Filled in after running]
```

**Payoff:** Every Strata improvement gets the same rigor. Prevents "I think it's better" conclusions.

---

## 6. Metric-Perception Alignment

**Gap:** The deep-research report cites work showing boundary F-measure doesn't always align with how humans perceive boundary correctness. Strata's downstream consumer is lighting/lasers — perceptual relevance matters more than academic metrics.

**Action:**

### 6a. Application-Aligned Scoring
Define a **show-control score** that weights metrics by downstream impact:
- Transition timing error × cost_weight (drop timing matters more than intro/outro boundary)
- Layer activity accuracy × visibility_weight (drums matter most for strobes, vocals for spotlights)
- Energy narrative correctness × 1.0 (directly drives intensity curves)
- Stability score × 2.0 (flicker is the worst possible failure mode for lighting)

Weights are configurable in `config/strata_eval.yaml`.

### 6b. Lightweight Perceptual Checks
For top candidates after automated eval:
- Play track with Strata overlay in StrataPage
- Brach rates each section boundary: correct / early / late / missing / phantom
- Each transition: correct type / wrong type / missing / phantom
- Aggregate into a "perceptual agreement" score
- 10-track spot-check per major change, not every commit

**Payoff:** Prevents optimizing for metrics that don't matter. Keeps evaluation grounded in the actual use case.

---

## 7. Tier Comparison Framework

**Gap:** The comparison view in StrataPage exists but there's no systematic way to measure quality differences between tiers or track improvement over time.

**Action:**

### 7a. Tier Regression Dashboard
Extend `tools/strata_eval.py` with `--dashboard` flag:
- Runs all tiers on the gold set
- Produces an HTML report (like the token dashboard) showing:
  - Per-tier metrics (boundary F, label accuracy, layer F1, stability)
  - Tier-vs-tier improvement (quick→standard, standard→deep)
  - Per-track outliers (tracks where a tier performs unusually badly)
  - Historical trend (if previous eval results exist)

### 7b. Automatic Regression Gate
Add to CI or pre-commit hook:
- If a strata module changes, run eval on a 5-track fast subset
- Fail if any primary metric drops by >5% from last recorded baseline
- Baseline stored in `eval_results/baseline.json`, updated manually after intentional changes

**Payoff:** Quality can only go up. Regressions are caught before they ship.

---

## Implementation Sequencing

```
Phase 1 — Foundation (do before any companion-proposal work):
  1c → Evaluation runner (tools/strata_eval.py)
  1a → Metrics module (eval_metrics.py)
  2a → Annotation format definition
  4b → Config-as-code consolidation (config/strata.yaml)

Phase 2 — Gold Data (do alongside companion Phase A):
  2b → Annotate 20-track gold set with Brach
  3a → Quantify Pioneer phrase noise
  5  → Experiment template (docs/)

Phase 3 — Measurement Infrastructure (do before companion Phase B):
  1b → Show-control-specific metrics
  6a → Application-aligned scoring
  7a → Tier regression dashboard

Phase 4 — Ongoing:
  3b → Noise-robust training (when HSMM work begins)
  3c → Disagreement tracking
  4a → Analysis manifest enrichment
  4c → Deterministic preprocessing
  6b → Perceptual checks on major changes
  7b → Automatic regression gate
```

**Critical dependency:** Phase 1 should complete BEFORE the companion proposals start building the HSMM and fusion engine. Without the eval harness, those improvements can't be measured.

---

## Relationship to Companion Proposals

| This proposal | Enables measuring... | In companion proposal... |
|--------------|---------------------|-------------------------|
| Boundary F-measure | Section boundary improvements | EDM priors items 1-3, 7, 8 |
| Label accuracy | Section classification | EDM priors item 2 (HSMM) |
| Layer activity F1 | Stem separation quality | Research migration items 1-2 |
| Stability metrics | Live tier reliability | Research migration item 5 (fusion) |
| Weak-label robustness | Pioneer data usage | EDM priors item 8 (Pioneer-first) |
| Experiment template | All proposed experiments | Every item in both proposals |
| Regression gate | No quality backslide | Every code change |

---

## New Files Created

| File | Purpose |
|------|---------|
| `scue/layer1/strata/eval_metrics.py` | Metric implementations (wraps mir_eval) |
| `tools/strata_eval.py` | Evaluation runner CLI |
| `config/strata.yaml` | Consolidated tunable parameters |
| `config/strata_eval.yaml` | Evaluation weights and thresholds |
| `docs/strata-annotation-format.md` | Gold annotation schema |
| `docs/strata-experiment-template.md` | Per-experiment design template |
| `docs/pioneer-phrase-noise-profile.md` | Phrase analysis reliability data |
| `tests/fixtures/strata_gold/` | Gold annotations directory |
| `eval_results/` | Evaluation run outputs + baseline |

---

## Dependencies

| Item | Dependency | Risk |
|------|-----------|------|
| 1a (mir_eval) | `pip install mir_eval` | Low — stable, well-maintained |
| 2b (gold annotations) | Brach's time for 20-track annotation | Medium — calendar dependency |
| 3a (phrase noise) | Pioneer data from scanner/bridge | Low — already captured |
| 7b (regression gate) | Fast eval subset (<30s total) | Low — just pick 5 short tracks |
