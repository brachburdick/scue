# Research Findings: Arrangement Formula via Acoustic Event Detection and Few-Shot Learning

**Request:** Deep research on building a tool that turns audio into an arrangement formula:
atomic events and their characteristics, instruments/tracks, and grouped event patterns
such as drum fills and arpeggio runs. Section detection intentionally excluded.

**Date:** 2026-03-22
**Status:** Complete

---

## Executive Summary

The short version: there is no current single SOTA model that reliably takes a finished
stereo song and emits all of the following at once: per-event timing, per-event semantics,
instrument attribution, grouped motifs like fills/runs, and track-like decomposition.
The best current approach is a **stacked pipeline**:

1. **Strong frozen audio/music representation models** for frame embeddings
2. **Source separation and/or transcription** to expose cleaner atomic events
3. **Task-specific event heads** for drums, note onsets, instrument activity, and FX-like
   events
4. **Sequence grouping over detected events** to infer patterns such as fills and arp runs
5. **Few-shot adapters** so new event vocabularies can be added without retraining the
   whole system

For SCUE specifically, the highest-leverage direction is:

- Use a **music-specific SSL backbone** such as MERT or MuQ for broad music semantics
- Keep a **frame-level acoustic backbone** such as ATST-Frame or BEATs for precise event
  localization
- Use **source separation + transcription** for drums, pitched notes, and instrument
  activity
- Treat "drum fill", "arp run", "pickup", "noise sweep", etc. as **group labels over an
  event graph**, not as first-pass frame labels
- Use **few-shot prototype heads on frozen embeddings** for SCUE-specific event classes
  that public datasets do not cover well

Most important architectural conclusion:

**Few-shot learning is best used as an adaptation layer on top of strong pretrained audio
embeddings, not as the only core detector.**

---

## Bottom-Line Recommendations

### Recommended stack for SCUE

| Layer | Recommendation | Why |
|---|---|---|
| Frame embeddings | ATST-Frame or BEATs for localization, plus MERT or MuQ for music semantics | General SED models localize well; music SSL models understand pitch/timbre/style better |
| Coarse stems | HT Demucs-class separator | Greatly improves drum/instrument activity detection from dense mixes |
| Fine drum structure | Drum-specific separator/transcriber, optionally StemGMD/LarsNet-style tooling | Drum fills are much easier once the drum bus is isolated |
| Note/instrument events | YourMT3+ first, MT3/Perceiver TF as baselines | Best current practical path to note-level multi-instrument events |
| Novel event classes | Few-shot prototype detector over frozen frame embeddings | Cheap to extend; works with small labeled sets |
| Open vocabulary | CLAP-style text/audio head or MuLan-style music-text head | Good for search/bootstrap, weaker than audio exemplars for precise temporal detection |
| Pattern grouping | Separate sequence model over detected events | Fills and runs are compositional patterns, not raw acoustic primitives |

### What not to assume

- You will not recover true DAW-style "individual tracks" from a stereo master.
  You can usually recover **stems**, **instrument activity**, and **note/event streams**.
- General SED alone is not enough for musical arrangement extraction.
- Open-vocabulary text prompting is promising, but for precise timing and SCUE-specific
  semantics it is still weaker than exemplar-based few-shot detection.

---

## Research Findings

### 1. SOTA acoustic event detection is now backbone-driven

Modern SED systems are dominated by **pretrained audio transformers** and
semi-supervised training rather than hand-built feature stacks.

- The DCASE 2024 Task 4 leaderboard for sound event detection with heterogeneous data
  shows top systems clustered around pretrained encoders such as **ATST** and **BEATs**,
  with the best single-model score at **1.35** vs the official baseline at **1.13**.
- **ATST** is especially relevant because it explicitly targets both clip-level and
  frame-level tasks; the paper reports strong gains on frame-level sound event detection.
- **BEATs** remains one of the strongest general-purpose audio SSL backbones, with SOTA
  classification performance reported on AudioSet and ESC-50.

Implication for SCUE:

- If you want precise event boundaries, do not start from raw handcrafted DSP alone.
- Start from a strong frame-level backbone and add SCUE-specific heads.

### 2. Music-specific SSL matters for arrangement analysis

General acoustic models help with event timing, but **music-specific foundation models**
are better priors for pitch, harmony, instrumentation, and arrangement texture.

- **MERT** was built specifically for acoustic music understanding and reports SOTA
  overall performance across 14 music understanding tasks.
- **MuQ** extends this direction with music-focused SSL and a music-text variant
  (**MuQ-MuLan**) that reports SOTA zero-shot music tagging in its paper.
- **MuLan** itself is important conceptually: it learns a joint embedding between music
  audio and natural language, enabling zero-shot or open-vocabulary music tagging.

Implication for SCUE:

- For arrangement analysis, use a **dual-backbone mentality**:
  - frame-accurate acoustic backbone for timing
  - music-specific backbone for semantic interpretation

I would not choose only one.

### 3. Multi-instrument transcription is the best current route to atomic musical events

If you want "individual events and their characteristics" in a musical sense, the best
publicly documented route is **automatic music transcription (AMT)** rather than generic
SED.

- **MT3** showed that a unified Transformer can do multi-task multitrack transcription
  across diverse instruments and low-resource settings.
- **Perceiver TF** reported outperforming MT3 and SpecTNT on public multitrack
  transcription datasets while modeling 12 instruments plus vocals.
- **YourMT3+** is the most relevant current practical reference point. It improves MT3
  with hierarchical time-frequency attention, mixture-of-experts, and cross-dataset stem
  augmentation. Its paper also explicitly notes that dense pop recordings still expose
  limitations.

Implication for SCUE:

- For pitched/harmonic events, treat AMT as the main engine.
- Use the resulting note and instrument streams as your "atomic event lattice".
- Do not expect AMT alone to cleanly detect grouped concepts like fills or risers. Those
  should be inferred later.

### 4. Source separation is still necessary

Dense modern mixes make event detection much easier if you split the signal first.

- **HT Demucs** remains a strong reference architecture for music source separation and
  reported SOTA MUSDB performance in its paper.
- For drums specifically, **Toward Deep Drum Source Separation** introduced the large
  **StemGMD** dataset and a **LarsNet** model that separates five drum stems faster than
  real time.

Implication for SCUE:

- Even if your final product is "arrangement formula", a separator upstream will pay for
  itself immediately in detector quality.
- At minimum, separate `drums / bass / vocals / other`.
- If drum fill quality matters a lot, add a second-stage drum separator or drum
  transcription model on the drum stem.

### 5. Few-shot learning is already useful in audio, but not as magic

The most actionable few-shot lesson from the literature is that **frozen pretrained
features + simple adaptation heads** can work surprisingly well.

- In DCASE 2024 Task 5 (few-shot bioacoustic event detection), the official baseline
  prototypical network scored **41.6 F1**, while the best team reached **65.2 F1** with
  frame-level embedding learning. That is a meaningful gap, but it is still clearly a
  "specialized few-shot detector on top of strong embeddings" story.
- Apple's ICASSP 2023 paper on **few-shot detection of novel and fine-grained acoustic
  sequences using pretrained audio representations** is especially relevant. It argues
  that pretrained embeddings make few-shot SED feasible even for events with meaningful
  temporal structure.
- In music specifically, **Music auto-tagging in the long tail: A few-shot approach**
  shows that a simple linear probe on pretrained features can get close to SOTA with as
  few as **20 samples per tag**.
- For instrument recognition, **Leveraging Hierarchical Structures for Few-Shot Musical
  Instrument Recognition** shows that prototypical few-shot methods improve if you encode
  a hierarchy such as `percussion -> drum kit -> snare`.

Implication for SCUE:

- Few-shot is a great fit for **SCUE-defined classes** like:
  - `noise_riser`
  - `drum_fill`
  - `triplet_fill`
  - `acid_arp_run`
  - `impact_hit`
  - `vocal_chop_burst`
- The best setup is:
  - frozen backbone
  - small support set per class
  - prototype or linear probe head
  - temporal smoothing / alignment

### 6. Open-vocabulary detection is promising but still early

Recent work is moving toward detectors that accept **free-text event queries**.

- **CLAP** showed that contrastive language-audio pretraining can support zero-shot audio
  classification and retrieval.
- **FlexSED** pushes this into open-vocabulary sound event detection with zero-shot and
  few-shot capabilities. This is exciting, but it is a 2025 preprint and not yet the kind
  of battle-tested musical event stack you would want to depend on for production.
- On the music side, **MuLan** and **MuQ-MuLan** suggest a similar direction for
  natural-language music descriptors.

Implication for SCUE:

- Use open-vocabulary models as:
  - bootstrap search tools
  - weak annotators
  - candidate proposal systems
- Do not trust them yet as the only detector for fine temporal events in dense EDM.

### 7. Grouped events should be modeled as sequence structure, not raw acoustics

This is the most important modeling point for the examples you gave.

`drum fill` and `arpeggio run` are not single acoustic atoms. They are **temporally
organized collections of lower-level events**.

That means the right representation is:

1. detect atomic events first
2. build a time-ordered event graph
3. run a second model over event sequences

Examples:

- **Drum fill**
  - Input: kick/snare/tom/cymbal hits, onset density, rhythmic displacement, bar position
  - Output: fill start, fill end, fill subtype, intensity, confidence

