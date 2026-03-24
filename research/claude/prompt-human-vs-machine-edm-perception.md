# Research Agent Prompt: Human vs Machine EDM Arrangement Perception

**Created:** 2026-03-22
**Purpose:** Hand this prompt to a research agent to investigate why humans can easily parse EDM arrangements while SOTA ML struggles.

---

## The Prompt

You are researching a specific question for a DJ/producer who is building an audio analysis tool (called SCUE) that extracts arrangement formulas from finished stereo mixes. The tool identifies individual acoustic events, classifies instruments, detects grouped patterns (drum fills, arp runs, risers), and maps the arrangement structure.

### The core question

**Why is EDM one of the hardest genres for computational audio analysis (source separation, event detection, transcription), when a trained human listener can hear an EDM track once and sketch out a fairly accurate arrangement — distinguishing kicks from synth layers, identifying fills, hearing risers, separating vocal chops from pads — with relative ease?**

Is this purely a "human brains are magic pattern recognizers" story, or are there specific computational/representational gaps that, if closed, would bring machines closer to human-level arrangement perception for dense electronic music?

### What to investigate

1. **Auditory scene analysis (ASA) literature** — Bregman's work and its descendants. How does the human auditory system solve the "cocktail party problem" for music? What principles (common fate, onset synchrony, harmonic relatedness, spatial cues, continuity) does the brain exploit that current models don't fully leverage?

2. **Gestalt grouping in music perception** — How do listeners group sounds into "objects" (a kick with its saturation harmonics, a synth pad with its reverb tail) rather than treating each frequency bin independently? How does prior knowledge of music production conventions help human listeners assign ambiguous energy to the right source?

3. **Top-down vs bottom-up processing** — Humans use both:
   - Bottom-up: raw spectral/temporal features
   - Top-down: "I know this genre has a kick on every beat, so that transient is probably a kick"

   How much of human advantage comes from top-down musical knowledge (genre conventions, arrangement expectations, production norms) vs raw perceptual superiority?

4. **The EDM-specific angle** — EDM has characteristics that make it simultaneously:
   - Hard for machines: dense layering, shared frequency bands, heavy processing, synthesized sounds without natural acoustic priors
   - Predictable for humans: rigid structure (4-bar phrases, 8/16/32 bar sections), genre-specific sound design conventions, repetition-based arrangement, clear energy arcs

   Is the human advantage partly that EDM's *structural predictability* compensates for its *spectral complexity*? A human who knows "drops have layered supersaws over sub bass with a snare on 2 and 4" can hear through the spectral mess because they know what to expect.

5. **Computational models of music cognition** — Are there models that attempt to replicate human music perception computationally? Look at:
   - Temperley's probabilistic models of music cognition
   - Expectation-based models (IDyOM, etc.)
   - Schema theory applied to music
   - Any work on computational auditory scene analysis (CASA) applied to music specifically

6. **The gap analysis** — Based on findings, identify the specific representational or architectural gaps between current ML approaches and human perception:
   - Do current models lack long-range structural context?
   - Do they lack genre-specific priors?
   - Do they lack multi-scale temporal processing (micro: transient shape; meso: phrase patterns; macro: arrangement arc)?
   - Do they process frequency bins independently rather than as coherent "auditory objects"?
   - Is the training data problem (no large-scale EDM stems dataset) the bottleneck, or is it architectural?

7. **Bridging work** — Any research explicitly trying to bridge cognitive music perception and ML audio analysis. Examples might include:
   - Neural networks inspired by auditory cortex processing
   - Models that incorporate musical structure priors
   - Systems that combine bottom-up feature extraction with top-down musical knowledge
   - Few-shot or meta-learning approaches that capture the "listen once, understand the pattern" ability humans have

### Context from prior research

The user has already done deep research on the following (do not re-cover this ground, but reference it as needed):

**Stem separation findings** (in `scue/research/claude/findings-stem-separation-limits-and-frontiers-2026-03.md`):
- SOTA: BS-RoFormer, Mel-Band RoFormer, HT Demucs, Banquet (query-based)
- Not solved — strong for coarse 4-stem, weak for fine-grained
- Fundamental limit: stereo mix is underdetermined (2 channels, 20-100+ tracks)
- Shared effects (reverb, bus compression, sidechain, mastering) blur source boundaries
- Music Source Restoration (MSR) is the new frontier attacking production-effect inversion
- EDM is one of the hardest genres for separation
- Percussion is the hardest stem to restore in MSR (0.29 dB average)

**Arrangement formula / AED / few-shot findings** (in `scue/research/gpt/findings-arrangement-formula-aed-few-shot-2026-03.md`):
- Best approach is stacked pipeline: backbone embeddings → separation → atomic detectors → event graph → pattern grouping
- Recommended backbones: ATST-Frame/BEATs for timing, MERT/MuQ for music semantics
- Few-shot works as adaptation layer on frozen embeddings (prototype networks, exemplar matching)
- Grouped events (fills, runs) are sequence structures over atomic events, not raw acoustic primitives
- Open-vocabulary (CLAP, FlexSED) promising but early

**Key references already covered** (don't re-research these, but you can reference):
- DCASE 2024 Tasks 4 & 5
- ATST, BEATs, MERT, MuQ, MuLan
- MT3, Perceiver TF, YourMT3+
- CLAP, FlexSED
- Apple few-shot acoustic sequence detection
- STAR Drums, StemGMD/LarsNet
- MSRBench, MSR Challenge

### Output format

Write findings as a research document with:
1. Executive summary (3-5 sentences)
2. Findings organized by investigation area
3. A "gap analysis" section that maps specific human perceptual abilities to missing ML capabilities
4. Practical implications for SCUE's architecture
5. Sources with links

Save the output to: `scue/research/claude/findings-human-vs-machine-edm-perception-2026-03.md`
