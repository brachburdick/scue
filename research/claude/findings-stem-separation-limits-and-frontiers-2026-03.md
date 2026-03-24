# Stem Separation: State of the Art, Limits, and Open Frontiers

**Date:** 2026-03-22
**Status:** Complete
**Context:** Brach asked whether stem separation is "solved," what SOTA approaches do, what their fundamental limits are, and what research is attacking those limits — particularly for downstream use in an arrangement-formula extractor for EDM.

---

## Is Stem Separation Solved?

**No.** It is strong enough to be a practical building block, but not a solved problem.

- For **2-stem** (vocals / instrumental) and **4-stem** (vocals / drums / bass / other), current models are good enough for many production workflows.
- For **fine-grained stems** (kick vs snare vs toms, piano vs organ, clean vs distorted guitar), quality drops significantly.
- For **EDM specifically**, separation is harder than average due to overlapping frequency content between synthesizers and drums, heavy layered processing, and shared bus effects.

The field is still moving fast. BS-RoFormer SW beat the previous MUSDB18HQ SOTA by 2+ dB SDR average. New model families and new problem formulations (Music Source Restoration) are still producing material improvements.

---

## How SOTA Separation Actually Works

Modern stem separation is **not frequency-band splitting**. That intuition is decades out of date.

### What the models actually learn

SOTA separators learn source structure across multiple dimensions simultaneously:

- **Time** — transient shape, attack/decay envelope, onset timing
- **Frequency** — harmonic series, formant structure, spectral envelope
- **Stereo cues** — panning position, stereo width, inter-channel differences
- **Context** — what came before and after an overlap region
- **Source priors** — what a "kick" or a "vocal" tends to look like spectrally and temporally

### Current model families

| Model | Approach | Strengths |
|---|---|---|
| **BS-RoFormer** | Band-split front-end + hierarchical RoPE Transformers across bands | Best overall SDR; strong frequency resolution |
| **Mel-Band RoFormer** | Overlapping mel-aligned subbands + Transformers | Dominates vocal separation (selected for 97% of songs in benchmarks); better perceptual frequency resolution |
| **HT Demucs** | Hybrid waveform + spectrogram branches with Transformer cross-attention | Most versatile; can decide which domain suits each source; better on transient-heavy sources |
| **Banquet** | Query-based single-decoder, conditioned on requested stem | Stem-agnostic; supports fine-grained/long-tail instruments at only 24.9M params; outperforms HT Demucs on guitar and piano |

### Key architectural insight

The hybrid approach matters because **different sources are better modeled in different domains**:
- Transients, phase, attack/decay → time domain
- Harmonics, partials, broadband masks → frequency domain

HT Demucs explicitly lets the model choose. BS-RoFormer gets similar benefits through hierarchical band modeling.

### The query-based direction (Banquet)

This is the most important architectural trend for your use case. Instead of hardcoding N stem outputs, you condition the separator on a query:

- "give me the kick"
- "give me clean acoustic guitar"
- "give me reeds"

Banquet showed this works competitively at ISMIR 2024. It uses a PaSST instrument recognition model to condition a bandsplit separator. This means you can potentially separate narrow instrument classes without multiplying model size.

---

## Stem Categories

There is no universal taxonomy. Categories depend on the dataset and product.

### Standard benchmarks
- **2-stem:** vocals, instrumental
- **4-stem (VDBO):** vocals, drums, bass, other

### Extended benchmarks (MoisesDB)
- Hierarchical taxonomy supporting 4-, 5-, and 6-stem evaluation
- Typical: vocals, drums, bass, guitar, piano/keys, other

### Fine-grained (commercial / query-based)
- kick, snare, hi-hat, toms, cymbals
- lead vocals, backing vocals
- piano, organ, acoustic guitar, electric guitar
- synth lead, synth pad, reeds
- ...but quality varies much more than coarse stems

---

## The Fundamental Limits

### 1. The mixture is underdetermined

A stereo mix has 2 channels. A typical production has 20-100+ tracks. You cannot uniquely recover every source from 2 channels. The model is always making informed guesses using learned priors.

