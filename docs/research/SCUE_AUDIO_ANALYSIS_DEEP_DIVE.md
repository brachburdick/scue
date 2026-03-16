# SCUE Audio Analysis Deep Dive

## Report Purpose

This report evaluates established methods for detecting musical events at three hierarchical levels — sections, subsections/phrases, and individual events — within the context of SCUE's EDM-focused analysis pipeline. The goal is to recommend a concrete toolchain, a hierarchical event model, and a testing strategy.

---

## Part 1: Recommended Event Hierarchy

Your current categorization (sections → subsections → individual events) is on the right track, but it conflates two orthogonal dimensions: temporal scale and temporal behavior. The model below separates these cleanly.

### Two-Axis Model: Scale × Behavior

**Axis 1 — Scale (how much time does it span?):**

| Level | Name | Typical Duration | Examples |
|---|---|---|---|
| L1 | **Section** | 8–64 bars (15s–2min) | intro, verse, build, drop, breakdown, outro |
| L2 | **Phrase** | 1–8 bars (2s–15s) | arp run, riser, faller, drum fill, melodic hook, fakeout |
| L3 | **Moment** | Sub-beat to 1 bar | kick, snare, clap, stab, note, chord strike, adlib |

**Axis 2 — Behavior (how does it change over time?):**

| Type | Name | Definition | Examples |
|---|---|---|---|
| D | **Discrete** | Has a clear onset (and optionally an offset). A "thing that happens." | kick, snare, clap, stab, chord strike, note onset, section boundary |
| C | **Continuous** | Has a start, an end, and a value that changes between them. A "thing that evolves." | riser, faller, filter sweep, pitch bend, volume swell, panning oscillation |
| S | **Sustained** | Has a start and end but is relatively static in character while active. A "thing that's present." | held pad, sustained bass, vocal phrase, arp loop (the loop as a whole, not individual notes) |

**Every detected event gets classified on both axes.** A riser is L2-C (phrase-scale, continuous). A kick is L3-D (moment-scale, discrete). An arp run is L2-S (phrase-scale, sustained) — but its individual notes are L3-D (moment-scale, discrete) and are children of the L2-S parent.

### Parent-Child Relationships

This is the key insight you were reaching toward. The hierarchy is:

```
L1 Section: "drop" (bars 33–64)
├── L2 Phrase: "main arp loop" (bars 33–48, sustained)
│   ├── L3 Moment: note C4 (bar 33, beat 1, discrete)
│   ├── L3 Moment: note E4 (bar 33, beat 1.5, discrete)
│   ├── L3 Moment: note G4 (bar 33, beat 2, discrete)
│   └── ...
├── L2 Phrase: "drum fill" (bar 48, beats 3–4, sustained)
│   ├── L3 Moment: snare (bar 48, beat 3, discrete)
│   ├── L3 Moment: snare (bar 48, beat 3.25, discrete)
│   ├── L3 Moment: snare (bar 48, beat 3.5, discrete)
│   └── L3 Moment: snare (bar 48, beat 3.75, discrete)
├── L2 Phrase: "bass oscillation" (bars 33–64, continuous)
│   └── value curve: frequency wobble at 1/4 note rate
├── L3 Moment: kick (bar 33, beat 1, discrete)
├── L3 Moment: kick (bar 33, beat 2, discrete)
└── ... (kicks/snares live directly under section, not under a phrase)
```

