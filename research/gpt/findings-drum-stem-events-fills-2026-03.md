# Research Findings: Drum Stem to Drum Events to Grouped Fills

**Request:** Research the best pipeline from `drum stem -> individual drum events ->
grouped drum fills` for EDM / club music, including SOTA methods, practical limits,
taxonomy choices, few-shot possibilities, and what SCUE should do next.

**Date:** 2026-03-22
**Status:** Complete

---

## Executive Summary

The current research picture suggests a very practical architecture:

1. **Separate a drum stem first**
2. **Run a dedicated automatic drum transcription (ADT) model on that stem**
3. **Represent the result as a beat/tatum-aligned hit stream**
4. **Detect fills as grouped deviations from the local drum pattern, not as raw-audio
   primitives**

The strongest evidence for this pipeline is:

- **STAR Drums (2025)** and **Understanding Performance Limitations in ADT (2025)** both
  support the conclusion that melodic interference is a major bottleneck for drum
  transcription in mixtures.
- Once you remove melodic interference, the next dominant bottleneck is **simultaneous
  overlapping drum hits**, especially for toms and cymbals.
- The latest ADT frontier in **2025-2026** is moving along two axes:
  - better training data realism
  - stronger modeling, including foundation-model features and diffusion-style decoding
- There is also a **direct few-shot ADT path**: **Real-Time Automatic Drum Transcription
  Using Dynamic Few-Shot Learning (2024)** reports state-of-the-art performance for
  10 drum classes in mixtures and can learn new classes from examples provided at test
  time.

My main recommendation for SCUE:

**Do not start with the fanciest 2026 diffusion model. Start with a strong drum-stem-first
ADT pipeline and a separate fill grouper over hit streams.**

That gives the best ratio of research sophistication to implementation payoff.

---

## Bottom-Line Recommendations

### What SCUE should build first

- Keep stem separation as a dedicated upstream step
- Transcribe the drum stem into a hit grid at **tatum or beat subdivision resolution**
- Start with a compact atomic class set
- Model fills as **window/bar-level group events** derived from atomic hits
- Reserve few-shot learning for:
  - custom fill subtypes
  - custom club-percussion categories
  - unusual impact/fill gestures not covered by public datasets

Exception:

- If you specifically want the ability to add or adapt **new atomic drum classes quickly**,
  dynamic few-shot ADT is now strong enough to justify an earlier experiment.

### What SCUE should not do first

- Do not start from full-mixture raw audio for fill detection
- Do not make `drum_fill` a first-pass raw acoustic class
- Do not overcommit to large fine-grained drum taxonomies before the base hit stream is
  reliable
- Do not assume literature benchmarks map cleanly to EDM; a lot of the EDM-specific work
  will still require custom data

---

## Research Findings

### 1. Drum stem first is the right decomposition

The literature now makes this pretty clear.

- **STAR Drums (2025)** creates ADT training data by first separating a mixture into
  `drum stem` and `non-drum stem`, then annotating and re-synthesizing the drum stem.
  The paper explicitly frames drum transcription in the presence of melodic instruments as
  the hardest ADT setting.
- **Understanding Performance Limitations in Automatic Drum Transcription (ISMIR 2025)**
  finds that for drum transcription in mixtures, the **primary limiting factor is
  interference from melodic instruments and singing**. For drum-only recordings, the
  dominant remaining bottleneck becomes **simultaneous overlapping drum hits**.
- **Enhanced Automatic Drum Transcription via Drum Stem Source Separation (2025)** shows a
  pragmatic gain from using drum stem source separation downstream of ADT: it expands a
  five-class transcription into seven classes and adds velocity estimation.

Implication for SCUE:

- Separating the drum stem is not optional polish; it changes the problem.
- Your intuition was right that downstream drum classification becomes much easier after
  separation.
- But the 2025 limitations paper also makes it clear that this does **not** make the task
  trivial, because overlapping drum hits remain the next major error source.

### 2. The ADT frontier in 2026 is split between better data and better decoders

There is no single settled winner yet.

#### Data-centric progress

- **High-Quality and Reproducible Automatic Drum Transcription from Crowdsourced Data
  (2023)** shows that large crowdsourced real-world data strongly improves generalization.
- **Analyzing and reducing the synthetic-to-real transfer gap... (2024)** argues that
  infinite synthetic data is not enough by itself; realism matters, and the paper studies
  strategies to narrow the transfer gap.
- **Towards Realistic Synthetic Data for Automatic Drum Transcription (2026)** reports new
  SOTA results on ENST and MDB by curating realistic one-shot drum data and training a
  sequence-to-sequence transcription model.

#### Model-centric progress

- **Global Structure-Aware Drum Transcription Based on Self-Attention Mechanisms (2021)**
  is important conceptually because it predicts a **tatum-level drum score**, which is a
  very natural fit for SCUE's beat-aligned workflow.