- **Arpeggio run**
  - Input: note onset stream, pitch intervals, repetition rate, contour, duration
  - Output: arp start, arp end, rate, contour type, harmonic center, confidence

This second pass can begin as rules, then graduate to a learned sequence classifier.

---

## Practical Architecture for SCUE

### Proposed inference stack

```text
Stereo mix
  ->
Beatgrid + sections (already in SCUE)
  ->
Backbone embeddings
  - ATST-Frame or BEATs
  - MERT or MuQ
  ->
Coarse source separation
  - drums / bass / vocals / other
  ->
Atomic detectors
  - drum onset / drum transcription
  - AMT for pitched notes
  - instrument activity detection
  - FX/event detector head for sweeps, impacts, uplifters
  ->
Event graph
  - nodes: atomic events
  - edges: temporal adjacency, co-occurrence, stem co-membership
  ->
Pattern/group detectors
  - drum fill
  - arp run
  - pickup
  - roll
  - repeated stab pattern
  ->
Arrangement formula
```

### Recommended event schema

Each atomic event should carry at least:

- `start_time`
- `end_time`
- `event_type`
- `instrument_or_stem`
- `pitch_or_band`
- `energy`
- `brightness`
- `noisiness`
- `confidence`
- `source_model`

Each grouped event should carry at least:

- `group_type`
- `start_time`
- `end_time`
- `member_event_ids`
- `density`
- `contour`
- `role`
- `confidence`

This makes the grouped layer auditable and editable.

### How I would map tasks to models

| Task | Best first choice | Notes |
|---|---|---|
| Kick/snare/hat/tom events | Drum stem + drum detector/transcriber | Better than full-mix SED |
| Riser/impact/downlifter/noise FX | Frame-level SED head on ATST/BEATs embeddings | Likely needs custom SCUE labels |
| Notes / arp components | YourMT3+ | Most useful current reference point |
| Instrument activity | Separation + instrument classifier / AMT labels | Better than direct clip tagging |
| Grouped fills/runs | Sequence model over atomic events | Should not be first-pass detector |
| Novel SCUE classes | Few-shot prototypes on frozen embeddings | Best cost/benefit path |

---

## Few-Shot Strategy I Would Actually Build

### Best practical design

Use a **frozen frame encoder** and build a support-set detector on top.

#### For short event classes

Examples: `impact hit`, `reverse cymbal`, `vocal chop`, `laser stab`

1. Encode short labeled exemplars into frame/window embeddings
2. Average them into one or more class prototypes
3. Slide over the song embedding sequence
4. Score cosine similarity to prototypes
5. Apply temporal smoothing and peak picking

This is the simplest useful few-shot detector.

#### For temporally structured classes

Examples: `drum fill`, `arp run`, `snare roll`, `triplet pickup`

Do not use a single averaged prototype. Use one of these:

- **prototype bank + duration buckets**
- **DTW/alignment against support sequences**
- **cross-attention matching between support and query windows**

This matters because the temporal order is part of the class definition.

### Where hierarchy helps

SCUE should define a class hierarchy and use it in few-shot learning.

Example:

```text
percussion_event
  -> kick
  -> snare
  -> clap
  -> cymbal
group_event
  -> drum_fill
  -> roll
  -> arp_run
fx_event
  -> riser
  -> downlifter
  -> impact
```

This gives graceful fallback. If the model cannot confidently call something a
`triplet_tom_fill`, it may still correctly call it `drum_fill`.

### Where text prompting fits

Text-conditioned models are useful for:

- discovering candidate labels
- retrieving similar examples
- generating weak labels
- bootstrapping annotation tools

But for precise SCUE use, I would prefer:

- **audio exemplars first**
- text prompts second

---

## Datasets You Will Need

Public data covers only part of the problem.

### Strong public starting points

| Need | Candidate data |
|---|---|
| General acoustic events | AudioSet, AudioSet-Strong, DESED, MAESTRO |
| Music stems / separation | MUSDB18, Slakh2100 |
| Multitrack transcription | Slakh2100, MusicNet, MIR-ST500, GuitarSet, MAESTRO piano, related AMT corpora |
| Drum-only detail | ENST Drums, E-GMD, StemGMD |

### Data you will almost certainly need to build yourself

Public datasets are weak on exactly the semantics SCUE cares about most:

- EDM risers
- downlifters
- impacts
- fill taxonomies
- arp runs
- modern layered drum programming
- vocal chop bursts

So the practical answer is:

1. pretrain or initialize from public models
2. build a **small, high-quality SCUE library**
3. use few-shot adaptation for SCUE-specific classes

This is where your own catalog becomes an advantage.

---

## What I Would Build First

### Phase 1: Useful fast baseline