Your kick+synth example lives here: the decaying kick has upper harmonics from saturation; a synth enters occupying the same frequency band. The model can use:
- transient shape (kick has a sharp attack, synth doesn't)
- decay pattern (kick decays, synth sustains)
- repetition (kick repeats on a rhythmic grid)
- spectral context (kick harmonics have a characteristic roll-off)

But when overlap is severe enough, it has to guess. And in EDM, overlap is often severe.

### 2. Shared effects destroy source boundaries

This is arguably the biggest practical limit, and the one the field is now actively attacking.

In a professional mix, energy that "belongs" to one source gets smeared across the mix by:
- **Reverb sends** — multiple sources share a reverb bus; the tail is a mixture
- **Bus compression** — drum bus, mix bus compression creates inter-source dynamics
- **Sidechain** — kick ducks the bass/pad; the ducking artifact is a product of both
- **Saturation/distortion** — generates new harmonics that weren't in the original
- **Mastering EQ and limiting** — reshapes everything globally
- **Delay throws** — feed multiple sources into shared delays

Current separators assume `mix = sum(sources)`. That's wrong. The real equation is more like:
```
mix = master_chain(bus_processing(sum(per_source_processing(source_i))))
```

And inverting that chain is a different, harder problem.

### 3. The new frontier: Music Source Restoration (MSR)

This is the research that directly attacks limit #2.

**MSR** (introduced as an ICASSP 2026 Grand Challenge) redefines the goal: recover the **original unprocessed stems** from a mastered mix. This requires inverting:
- per-instrument EQ, compression, saturation, spatial effects
- bus processing (group compression, corrective EQ, shared reverb/delay)
- mastering chain

Key findings from the inaugural MSR Challenge (5 teams):
- **Winning system:** 4.46 dB Multi-Mel-SNR (91% improvement over 2nd place)
- **Per-stem difficulty varies enormously:** bass averaged 4.59 dB across teams; percussion averaged only 0.29 dB
- Percussion is the hardest to restore — exactly the stem SCUE cares about most for drum event detection
- The MSRBench dataset has 2,000 professionally mixed clips with parallel processed/unprocessed stems

**Why this matters for SCUE:** MSR research is directly studying the problem of disentangling shared production effects. Even if you don't use MSR models directly, the techniques and insights about inverting non-linear production chains will inform how you handle the artifacts that stem separation leaves behind.

### 4. Fine-grained stems are much harder

Broad categories work because they're spectrally and temporally distinct. As you go finer:
- piano vs organ (both sustained, harmonic, mid-frequency)
- toms vs snare vs clap (similar frequency ranges, short transients)
- synth lead vs synth pad (same synthesis engine, different ADSR)
- FX riser vs pad wash (both broadband, evolving)

...the problem gets substantially harder because the learned priors have less to distinguish.

### 5. EDM is one of the hardest genres

Research confirms this directly:
- In electronic and rap, bass separation suffers due to overlap with kick drums and sub-bass elements
- Drum stems are harder in electronic and rock due to complex effects and heavy production
- The layered nature of synthesized sounds combined with heavy processing creates difficulty that simpler genres don't have

---

## Does a Good Drum Stem Make Drum Classification Trivial?

**Dramatically easier, not trivial.**

The pipeline `separate drums → classify individual hits` is the right approach, and recent research validates it:

### STAR Drums dataset findings
- Training ADT on STAR Drums data outperforms MIDI-rendered-only training
- The primary limiting factor for drum transcription with melodic instruments present is **interference from those melodic instruments** — which separation largely removes
- But after separation, you still face: cymbal wash masking transients, layered hits blurring boundaries, processed drums resembling synth noise

### Enhanced ADT via stem separation (2025)
- Recent work separates drum stems into 6+ classes (kick, snare, hi-hat, toms, ride, crash)
- Per-stem RMS curves expand transcription from 5 to 7 classes with velocity estimation
- F-measure improved 12% over baselines

### What's still hard after separation
- Layered kicks (sub + click + distortion layer)
- Parallel-processed drums (dry + compressed + saturated copies summed)
- Ghost notes and rolls at low velocity
- Hybrid percussion (is a filtered noise burst a hi-hat or a synth perc?)
- EDM drum design that intentionally blurs the line between drums and synths

---

## Same Story for Vocals

Separated vocals make downstream tasks much easier but don't collapse them:
- Vocal activity detection: easy on a clean stem
- Melody extraction: easier but still needs its own model
- Vocal chop detection: needs temporal pattern analysis beyond just "voice present"
- Phrase boundaries: still an open problem

---

## The Research Frontier: What's Being Worked On

### Active areas attacking the limits above

| Problem | Research direction | Key work |
|---|---|---|
| Shared effects / production chain | Music Source Restoration (MSR) | ICASSP 2026 Grand Challenge, MSRBench, RawStems dataset |
| Fine-grained stems | Query-based separation (Banquet) | ISMIR 2024 |
| EDM-specific overlap | Genre-conditioned separation, per-stem difficulty analysis | MSR challenge per-stem results |
| Underdetermined mixture | Stereo-aware band-split models, multi-channel extensions | SIMO Stereo BSR |
| Temporal context for attribution | RoPE positional encoding giving long-range context | BS-RoFormer, Mel-Band RoFormer |
| Dataset quality | Professional mixing + unprocessed stems | MSRBench, RawStems (578 songs, 354 hours) |

### What to watch

1. **MSR maturation** — as teams get better at inverting production effects, the "shared effects destroy boundaries" problem shrinks
2. **Query-based separation scaling** — Banquet is 24.9M params; scaling this with better instrument recognition could unlock true per-instrument separation
3. **Cascaded pipelines** — coarse separation → fine separation → event detection, where each stage benefits from cleaner input
4. **Genre-specific fine-tuning** — EDM-specific separators trained on EDM stems could close the genre gap

---

## Practical Implications for SCUE

1. **Use separation as a decomposition prior, not ground truth.** Treat separated stems as "probably right, verify downstream."

2. **The drum stem is your highest-value separation target.** After separation, drum event classification becomes tractable with relatively simple models. But budget for handling artifacts and edge cases.

3. **Bus/shared effects are your biggest enemy.** Sidechain pumping, shared reverb tails, and bus compression create energy that genuinely belongs to multiple sources. MSR research is the frontier here.

4. **Query-based separation (Banquet-style) is the right direction for fine-grained needs.** Don't commit to a fixed stem taxonomy — use a model that can be queried for arbitrary instruments.

5. **Percussion MSR is the hardest subproblem.** The MSR challenge showed percussion scoring 0.29 dB average — by far the worst stem. This means your drum pipeline will face the most artifacts from production effects.

6. **EDM is genuinely harder** for these models. Plan for lower separation quality and build your downstream detectors to be robust to bleed.

---

## Sources

- BS-RoFormer: https://arxiv.org/abs/2309.02612
- Mel-Band RoFormer: https://arxiv.org/abs/2310.01809
- HT Demucs: https://arxiv.org/abs/2211.08553
- Banquet (stem-agnostic separation): https://arxiv.org/abs/2406.18747
- SDX'23 Music Demixing Challenge: https://arxiv.org/abs/2308.06979
- MoisesDB: https://arxiv.org/abs/2307.15913
- Music Source Restoration (MSR) paper: https://arxiv.org/abs/2505.21827
- MSRBench dataset: https://arxiv.org/abs/2510.10995
- MSR Challenge summary: https://arxiv.org/abs/2601.04343
- MSR Challenge site: https://msrchallenge.com/
- STAR Drums: https://transactions.ismir.net/articles/10.5334/tismir.244
- Enhanced ADT via stem separation: https://arxiv.org/abs/2509.24853
- Ensemble approach to MSS (genre analysis): https://arxiv.org/abs/2410.20773
- DTT-BSR (GAN for MSR): https://arxiv.org/abs/2602.19825
- MSR with ensemble separation: https://arxiv.org/abs/2603.16926