Rules:
- Every L3 event lives inside exactly one L1 section (determined by time).
- An L3 event *may* additionally belong to an L2 phrase (if it's part of an identifiable group like an arp or fill).
- An L2 phrase lives inside exactly one L1 section.
- L3 events that aren't part of any phrase (like regular kicks on the beat) are direct children of the L1 section.

### Additional Categories You're Missing

**Pattern repetitions:** Many L3 events form rhythmic patterns that repeat. A "four-on-the-floor kick" isn't just a series of individual kicks — it's a pattern. Detecting the *pattern* (and when it changes) is distinct from detecting individual kicks. Pattern changes are L2-D events (phrase-scale, discrete — the moment the pattern shifts).

**Textural changes:** A section might maintain the same drums and melody but add a new layer (a vocal chop, a new synth pad). These are L2-D events — the onset of a new textural element.

**Silence / space:** The absence of elements is musically meaningful in EDM. A "bass drop-out" (bass disappears for 4 beats before the drop) is an L2-S event (a sustained absence).

---

## Part 2: Stem Separation as a Preprocessing Step

### The Case For It

Running detection algorithms on the full mix is hard. Kicks, snares, basslines, synths, and vocals all overlap in frequency and time. Stem separation dramatically simplifies every downstream task:

- **Drum detection** on an isolated drum stem is a near-solved problem. On a full mix, it's a hard problem with frequent false positives from bass transients.
- **Pitch tracking / arp detection** on an isolated "other" stem (melodic instruments minus drums, bass, and vocals) produces far cleaner results than on the full mix.
- **Riser/faller detection** on individual stems avoids false triggers from drums and bass.
- **The all-in-one model already does this internally.** The allin1 model uses Demucs to separate into 4 stems (bass, drums, other, vocals) before analysis. Its improved performance comes directly from this design choice.

### Recommended Approach

**Use Demucs `htdemucs` as the first step in the analysis pipeline.** Separate every track into 4 stems: drums, bass, other (melodic/harmonic instruments), vocals. Then run all subsequent detection algorithms on the separated stems, not the full mix.

| Model | Quality (SDR) | Speed | GPU Required? |
|---|---|---|---|
| `htdemucs` | 9.0 dB | ~1x real-time on GPU | Recommended |
| `htdemucs_ft` | 9.2 dB (slightly better) | ~4x slower | Recommended |
| `hdemucs_mmi` | 8.5 dB | Faster | Optional |
| `htdemucs_6s` | Adds guitar + piano stems | Variable | Optional, piano quality poor |

**Recommendation:** Use `htdemucs` as default, offer `htdemucs_ft` as an option for users who want higher quality and don't mind the wait. The 4-stem separation (drums, bass, other, vocals) is sufficient for SCUE's needs. The 6-stem model's piano separation is unreliable and isn't useful for EDM.

**Implementation note:** Stem separation is the most computationally expensive step in the pipeline. On a Mac with Apple Silicon, expect ~30–60 seconds per track with `htdemucs`. The separated stems should be cached alongside the track analysis JSON — they're needed for multiple downstream detectors and shouldn't be re-computed.

---

## Part 3: Detection Methods by Level

### L1 — Section Detection

This is the highest-impact detection task for SCUE. Getting section boundaries and labels right drives everything downstream.

#### Option A: allin1 + SCUE post-processing (Recommended for v1)

**What it is:** The all-in-one model you're already using. It jointly predicts beats, downbeats, and section labels from Demucs-separated stems.

**Strengths:** Out-of-the-box, no training required. Handles beat/downbeat/section jointly (they inform each other). Uses source separation internally. State of the art on HarmonixSet.

**Weaknesses for EDM:** Trained on pop music (HarmonixSet). Uses pop labels (verse, chorus, bridge) that don't map cleanly to EDM (build, drop, breakdown). The "chorus" label often corresponds to "drop" in EDM. Section boundaries don't respect the 8-bar grid.

**SCUE's fix:** Use allin1's raw boundary activations and beat/downbeat output, but replace the labeling with SCUE's EDM flow model. Pipeline: allin1 → extract boundary candidates + beat grid → 8-bar snapping → EDM flow model relabeling. This is what the architecture doc already describes.

**Reliability:** Boundary detection F-measure ~0.7–0.75 on pop music. Lower on EDM specifically, but the 8-bar snapping pass should recover most errors. Labeling is the weak point — relabeling with the EDM flow model is essential.

**Implementation difficulty:** Low. allin1 is pip-installable. The post-processing (snapping, relabeling) is custom code but straightforward.

#### Option B: EDMFormer (Watch, not ready yet)

**What it is:** A transformer model trained specifically on EDM with an EDM-specific taxonomy (intro, build-up, drop, breakdown, outro). Released March 2025, published with a 98-track annotated EDM dataset.

**Strengths:** Uses EDM-native labels. Trained on EDM data. Reportedly improves boundary detection and labeling for drops and buildups specifically.

**Weaknesses:** Very new (one week old as of research date). Tiny training set (98 tracks). Not pip-installable yet. No established community or production track record.

**Recommendation:** Monitor this project. If it matures and becomes pip-installable with a larger training set, it could replace allin1 as the section detector. For now, stick with allin1 + post-processing.

#### Option C: Self-similarity matrix + spectral clustering (Fallback / comparison)

**What it is:** The classic unsupervised approach. Compute self-similarity using chroma or MFCC features, then apply spectral clustering or novelty curve peak-picking to find boundaries. No ML model needed.

**Strengths:** No training data dependency. Works on any genre. Transparent — you can inspect the self-similarity matrix. Good for catching repetition-based structure.

**Weaknesses:** Finds repeated sections but doesn't label them. Struggles with EDM specifically because EDM structure is energy/texture-based, not repetition-based (a build and a drop may use the same chord progression).

**Recommendation:** Implement as a comparison baseline for testing. Run both allin1 and self-similarity, and flag tracks where they disagree for manual review. Not a primary detector.

### L3 — Moment Detection (Individual Events)

I'm covering L3 before L2 because phrase detection (L2) largely builds on top of moment detection results.

#### Drum Events (kick, snare, hihat, clap)

**Recommended approach: Onset detection on Demucs drum stem → classification**

Step 1: Separate the drum stem using Demucs.
Step 2: Run onset detection on the drum stem using `madmom.features.onsets.RNNOnsetProcessor` or `librosa.onset.onset_detect`. madmom's RNN-based onset detector is more accurate on percussion; librosa's is simpler and faster.
Step 3: For each detected onset, extract a short window (~100ms) around the onset time.
Step 4: Classify the window as kick / snare / hihat / clap / other using spectral features.

**Classification approach:** A simple classifier (random forest or small CNN) trained on a few hundred labeled drum samples per class, using MFCC + spectral centroid + spectral bandwidth as features. The drum stem is already isolated, so the classification problem is much easier than in a full mix. Libraries like `scikit-learn` or a small TensorFlow model work fine.

**Alternative: ADTLib** — An automatic drum transcription library that does onset detection + classification in one step. Uses pre-trained neural networks for kick/snare/hihat detection. Less flexible but ready to use.

**Reliability:** On isolated drum stems, expect ~90%+ accuracy for kick vs snare vs hihat classification. The main failure mode is misclassifying claps as snares (they're genuinely similar in many EDM tracks).

**Implementation difficulty:** Low-medium. The stem separation does the heavy lifting. The classifier is small and easy to train from drum sample packs.

#### Pitched Events (notes, chords, arps)

**Recommended approach: Spotify's Basic Pitch on Demucs "other" stem**

Step 1: Separate the "other" stem (everything minus drums, bass, vocals) using Demucs.
Step 2: Run Basic Pitch on the "other" stem to get MIDI note events (onset time, offset time, pitch, velocity).
Step 3: Optionally, also run Basic Pitch on the bass stem separately for bass note detection.

**Why Basic Pitch:** It's polyphonic (handles chords and arps), instrument-agnostic, lightweight (runs faster than real-time), outputs MIDI with pitch bends, and is pip-installable. It works best on one instrument at a time — which is exactly what stem separation gives you.

**Reliability:** On isolated stems, note-level F-measure ~70–80%. On full mixes, it drops to ~40%. This is why stem separation is critical. Accuracy is higher for monophonic lines (bass, lead melody) than for dense chords.

**Alternative: librosa.pyin** for monophonic pitch tracking (bass lines, single lead synths). Better for continuous pitch tracking (pitch bends, vibrato) but only handles one note at a time. Use Basic Pitch for polyphonic content and pyin for the bass stem if Basic Pitch's bass note detection isn't accurate enough.

**Implementation difficulty:** Low. Basic Pitch is pip-installable. Output is standard MIDI events.

#### Stabs / Adlibs / One-Shots

**Recommended approach: Onset detection on "other" stem + short-duration filtering**

Stabs and adlibs are short, often percussive melodic events. After running Basic Pitch, filter the note events: any note with duration < ~200ms and high onset velocity that doesn't fit into a repeated pattern is likely a stab or adlib.

Alternatively, use `librosa.onset.onset_detect` on the "other" stem with a high `backtrack` parameter to catch sharp transients, then cross-reference against Basic Pitch's note events. Onsets that don't correspond to a Basic Pitch note are likely non-pitched stabs (noise hits, impacts, vocal chops).

**Reliability:** Medium. Stabs and adlibs are the hardest events to detect reliably because they're diverse in character and infrequent. Start by detecting them as "short, loud, non-pattern events" and refine from there.

### L2 — Phrase Detection (Subsections)

Phrase detection largely builds on top of L3 moment-level results and L1 section context.

#### Arpeggios

**Approach:** After Basic Pitch produces note events on the "other" stem, scan for sequences of notes that form a repeating pitch pattern within a short time window. An arp is characterized by: notes at regular (or near-regular) rhythmic intervals, a repeating pitch sequence (e.g., [C, E, G, C, G, E] repeating), and individual note durations shorter than the inter-onset interval (notes don't sustain into each other).

**Algorithm:** Quantize note onsets to the beat grid. Group consecutive notes within the same stem. Check for pitch-interval pattern repetition using circular pattern matching. If a pattern of length N repeats M times (M ≥ 2), classify it as an arp.

**Output:** Arp phrase with: start/end time, pattern (as relative intervals from root), repetition count, note rate (16ths, 8ths, triplets). Each constituent note is an L3 child.

**Reliability:** High when the arp is isolated in the "other" stem. Lower when multiple melodic instruments overlap. The quantization to beat grid helps reject false patterns.

#### Risers and Fallers

**Approach:** These are continuous broadband energy increases (risers) or decreases (fallers) over 1–16 bars. Detect them using spectral flux computed over a long window.

**Algorithm:**
1. Compute spectral flux on the full mix (not stems — risers are often full-mix phenomena).
2. Apply a long moving average (2–8 seconds) to get a smoothed energy trajectory.
3. Compute the derivative of the smoothed trajectory.
4. Sustained positive derivative above a threshold = riser. Sustained negative = faller.
5. Refine by checking the "other" stem for spectral centroid increase (risers typically sweep from low to high frequency).

**Also useful:** On the "other" stem, track spectral centroid over time. A monotonically increasing spectral centroid over several bars strongly indicates a riser (filter opening). A decreasing centroid indicates a faller.

**Output:** Riser/faller phrase with: start/end time, intensity curve (the smoothed energy trajectory), type (noise-based, pitched, filter sweep).

**Reliability:** Medium-high for typical EDM risers (white noise + filter sweep). Lower for subtle risers (volume-only, no spectral change).

#### Filter Sweeps / Panning / Modulation Effects

**Approach:** Track spectral centroid, stereo width, and spectral contrast over time on relevant stems.

**Algorithm for filter sweeps:** Compute spectral centroid per frame on the "other" or "bass" stem. Smooth over ~0.5s. A sinusoidal or monotonic centroid trajectory indicates a filter sweep. Detect oscillation frequency for LFO-driven sweeps.

**Algorithm for panning:** Compute left-right energy ratio per frame. Oscillation in this ratio = auto-panning. Can also detect from stereo correlation coefficient changes.

**Reliability:** Medium. These are subtle effects and prone to false positives from other spectral changes.

#### Drum Pattern Changes

**Approach:** After detecting individual drum events (L3), quantize them to the beat grid and compute a "drum pattern fingerprint" per bar or per 2 bars. When the fingerprint changes significantly, that's a pattern change event.

**Algorithm:** For each bar, create a binary vector: which 16th-note subdivisions have a kick, which have a snare, which have a hihat. Compare consecutive bars using Hamming distance. A sudden change (distance above threshold) = pattern change event. A gradual increase in density (more hits per bar) over several bars = intensification (common in builds).

**Output:** Pattern change event with: time, old pattern description, new pattern description, type (density change, element addition, fill).

**Reliability:** High on isolated drum stems. The beat grid quantization is critical — errors in the beat grid propagate directly into pattern detection errors. This is another reason Pioneer enrichment matters.

---

## Part 4: Recommended Toolchain Summary

| Task | Tool | Runs On | Input |
|---|---|---|---|
| Stem separation | **Demucs htdemucs** | Full mix | Audio file |
| Beat/downbeat tracking | **allin1** (uses madmom internally) | Full mix | Audio file |
| Section boundaries | **allin1** raw activations | Full mix (via stems) | Audio file |
| Section labeling | **SCUE EDM flow model** (custom) | allin1 output | Boundary candidates + beat grid |
| Drum onset detection | **madmom RNNOnsetProcessor** | Drum stem | Demucs drums output |
| Drum classification | **Small CNN or random forest** (custom) | Drum stem windows | Onset windows |
| Pitch/note detection | **Basic Pitch** (Spotify) | "Other" stem, bass stem | Demucs other/bass output |
| Arp detection | **Custom pattern matcher** | Basic Pitch output | Note events + beat grid |
| Riser/faller detection | **Spectral flux + centroid** (librosa) | Full mix + "other" stem | Audio |
| Filter/panning effects | **Spectral centroid + stereo analysis** (librosa) | Relevant stems | Audio |
| Drum pattern analysis | **Custom quantization + fingerprinting** | Drum onset events | L3 drum events + beat grid |

### Analysis Pipeline Order

```
Audio file
  │
  ├──→ Demucs htdemucs → drums, bass, other, vocals stems (cached)
  │
  ├──→ allin1 → beats, downbeats, raw section boundaries + labels
  │       │
  │       └──→ SCUE 8-bar snap + EDM flow model → L1 sections
  │
  ├──→ [drums stem] → madmom onset detect → drum classifier → L3 drum events
  │       │
  │       └──→ quantize to grid → pattern fingerprint → L2 pattern changes
  │
  ├──→ [other stem] → Basic Pitch → L3 note events
  │       │
  │       ├──→ pattern matcher → L2 arp phrases
  │       └──→ short-event filter → L3 stabs/adlibs
  │
  ├──→ [bass stem] → Basic Pitch or pyin → L3 bass notes
  │
  ├──→ [full mix + other stem] → spectral flux + centroid → L2 risers/fallers
  │
  └──→ [other stem] → spectral centroid + stereo analysis → L2 filter sweeps/panning
```

---

## Part 5: Testing Strategy

### Evaluation Framework

Build a test harness that can compare detection results against hand-labeled ground truth. Use `mir_eval` for standard MIR metrics where applicable.

### Per-Level Test Approach

**L1 Section testing:**
- Hand-label 5–10 tracks across genres (house, techno, dubstep, DnB, trance).
- Metrics: Boundary detection F-measure at 0.5s and 3s tolerance (via `mir_eval.segment`). Label accuracy (% of segments with correct EDM label).
- Compare: allin1 raw output vs. allin1 + 8-bar snap vs. allin1 + 8-bar snap + flow model. This isolates the value of each post-processing stage.

**L3 Drum event testing:**
- Use 3–5 tracks where you manually mark kick/snare/hihat onsets (tedious but essential — even marking 30 seconds per track is useful).
- Metrics: Onset F-measure at ±50ms tolerance. Classification accuracy per drum type.
- Compare: onset detection on full mix vs. on drum stem. This quantifies the value of stem separation.

**L3 Pitched event testing:**
- Select tracks with known, simple melodic content (arps with identifiable patterns).
- Run Basic Pitch on full mix vs. on "other" stem. Compare MIDI output against hand-transcribed reference.
- Metrics: Note-level F-measure (onset within ±50ms, pitch within ±1 semitone).

**L2 Riser/faller testing:**
- Select 5 tracks with obvious risers/fallers (build sections in trance/progressive house are ideal).
- Hand-mark riser start/end times.
- Metrics: Detection F-measure (detected riser overlaps ground truth by ≥50%). False positive rate.

**L2 Arp testing:**
- Select tracks with known arps.
- Verify: correct note pattern, correct start/end time, correct note rate classification.

### A/B Testing Infrastructure

Build the pipeline so you can swap individual detectors and compare. Each detector should conform to a standard interface:

```python
class Detector(Protocol):
    def detect(self, audio: np.ndarray, sr: int, beat_grid: list[float]) -> list[Event]:
        ...
```

This lets you run the same test tracks through multiple detector implementations and compare output. When a better drum classifier or section model comes along, you swap the implementation and re-run the test suite.

### The "Disagreement Log" Pattern

When two detection methods disagree (e.g., allin1 says section boundary at bar 32 but self-similarity says bar 33), log the disagreement rather than silently picking one. Over time, this log — like the Pioneer divergence log — reveals which methods are systematically better for which scenarios.

---

## Part 6: Build Priority

| Priority | Detection Task | Why This Order |
|---|---|---|
| 1 | Stem separation (Demucs) | Everything downstream benefits. Do this first. |
| 2 | Section boundaries + labels (allin1 + post-processing) | Highest impact for cue generation. Already partially built. |
| 3 | Beat/downbeat grid | Already provided by allin1. Pioneer enrichment improves it. |
| 4 | Drum onset + classification | Enables kick/snare cues for beat-reactive lighting. High visual impact. |
| 5 | Riser/faller detection | Enables anticipation-based lighting (building intensity before drops). |
| 6 | Basic Pitch note detection | Enables melodic cues (arps, note patterns). |
| 7 | Arp pattern detection | Enables runner/chase effects synchronized to melodic patterns. |
| 8 | Drum pattern analysis | Enables pattern-change cues (snare doubling before drops). |
| 9 | Filter sweep / panning / modulation | Enables spatial lighting effects. Hardest to detect reliably. |
| 10 | Stab / adlib detection | Low frequency, hard to detect, small visual impact. |

Items 1–5 should be part of Milestones 1 and 7. Items 6–10 are refinements for later milestones.