- Add one frame-level backbone: **ATST-Frame**
- Add one music backbone: **MERT** or **MuQ**
- Add source separation: **HT Demucs-class**
- Keep existing SCUE heuristics for sections and simple rhythm priors
- Build a few-shot prototype detector for 5-10 custom classes

Target outputs:

- drum events
- impacts
- risers
- downlifters
- vocal chop bursts
- repeated stab patterns

### Phase 2: Strong musical event layer

- Add **YourMT3+**
- Run it on full mix and on separated non-drum stems
- Build note/event graph and instrument activity streams

Target outputs:

- note onsets
- per-instrument note streams
- arp candidate windows
- repeated melodic motifs

### Phase 3: Grouped arrangement logic

- Build a sequence model over event tokens
- Start rule-based, then train on SCUE annotations
- Add grouped labels such as:
  - `drum_fill`
  - `snare_roll`
  - `arp_run`
  - `pickup`
  - `drop_impact_cluster`

---

## Main Risks and Limitations

1. **Stereo mix ambiguity**
   Exact "individual tracks" are usually unrecoverable from a master.

2. **Dataset mismatch**
   Public SED and AMT benchmarks underrepresent modern EDM production tropes.

3. **Temporal semantics**
   Group labels need structured temporal modeling, not only frame classification.

4. **Annotation bottleneck**
   You will still need a labeled SCUE-specific support library for your most valuable
   classes.

5. **Compute cost**
   Separation + AMT + few-shot matching is heavier than SCUE's current heuristic pass.
   This is probably fine for offline analysis but not free.

---

## Final Recommendation

If the goal is a production-worthy "arrangement formula" extractor, I would not frame the
project as "find one better event detector."

I would frame it as:

**Build a music analysis stack whose lowest layer is strong frozen embeddings, whose middle
layer exposes atomic musical events, and whose top layer turns those events into arrangement
concepts.**

That gives you:

- immediate wins from modern SOTA backbones
- a clear place for few-shot adaptation
- an architecture that matches how musical concepts are actually composed

In other words:

- **ATST/BEATs** for timing
- **MERT/MuQ** for music semantics
- **HT Demucs** for separation
- **YourMT3+** for note/instrument events
- **few-shot prototypes** for custom SCUE labels
- **sequence grouping** for fills, runs, and higher-order arrangement patterns

---

## Sources

Primary sources used:

- DCASE 2024 Task 4 results:
  [dcase.community/challenge2024/task-sound-event-detection-with-heterogeneous-training-dataset-and-potentially-missing-labels-results](https://dcase.community/challenge2024/task-sound-event-detection-with-heterogeneous-training-dataset-and-potentially-missing-labels-results)
- DCASE 2024 Task 5 results:
  [dcase.community/challenge2024/task-few-shot-bioacoustic-event-detection-results](https://dcase.community/challenge2024/task-few-shot-bioacoustic-event-detection-results)
- ATST:
  [arxiv.org/abs/2306.04186](https://arxiv.org/abs/2306.04186)
- BEATs:
  [proceedings.mlr.press/v202/chen23ag.html](https://proceedings.mlr.press/v202/chen23ag.html)
- MERT:
  [arxiv.org/abs/2306.00107](https://arxiv.org/abs/2306.00107)
- MuQ:
  [arxiv.org/abs/2501.01108](https://arxiv.org/abs/2501.01108)
- MuLan:
  [research.google/pubs/mulan-a-joint-embedding-of-music-audio-and-natural-language](https://research.google/pubs/mulan-a-joint-embedding-of-music-audio-and-natural-language/)
- MT3:
  [arxiv.org/abs/2111.03017](https://arxiv.org/abs/2111.03017)
- Perceiver TF:
  [arxiv.org/abs/2306.10785](https://arxiv.org/abs/2306.10785)
- YourMT3+:
  [arxiv.org/abs/2407.04822](https://arxiv.org/abs/2407.04822)
- HT Demucs:
  [arxiv.org/abs/2211.08553](https://arxiv.org/abs/2211.08553)
- StemGMD / LarsNet drum separation:
  [arxiv.org/abs/2312.09663](https://arxiv.org/abs/2312.09663)
- CLAP:
  [arxiv.org/abs/2211.06687](https://arxiv.org/abs/2211.06687)
- FlexSED:
  [arxiv.org/abs/2509.18606](https://arxiv.org/abs/2509.18606)
- Apple few-shot acoustic sequence detection:
  [machinelearning.apple.com/research/learning-detect-novel](https://machinelearning.apple.com/research/learning-detect-novel)
- Few-shot music auto-tagging in the long tail:
  [arxiv.org/abs/2409.07730](https://arxiv.org/abs/2409.07730)
- Few-shot musical instrument recognition with hierarchy:
  [arxiv.org/abs/2107.07029](https://arxiv.org/abs/2107.07029)