- **Real-Time Automatic Drum Transcription Using Dynamic Few-Shot Learning (2024)**
  is especially relevant to SCUE because it combines prototype-style few-shot adaptation
  with mixture transcription, reports state-of-the-art performance for **10 drum classes**
  on three public datasets, and explicitly supports learning new classes from a few test-
  time examples.
- **Noise-to-Notes (2025/2026)** reframes ADT as a conditional generative problem and
  reports SOTA across multiple ADT benchmarks, with additional gains from music foundation
  model features.

Implication for SCUE:

- The frontier is moving fast, but the research signal is consistent:
  - better temporal structure modeling helps
  - better data realism helps
  - music/foundation features help robustness
- For a first SCUE implementation, the safest path is still a **strong discriminative or
  tatum-level model on a drum stem**, not a diffusion-first system.

### 3. Common atomic drum taxonomies are still relatively coarse

This matters because taxonomies drive both data availability and achievable accuracy.

Across the literature, common ADT label sets are roughly:

- **3 classes:** kick, snare, hi-hat
- **5 classes:** kick, snare, hi-hat, toms, cymbals
- **7-8 classes:** split open/closed hats and split crash/ride, sometimes keep toms merged

Evidence:

- The 2025 **Enhanced ADT via Drum Stem Source Separation** abstract explicitly talks about
  expanding from **5 classes to 7 classes** using separated stems.
- Older pattern-based ADT work such as **Drum Transcription via Classification of Bar-Level
  Rhythmic Patterns (2014)** already showed the value of handling a somewhat broader set:
  kick, snare, closed hi-hat, open hi-hat, ride, crash.
- The 2025 limitations work still highlights **toms and cymbals** as difficult, which is a
  reminder that finer taxonomies get harder quickly.

### 4. Recommended atomic taxonomy for SCUE

This is my recommendation, not a direct benchmark fact.

I would start with these atomic classes:

- `kick`
- `snare`
- `clap`
- `hihat_closed`
- `hihat_open`
- `tom`
- `crash`
- `ride`
- `perc_other`
- `impact_other`

Why this set:

- It preserves classes that matter a lot for cueing
- It maps reasonably well onto public ADT conventions
- It does not overfit too early to extremely fine subtypes
- It keeps `fill` out of the atomic layer, where it does not belong

I would treat these as **group labels**, not atomic labels:

- `drum_fill`
- `snare_roll`
- `tom_fill`
- `triplet_fill`
- `pickup_fill`
- `impact_cluster`

### 5. Fill detection should happen over hit streams, not raw audio

This is the most important design call.

I did **not** find a strong standardized literature track for "drum fill detection from raw
audio" comparable to MSS or ADT benchmarks. That is an inference from the literature search,
not a formal claim.

What the literature does support is:

- **Pattern-level drum modeling** is useful
- **Fills/improvisations are sparse and underrepresented**
- **Bar context matters**

Evidence:

- **Drum Transcription via Classification of Bar-Level Rhythmic Patterns (2014)** shows
  that bar-level pattern classification is a workable proxy for individual drum events and
  is more robust to polyphonic accompaniment in some settings.
- **Generating Coherent Drum Accompaniment with Fills and Improvisations (ISMIR 2022)**
  treats fills as sparse, special bars that require explicit location modeling and
  in-filling, which matches the intuition that fills are deviations from a local pattern
  baseline rather than isolated raw events.

Practical implication:

- First build a reliable atomic hit stream.
- Then compute a local pattern baseline over neighboring bars.
- A fill is a **structured deviation** from that baseline.

### 6. A good fill detector should use novelty, density, and bar position

This is partly inference from the papers above and partly design guidance.

Useful features for grouped fill detection:

- increase in onset density vs neighboring bars
- stronger use of toms/crashes/open hats vs local baseline
- deviation from the repeated groove prototype
- occurrence near phrase / section transitions
- reduced kick regularity or backbeat stability
- short run-up to a boundary
- repeated rapid hits or triplet-like subdivisions

This suggests a two-stage grouping system:

1. **Fill candidate detection**
   - novelty score per bar or half-bar
   - density delta
   - deviation from groove centroid

2. **Fill subtype classification**
   - tom-heavy fill
   - snare roll
   - cymbal-led pickup
   - triplet fill
   - impact cluster

### 7. Few-shot learning is best used at the fill subtype layer

I do not think few-shot should be used for your core `kick/snare/hat` detector.

Better use cases:

- `triplet_tom_fill`
- `snare-buzz roll`
- `festival-build fill`
- `hybrid impact fill`
- `latin-ish percussion pickup`

Why:

- atomic drum classes are common enough that supervised models already have a lot to learn from
- fill subtypes are rarer, more style-specific, and more SCUE-specific

This matches the broader few-shot lesson from the earlier arrangement research:

- frozen backbone
- small support set
- similarity/prototype or light adaptation head
- temporal matching over short sequences

