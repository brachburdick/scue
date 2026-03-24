# Research Findings: Stem Separation and Polyphonic Limits

**Request:** Explain whether stem separation is "solved," how SOTA systems work, what
their limitations are, what stem categories exist, and what those limits imply for
downstream tasks such as drum events, vocal analysis, instrument activity, note streams,
and grouped arrangement patterns in dense polyphonic music.

**Date:** 2026-03-22
**Status:** Complete

---

## Executive Summary

Stem separation is **not fully solved**, but it is very strong in a few important cases.

- For **offline 2-stem** separation (`vocals` / `instrumental`) and **offline 4-stem**
  separation (`vocals`, `drums`, `bass`, `other`), current systems are often good enough
  to feel nearly solved on many mainstream tracks.
- It is **not** source-perfect, and it is **not** solved for:
  - fine-grained stems
  - long-tail instruments
  - exact attribution under heavy overlap
  - shared effects like reverb, bus compression, and saturation
  - artifact-free isolation in all genres and mixes

Most important correction:

**Modern stem separation is not just frequency-band splitting.**

SOTA systems learn source structure across:

- time
- frequency
- stereo cues
- transient shape
- harmonic structure
- decay patterns
- context before and after overlaps

This is why a strong model can often handle cases like:

- a decaying saturated kick whose upper harmonics overlap with a synth entering in the
  same band

But this is also exactly where models can still fail, because the mixture is
**underdetermined** and the separator is relying on learned priors rather than perfect
recovery.

---

## Is Stem Separation Solved?

My conclusion from the current literature is:

- **No**, not in the strict research sense
- **Yes-ish**, for some practical offline workflows involving common stems

Why I do not call it solved:

- The 2023 Sound Demixing Challenge still focused on robustness to **label noise** and
  **bleeding** in training data, and the best system still improved by more than **1.6 dB
  SDR** over the previous challenge winner. That is not a mature, saturated field.
- New model families such as **BS-RoFormer**, **Mel-Band RoFormer**, and
  **stem-agnostic/query-based** systems are still materially improving results and
  widening the set of stems that can be separated.

Primary references:

- [Hybrid Spectrogram and Waveform Source Separation](https://arxiv.org/abs/2111.03600)
- [Music Source Separation with Band-Split RoPE Transformer](https://arxiv.org/abs/2309.02612)
- [Mel-Band RoFormer for Music Source Separation](https://arxiv.org/abs/2310.01809)
- [The Sound Demixing Challenge 2023 – Music Demixing Track](https://arxiv.org/abs/2308.06979)

Inference from those sources:

**Stem separation is strong enough to be a first-class building block for SCUE, but not
strong enough to be treated as ground truth.**

---

## How SOTA Stem Separation Actually Works

### 1. Spectrogram-mask models

These systems transform audio into a complex spectrogram and predict masks or direct source
estimates over time-frequency bins.

Examples:

- **BS-RoFormer** uses a band-split front-end and hierarchical Transformers to model both
  within-band and across-band structure.
- **Mel-Band RoFormer** replaces heuristic band partitions with overlapping mel-aligned
  subbands and reports better separation for several stems.

This is where frequency bands matter, but only as one part of a learned model.

### 2. Waveform or hybrid models

These models work directly on waveforms or combine waveform and spectrogram branches.

- **Hybrid Demucs** explicitly combines waveform and spectrogram processing and states that
  the model can decide which domain is best for each source.

This matters because some sources are easier to model in time-domain terms
(`transients`, `phase`, `attack/decay`) while others benefit from frequency-domain
structure (`harmonics`, `partials`, `broadband masks`).

### 3. Query-based or stem-agnostic systems

The newer direction is not "hardcode exactly 4 stems forever," but instead:

- condition the separator on the requested stem
- use a shared decoder or query mechanism
- support rare or narrow classes without multiplying model size linearly

Example:

- **Banquet** targets source separation beyond the standard `vocals / drums / bass / other`
  setup and uses a query-based system with a single decoder.

This direction matters because fixed 4-stem MSS is much easier than "give me organ,"
"reeds," or "clean acoustic guitar."

---

## What Stem Categories Exist?

There is no single universal taxonomy. The categories depend on the dataset or product.

### Standard benchmark categories

- **2-stem:** `vocals`, `instrumental`
- **4-stem:** `vocals`, `drums`, `bass`, `other`

This is the standard MUSDB / MDX world.

### Extended benchmark categories

Datasets like **MoisesDB** were created specifically because 4 stems are too coarse.
MoisesDB provides a **two-level hierarchical taxonomy** and supports evaluation at
different granularities including **4-, 5-, and 6-stem** settings.

Typical extended categories include some combination of:

- vocals
- drums
- bass
- guitar
- piano / keys
- other

### Fine-grained or product-style categories

Commercial and query-based systems often go finer:

- lead vocals
- backing vocals
- kick
- snare
- hi-hat
- toms
- cymbals
- piano
- organ
- acoustic guitar
- electric guitar
- reeds
- synth lead
- synth pad

But these are much less standardized, and quality varies a lot more than with 4-stem
separation.

---

## The Fundamental Limits of Stem Separation

These are the real limits to keep in mind.

### 1. The mixture is underdetermined

A stereo mix does not contain enough information to uniquely recover every original source.

If two sources overlap in the same time-frequency region, exact recovery may be impossible.
The model is using source priors to make its best guess.

Your kick+synth example lives exactly here:

- the model can use transient shape, decay, repetition, context, and expected timbre to
  infer source ownership
- but if the overlap is severe enough, it still has to guess

### 2. Shared effects blur source ownership

A lot of energy in a master belongs to multiple sources at once:

- reverb returns
- delay tails
- bus compression pumping
- saturation/distortion
- sidechain artifacts
- mastering EQ and limiting

These effects are often not cleanly attributable to one stem.

### 3. Stem ontology is partly subjective

Sometimes the hard question is not "can the model separate it?" but "what is the right
label?"

Examples:

- Is a layered synth-bass hit `bass` or `other`?
- Is a vocal reverb tail part of `vocals` or ambient `other`?
- Is a percussion layer `drums` or `other percussion`?

So some errors are ontology problems, not only modeling problems.

### 4. Training data is imperfect

SDX'23 directly emphasized robustness to:

- **label noise**
- **bleeding**

That is a strong sign that source separation is limited by dataset quality as much as by
architecture.

### 5. Fine-grained stems are much harder than coarse stems

`vocals`, `drums`, `bass`, `other` works partly because each class is broad.

As soon as you ask for:

- piano vs organ
- clean guitar vs distorted guitar
- toms vs snare vs clap
- FX riser vs pad wash

the problem becomes substantially harder.

### 6. Objective metrics do not capture everything

The literature still uses SDR heavily, but challenge reports also include listening tests
because:

- a separation can score well numerically and still sound artifacty
- a musically useful separation is not the same thing as a metric-optimal one

---

## Does a Good Drum Stem Make Drum Classification Trivial?

Not trivial, but dramatically easier.

I would frame it like this:

- `drum transcription in full mixture` = hard
- `drum transcription on a good separated drum stem` = much more tractable

Why it is still not trivial:

- cymbal wash masks transients
- layered hits blur class boundaries
- distorted tops can resemble synth noise
- open hats overlap with snares and claps
- reverb and parallel processing alter envelopes
- toms, fills, impacts, and hybrid percussion are highly variable

The new **STAR Drums** dataset is a great indicator of where the field is:

- researchers first separate recordings into **drum stem** and **non-drum stem**
- then they build better ADT data and show that training on it improves performance

That is basically the field telling you:

**Yes, stem separation is useful enough to change the downstream problem materially.**

But the fact that drum transcription remains an active research area also tells you:

**No, separated drums do not make the task trivial.**

---

## Same Story for Vocals

Separated vocals make many tasks much easier, but they do not collapse into a solved
problem either.

The 2024 **Mel-RoFormer for Vocal Separation and Vocal Melody Transcription** paper is a
good example:

- they first train vocal separation
- then use that model as a foundation for vocal melody transcription

That only makes sense because:

- separation helps
- but the downstream objective is still different enough to need its own modeling

Implication for SCUE:

- a vocal stem is an excellent substrate for:
  - vocal activity
  - melody contour
  - phrase onset
  - chop detection
- but those still need dedicated heads or post-processing

---

## What This Means for Other Polyphonic Tasks

### Instrument activity

This is less mature than 4-stem separation.

Best practical routes:

- derive activity from separated stems
- use query-based separation
- use frame-level multi-label tagging on strong music embeddings
- combine AMT outputs with timbral classifiers

Main limitation:

- long-tail instruments and hybrid sounds are hard
- frame-level activity labels are expensive and noisy

### Note and event streams

This is automatic music transcription, not stem separation.

Best current direction:

- strong AMT models such as **MT3**, **Perceiver TF**, and **YourMT3+**
- optionally run on full mix plus separated non-drum stems

Main limitation:

- dense polyphony
- instrument overlap
- modern production FX
- weak supervision for non-piano/pop-in-the-wild cases

### Grouped arrangement patterns

This is the least "solved" part.

A grouped pattern like `drum_fill` or `arp_run` is usually not a primitive acoustic class.
It is a sequence-level structure over lower-level events.

Best route:

1. separate or denoise when useful
2. detect atomic events
3. build an event sequence or graph
4. detect grouped patterns over that structure

Main limitation:

- there is much less standardized benchmark data for these musical-semantic labels
- SCUE-specific classes will likely require custom annotation and few-shot adaptation

---

## Practical Guidance for SCUE

### What stem separation is good for

Use it as:

- a **decomposition prior**
- a **denoising stage**
- a way to convert one hard polyphonic problem into several easier downstream problems

### What stem separation is not

Do not treat it as:

- perfect source recovery
- exact DAW track reconstruction
- guaranteed ground truth for class labels

### The right mental model

For SCUE, I would treat stem separation as:

**a high-value intermediate representation that makes later event extraction and grouping
substantially easier, while still requiring uncertainty-aware downstream models**

---

## Recommended Next Pass

The highest-value next pass is:

**Research the best pipeline from `drum stem -> individual drum events -> grouped drum
fills` for EDM / club music.**

Why this should be next:

- it gives SCUE the most immediate cue-generation value
- stem separation already helps a lot here
- the event vocabulary is manageable
- grouped fills are musically meaningful and visually useful
- it creates a template for later work on vocals and melodic patterns

What I would cover in that pass:

1. SOTA drum transcription from separated drum stems
2. Class taxonomies for EDM-relevant percussion
3. What still breaks in layered / processed club drums
4. How to represent grouped fills over hit streams
5. Whether few-shot methods help for custom fill types
6. Practical model choices for offline SCUE analysis on Apple Silicon

Two good follow-ups after that:

- `vocal stem -> vocal phrase/chop/event detection`
- `non-drum stems -> note/event streams + arp-run grouping`

---

## Sources

- Hybrid Demucs:
  https://arxiv.org/abs/2111.03600
- BS-RoFormer:
  https://arxiv.org/abs/2309.02612
- Mel-Band RoFormer:
  https://arxiv.org/abs/2310.01809
- SDX'23 Music Demixing Track:
  https://arxiv.org/abs/2308.06979
- Peer-reviewed SDX'23 overview:
  https://transactions.ismir.net/articles/10.5334/tismir.171
- MoisesDB:
  https://arxiv.org/abs/2307.15913
- Banquet:
  https://arxiv.org/abs/2406.18747
- STAR Drums:
  https://transactions.ismir.net/articles/10.5334/tismir.244
- Mel-RoFormer vocal separation and melody:
  https://arxiv.org/abs/2409.04702
- MT3:
  https://arxiv.org/abs/2111.03017
- Perceiver TF:
  https://arxiv.org/abs/2306.10785
- YourMT3+:
  https://arxiv.org/abs/2407.04822