There is one important exception: **dynamic few-shot ADT** is now a credible option at the
atomic layer if you care about adding drum classes quickly or adapting to a specific kit.
Even then, I would still use few-shot on **event sequences** for fill subtypes rather than
expect raw waveform few-shot to solve grouped fill detection by itself.

### 8. What still breaks hardest in EDM / club drums

This is where public research stops being genre-specific and we have to infer carefully.

Based on the literature plus SCUE's domain, the hardest club-specific failure cases are:

- layered snare+clap stacks
- kick tops that resemble synth noise or distorted percussion
- cymbal wash masking weak fills
- large impacts that combine cymbal, downlifter, tom, and noise burst energy
- sidechained, heavily compressed drum buses
- synthetic percussion with ambiguous class boundaries
- fills made from non-drum synth stabs rather than drum-kit components

This is an inference from drum-transcription limits plus EDM production practice, not a
benchmark result.

The main consequence is:

**EDM fill detection will always be partly a musical-semantic task, not just a drum-kit
recognition task.**

---

## Practical Architecture for SCUE

### Recommended pipeline

```text
mixture audio
  ->
music stem separation
  ->
drum stem
  ->
ADT model
  ->
atomic hit grid
  ->
groove baseline model
  ->
fill candidate detector
  ->
fill subtype classifier
  ->
SCUE drum events + grouped fill events
```

### Best first implementation

#### Atomic layer

- Use a drum stem as input
- Quantize output to your known beatgrid / tatum grid
- Start with 5-8 classes
- Keep velocity if available

#### Group layer

- Build bar-level or half-bar-level windows
- Compare each window to neighboring groove context
- Emit `FillEvent` objects with:
  - `start`
  - `end`
  - `subtype`
  - `member_hits`
  - `density`
  - `energy`
  - `confidence`

---

## What I Would Build First

### Phase 1: Reliable atomic drum stream

- Choose a practical drum-stem ADT model
- Output `kick/snare/clap/hats/tom/crash/ride`
- Align to SCUE beatgrid
- Store hits compactly

This alone unlocks a lot of useful cue logic.

### Phase 2: Fill grouping

- Learn a groove prototype over the last 2-4 bars
- Compute novelty and density deltas
- Detect fill windows
- Classify a small number of fill subtypes

This is the first point where SCUE starts to extract musically meaningful grouped drum events.

### Phase 3: Few-shot adaptation

- Add support-set based subtype classification for custom fills
- Add club-specific categories
- Add uncertainty-aware fallback to generic `drum_fill`

### Phase 4: Frontier upgrades

- Try foundation-model feature augmentation
- Try diffusion-style ADT only if Phase 1-3 hit a ceiling

---

## Recommended Next Pass After This One

After this research pass, the next thing you should do is:

**Choose the concrete implementation stack for Phase 1.**

Specifically:

1. pick one drum stem separator to prototype with
2. pick one practical ADT model family
3. define the exact atomic label set
4. define the grouped fill schema
5. choose the offline eval datasets and custom SCUE eval tracks

If you want me to drive that pass, I would focus it on:

**"What exact separator + ADT stack should SCUE prototype first on Apple Silicon, and what
evaluation harness should we use?"**

That is the point where research turns into a concrete build plan.

---

## Sources

Primary sources used:

- STAR Drums:
  https://transactions.ismir.net/articles/10.5334/tismir.244
- Understanding Performance Limitations in Automatic Drum Transcription:
  https://publica.fraunhofer.de/entities/publication/825f8da1-a712-4825-bc33-8d869801a8e4
- Enhanced Automatic Drum Transcription via Drum Stem Source Separation:
  https://ismir2024program.ismir.net/lbd_482.html
- High-Quality and Reproducible Automatic Drum Transcription from Crowdsourced Data:
  https://www.mdpi.com/2624-6120/4/4/42
- ADTOF repository:
  https://github.com/MZehren/ADTOF
- Real-Time Automatic Drum Transcription Using Dynamic Few-Shot Learning:
  https://publica.fraunhofer.de/entities/publication/ea511ccd-d734-4e99-b98b-e795cba669e1
- Analyzing and reducing the synthetic-to-real transfer gap in MIR:
  https://arxiv.org/abs/2407.19823
- Towards Realistic Synthetic Data for Automatic Drum Transcription:
  https://arxiv.org/abs/2601.09520
- Noise-to-Notes:
  https://arxiv.org/abs/2509.21739
- Global Structure-Aware Drum Transcription Based on Self-Attention Mechanisms:
  https://www.mdpi.com/2624-6120/2/3/31
- Drum Transcription via Classification of Bar-Level Rhythmic Patterns:
  https://archives.ismir.net/ismir2014/paper/000302.pdf
- Generating Coherent Drum Accompaniment with Fills and Improvisations:
  https://archives.ismir.net/ismir2022/paper/000031.pdf
