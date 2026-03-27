# Research Findings: Layer 2 Cue Generation Architecture

**Date:** 2026-03-25
**Status:** Complete — research phase. Implementation planning follows.

---

## Executive Summary

Layer 2's job is to translate a stream of musical events into a stream of semantic cues that
Layer 3 can map to visual effects. The core challenge: doing this in a way that (a) works well
out of the box, (b) lets users remap event→cue logic at will, (c) degrades gracefully across
data tiers, and (d) doesn't need a rewrite as the system matures.

After surveying commercial products (SoundSwitch, MaestroDMX, Rekordbox Lighting), open-source
projects (music-reactive-lighting, QLC+, LightJams), lighting designer practices, academic
frameworks (Russell's Circumplex, CEP, dramatic arc theory), and SCUE's existing data models,
the recommended architecture is:

**A declarative rule engine with rich event context and tiered data support.**

---

## What Exists Externally

### Commercial Products

| Product | Approach | Key Insight for SCUE |
|---------|----------|---------------------|
| **SoundSwitch / Engine Lighting** | Pre-analyzes tracks → stores per-track "lighting scripts" (cue sequences). Phrase detection drives scene selection. 32 beat-synced fallback "Autoloops." | Pre-analyzed tracks get custom shows; unknown tracks get generic beat-reactive fallbacks. SCUE should follow this tiered model. |
| **MaestroDMX** | Real-time only, no pre-analysis. Listens to audio and responds to energy/rhythm/intensity. Sub-10ms latency. Color palettes per mood. | Proof that real-time-only can produce good results. Energy contour + beat detection alone can drive a show. The "palette per mood" concept maps to SCUE's section energy heuristics. |
| **Rekordbox Lighting Mode** | Uses Pioneer PSSI phrase analysis directly. Maps phrase type → lighting pattern. Mood (HIGH/MID/LOW) determines which phrase vocabulary applies. | SCUE already parses PSSI. This is essentially what the Pioneer-only tier should do. Rekordbox's simplicity here is instructive — phrase label + beat grid is enough for a baseline show. |

### Open Source

| Project | Approach | Key Insight for SCUE |
|---------|----------|---------------------|
| **[music-reactive-lighting](https://github.com/CanYuzbey/music-reactive-lighting)** | HPSS → tri-band exertion scores → Russell's Circumplex (valence × arousal) → 360° hue mapping. Includes reinforcement learning from human feedback. | **Most architecturally relevant.** The "exertion" concept (energy relative to rolling average) is exactly what SCUE should adopt. Russell's Circumplex as the bridge between audio features and visual output is elegant. Color Block Inertia (locks palette during high arousal) and Strobe Debouncing (120ms cooldown) are directly applicable to SCUE's cue density problem. |
| **audio-reactive-led-strip** and derivatives | Simple FFT → LED mapping. Volume/frequency → brightness/color. | Too simple for SCUE but proves the baseline: even volume→brightness creates a usable show. |

### Lighting Designer Mental Models

From [Mark LaPierre's cueing methodology](https://www.mlp-lighting.com/programming/lighting-music-basics-4-the-cueing/):

1. **"Visual Home"** — Each song has a visual anchor (color/look) you depart from and return to. Maps to: section-level palette assignment.
2. **Tension/Release** — Verse builds tension, chorus releases. Maps to: energy_trend field on cues.
3. **Two-Color Restraint** — A song is typically two contrasting colors. Maps to: palette should be minimal, not a rainbow.
4. **Cue-Per-Section** — If you have a cue for each section, you're in good shape. Maps to: section_change is the highest-priority cue type.
5. **Anticipatory Timing** — Pressing "Go" on the downbeat is already late. Maps to: section_anticipation cue must fire BEFORE the transition, not on it.
6. **Inhibitive Control** — The ability to reduce intensity without disrupting programmed sequences. Maps to: Layer 3 should have a master intensity/inhibit control separate from cue routing.

### Academic/Theoretical Frameworks

| Framework | Relevance |
|-----------|-----------|
| **Russell's Circumplex Model** | 2D emotional space (valence × arousal). Used by music-reactive-lighting to bridge audio→visual. SCUE should adopt this as the "mood dimensions" on MusicalContext. |
| **Dramatic Arc** (Ableton) | Exposition → rising action → climax → falling action → dénouement. Maps directly to EDM: intro → build → drop → breakdown → outro. SCUE's section labels already encode this. |
| **Complex Event Processing (CEP)** | Formal framework for "when these conditions co-occur within this time window, fire this action." Exactly what Layer 2's rule engine needs. Drools-style temporal reasoning is the right mental model. |
| **EDM tension/release** | Automation, risers, filter sweeps, rhythmic density changes all build tension. Drops release it. Layer 2 should track "tension" as a continuous dimension, not just "energy." |

---

## Architecture Recommendations

### Core Principle: Layer 2 is a Music-Domain Rule Engine

Layer 2 receives ALL events from Layer 1 (nothing pre-filtered). It evaluates rules against
the current musical context to produce richly annotated CueEvents. Layer 3 receives these cues
and makes visual decisions via its routing table.

**Layer 2 answers:** "What is happening musically, and how significant is it?"
**Layer 3 answers:** "What should that look like?"

### The CueEvent Should Be Richly Annotated

Every CueEvent should carry enough context that Layer 3's routing conditions are simple
pattern matches, not music theory. The current CueEvent has `musical_context` with
`section_label`, `section_progress`, `track_energy`, `track_mood`. Extend this to include:

```python
@dataclass
class MusicalContext:
    # Existing
    section_label: str          # intro, verse, build, drop, breakdown, outro
    section_progress: float     # 0.0-1.0
    track_energy: float         # 0.0-1.0 (absolute)
    track_mood: str             # dark, euphoric, melancholic, aggressive, neutral

    # Proposed additions
    energy_exertion: float      # current energy / rolling average (relative)
    energy_trend: str           # rising, falling, stable, peak, valley
    tension: float              # 0.0-1.0 (builds before drops, releases after)
    arousal: float              # 0.0-1.0 (Russell's model: energy dimension)
    valence: float              # 0.0-1.0 (Russell's model: mood dimension)
    data_tier: str              # "full" | "pioneer_live" | "beat_only"
    confidence: float           # 0.0-1.0 (how much we trust these values)
```

### Tiered Graceful Degradation

| Tier | Data Available | Cue Types Available | Context Quality |
|------|---------------|--------------------|-|
| **Full** (offline analysis + M7 events) | ArrangementFormula, all detected events, energy curves, drum patterns | All cue types. Full context. | High confidence |
| **Pioneer Live** (PSSI phrases + beat grid + waveform) | Section labels, beat positions, energy heuristics from section type | section_change, beat, kick (inferred from downbeat + section type), energy_level (heuristic), section_anticipation | Medium confidence (heuristic fill-in, flagged) |
| **Beat Only** (BPM + beat position, no phrases) | Beat grid only | beat, kick (inferred from downbeat pattern) | Low confidence |

At the Pioneer tier, use existing heuristics from `live_analyzer.py`:
- `SECTION_ENERGY` (drop=0.9, breakdown=0.3, etc.)
- `SECTION_TREND` (build=rising, drop=peak, etc.)
- Tag all heuristic-derived values with `confidence < 0.5` so Layer 3 can route differently.

### Rule Engine Design

**Phase 1 (MVP): Hardcoded rules as Python functions, one per cue category.**

```python
# generators/section_cues.py
def generate(cursor: TrackCursor, config: CueConfig) -> list[CueEvent]:
    # If section changed since last tick → section_change cue
    # If within N beats of next section → section_anticipation cue
    # Every bar → section_progress cue with energy/trend context
```

**Phase 2: Declarative YAML rules with condition matching.**

```yaml
rules:
  - name: "drop_impact"
    when:
      event_type: section_change
      payload.to_label: drop
      context.energy_exertion: { min: 1.3 }
    then:
      emit: impact
      intensity: 1.0
      priority: 10
```

**Phase 3: Python plugin escape hatch for complex custom logic.**

```python
# user_rules/my_custom_rule.py
class DoubleDropDetector(CuePlugin):
    """Detect when a track has two drops and make the second one bigger."""
    def evaluate(self, cursor, history) -> list[CueEvent]:
        ...
```

### Event Significance Model

All events enter Layer 2. Layer 2 computes **significance** for each:

```
significance = base_weight[event_type]
             × section_weight[section_label]
             × exertion_factor
             × confidence
```

Where:
- `base_weight` — per-type priority (kick=0.8, snare=0.6, hihat=0.2, riser=0.9, etc.)
- `section_weight` — section context boost (kick in drop=1.5, kick in breakdown=0.7, etc.)
- `exertion_factor` — relative energy (sparse context amplifies, dense context dampens)
- `confidence` — data tier quality

Events below a configurable threshold become metadata (attached to the next qualifying cue)
rather than independent CueEvents. They're never discarded — they're just demoted to context.

### Rate Limiting Per Cue Type

```yaml
rate_limits:
  kick: 100ms       # max ~10/sec (more than enough for 4-on-floor)
  snare: 200ms      # max ~5/sec
  hihat: 500ms      # max ~2/sec (only significant ones pass)
  section_change: 0  # never rate-limited
  energy_level: 1000ms  # once per second max
```

Within each rate window, keep the highest-significance event. This is inspired by
music-reactive-lighting's Strobe Debouncing (120ms cooldown).

### Color Block Inertia (from music-reactive-lighting)

During high-arousal/high-energy moments (>0.7), Layer 2 should emit a `palette_lock` flag on
cues, signaling Layer 3 to increase palette inertia. This prevents rapid palette flickering in
dense sections where many conflicting frequency cues fire simultaneously.

---

## MVP Scope (Milestone 3 Revised)

### Cue Types for MVP

1. **section_change** — fires on section transitions. Payload: `{from_label, to_label, is_impact, energy_delta}`
2. **section_anticipation** — fires N beats before section change. Payload: `{upcoming_label, beats_until}`
3. **kick** — fires on detected kick events (or inferred from downbeat in Pioneer tier). Payload: `{velocity, exertion}`
4. **snare** (if trivial) — fires on snare/clap events. Payload: `{velocity, exertion}`
5. **energy_level** — continuous, fires every bar. Payload: `{energy, exertion, trend}`

### Context Dimensions for MVP

- `section_label`, `section_progress` — from cursor
- `track_energy` (absolute) — from analysis or section heuristic
- `energy_exertion` (relative) — computed by L2
- `energy_trend` — from analysis or section heuristic
- `data_tier` — "full", "pioneer_live", or "beat_only"
- `confidence` — per-field quality indicator

### MIR Mood Dimensions (placeholder for MVP)

Reserve `valence` and `arousal` fields on MusicalContext. For MVP, derive from section
heuristics:

| Section | Arousal (approx) | Valence (approx) |
|---------|-----------------|-------------------|
| intro   | 0.3 | 0.5 |
| verse   | 0.5 | 0.5 |
| build   | 0.7 | 0.6 |
| drop    | 0.9 | 0.7 |
| breakdown | 0.2 | 0.4 |
| chorus  | 0.8 | 0.8 |
| bridge  | 0.4 | 0.5 |
| outro   | 0.2 | 0.4 |

These are rough. They become real when MIR feature extraction (M8+) provides actual
valence/arousal estimates from audio analysis.

---

## What NOT to Build (Anti-Patterns from Research)

1. **Don't hard-code aesthetic decisions in Layer 2.** "Drop = strobe" is a Layer 3 routing
   decision, not a Layer 2 cue generation decision. Layer 2 says "this is a high-energy
   section transition with high exertion." Layer 3 decides that means strobe.

2. **Don't pre-filter events before Layer 2.** All events enter L2. Significance scoring
   determines what becomes a cue vs. what becomes metadata. This preserves maximum flexibility
   for user remapping.

3. **Don't model lighting concepts in Layer 2.** No colors, no brightness, no DMX. Layer 2
   speaks music vocabulary only.

4. **Don't require ML for MVP.** The rule-based approach (hardcoded heuristics → declarative
   YAML → Python plugins) matches the "start simple, grow into goals" philosophy. ML-based
   cue generation can be a Phase 3+ experiment.

5. **Don't build the full 17-cue taxonomy at once.** Ship 5 cue types, validate the pipeline,
   then expand. Every new cue type needs a generator, config, tests, and L3 routing support.

---

## Key External References

- [music-reactive-lighting](https://github.com/CanYuzbey/music-reactive-lighting) — Russell's Circumplex, exertion scores, strobe debouncing, palette inertia
- [SoundSwitch](https://www.soundswitch.com/) — Per-track lighting scripts, phrase detection, Autoloop fallbacks
- [MaestroDMX](https://maestrodmx.com/) — Real-time autonomous lighting, energy/mood palette system
- [Rekordbox Lighting Mode Guide](https://cdn.rekordbox.com/files/20241203210634/rekordbox7.0.5_Phrase_Edit_operation_guide_EN.pdf) — Pioneer phrase vocabulary, mood categories
- [Mark LaPierre: Lighting Music Basics](https://www.mlp-lighting.com/programming/lighting-music-basics-4-the-cueing/) — "Visual Home", tension/release, cue-per-section, anticipatory timing
- [Ableton Dramatic Arc](https://makingmusic.ableton.com/dramatic-arc) — Exposition → climax → dénouement applied to music
- [EDM Tension & Energy Guide](https://www.edmprod.com/tension/) — Production-side view of tension/release in EDM
- [Creating Tension in EDM](https://www.pointblankmusicschool.com/blog/creating-tension-and-release-in-electronic-dance-music/) — Riser/filter/rhythm techniques for tension building
- [Drools CEP](https://docs.drools.org/6.5.0.Final/drools-docs/html/ch09.html) — Complex Event Processing temporal reasoning model
- [Vello Light: Programming Cues](https://www.vellolight.com/article/program-stage-light-scenes-cues/) — Scene/cue/stack vocabulary
- [DMX Cue Programming](https://oboe.com/learn/dmx512-lighting-control-essentials-1pko1du/programming-lighting-cues-and-scenes-4) — DMX cue programming fundamentals

---

## Additional Findings (from extended research)

### EDMFormer (2025) — EDM-Specific Structure Analysis

A transformer model with an EDM-specific taxonomy and dataset (EDM-98, 98 annotated tracks)
achieves **73.5% improvement in per-frame accuracy** over general-purpose SongFormer for EDM.
Key insight: pop-centric taxonomies (verse/chorus) fail for EDM. Sections are defined by
energy/rhythm/timbre, not lyrics/harmony.

- Source: [EDMFormer paper](https://arxiv.org/abs/2603.08759)
- Source: [edm-segmentation GitHub](https://github.com/mixerzeyu/edm-segmentation)

**Implication:** SCUE should support both traditional section labels (from allin1) AND
EDM-specific labels (from Pioneer phrases or EDMFormer). The Layer 2 rule engine should handle
both vocabularies transparently.

### Captivate (TypeScript/Electron — most architecturally interesting open-source)

A sophisticated live visual + DMX system that uses **synth-inspired design**: LFOs, MIDI pads,
randomizers modulate lighting parameters. Hundreds of DMX channels abstracted to a few
intuitive parameters. Integrates via Ableton Link for BPM/phase sync.

- Source: [Captivate GitHub](https://github.com/spensbot/captivate)

**Implication:** The "synth modulation" metaphor (LFOs, envelopes, modulators) is a compelling
way to think about how Layer 3 effects are parameterized. Layer 2 feeds the modulators; Layer 3
is the synth.

### Oculizer (Python — combines metadata + live audio)

Real-time music-reactive DMX lighting that combines Spotify metadata with live audio analysis.
Mel-scaled FFT mapped to DMX via configurable JSON scene rules. Tracks music intensity
(calm/normal/intense) to switch lighting programs.

- Source: [Oculizer GitHub](https://github.com/LandryBulls/Oculizer)

**Implication:** The three-tier intensity model (calm/normal/intense) as a program switcher is
a simple but effective approach. SCUE's section labels provide much richer context, but the
"intensity tier → program" pattern is a good UX starting point for non-technical users.

### Solberg (2014) — "Waiting for the Bass to Drop"

Identifies **5 specific production techniques** that create tension/anticipation in EDM buildups:
1. Uplifters (risers)
2. Drum roll effect (increasing density)
3. Large frequency changes (high-pass filter sweeps)
4. Bass removal + reintroduction
5. Contrasting breakdown (sparse → dense)

Framework: auditive expectancy based on gravity (what goes up must come down).

- Source: [Dancecult paper](https://dj.dancecult.net/index.php/dancecult/article/view/451)

**Implication:** These 5 techniques map directly to detectable events in SCUE's Layer 1:
risers, percussion density changes, spectral centroid shifts, bass energy drops, and
section-level sparsity changes. Layer 2 could synthesize these into a composite "tension"
score — exactly the `tension` field proposed in the extended MusicalContext.

### Semantic Cue Priority — An Unsolved Gap

From the research: **cue priority at the semantic level is unsolved in the literature.**
Existing systems handle priority at the DMX output level (HTP/LTP merging) or via manual
operator judgment. No automated system has a published approach to "this drop is more important
than that key change."

**This is a genuine gap SCUE could fill.** The significance scoring model proposed in this
document (base_weight × section_weight × exertion × confidence) would be novel.

### HTP/LTP Merge Model — Industry Standard for Output

The DMX industry standard for conflict resolution:
- **HTP (Highest Takes Precedence)**: for intensity/brightness channels — highest value wins
- **LTP (Latest Takes Precedence)**: for color/position — most recent change wins
- Priority integers (0-200) for override control

This belongs in Layer 3/4, not Layer 2, but informs the design: Layer 2's priority field
should be compatible with HTP/LTP semantics downstream.

### MIR-Driven Visualization — Academic Validation

A 2025 Frontiers in VR paper validates that MIR-controlled visualization receives significantly
higher ratings for aesthetic emotions and animation quality compared to randomized mapping.
**MIR-driven mapping is perceptually superior to arbitrary mapping** — the effort to detect and
use musical features is justified.

- Source: [Frontiers paper](https://www.frontiersin.org/journals/virtual-reality/articles/10.3389/frvir.2025.1552321/full)

### Emotion-to-Color Research (PNAS)

Music-color associations are **mediated by emotion** (not arbitrary):
- Faster major-mode music → saturated, lighter, yellower color choices
- Slower minor-mode music → desaturated, darker, bluer choices
- High arousal → red-orange; low arousal → blue
- Neutral → fades to white

This validates using Russell's Circumplex (valence × arousal) as the bridge between MIR
features and color palette selection.

- Source: [PNAS paper](https://www.pnas.org/doi/10.1073/pnas.1212562110)

### Skip-BART (ICLR 2026) — Rule-Based vs ML for Music→Lighting, Directly Compared

The paper "Automatic Stage Lighting Control: Is it a Rule-Driven Process or Generative Task?"
is the **most directly relevant academic work** for SCUE's Layer 2 design. Key findings:

- **Skip-BART** (a BART variant with skip connections) treats lighting control as a generative
  sequence task: audio input → hue + intensity output
- ML outperforms rule-based across all metrics, BUT shows "only a limited gap compared to real
  lighting engineers"
- Dataset: 699 samples from 35 live performances (open source)
- **Code and dataset are open source**: [GitHub](https://github.com/RS2002/Skip-BART)

**Implication for SCUE:** This validates the "rule-based core with data-driven tuning" approach.
Rules get you 80% of the way. ML can add the last 20% but requires training data SCUE doesn't
yet have. The open dataset could be useful for future experiments.

- Source: [Skip-BART paper (arXiv)](https://arxiv.org/abs/2506.01482)

### "Glow with the Flow" (Feb 2026) — Hybrid Rule+Human Approach, Validated

A hybrid system for ambient lightscapes that uses rule-based generative mappings grounded in
expert practices, producing an editable baseline. **32 participants found the autonomous output
viable as a starting point for human refinement.** This directly validates SCUE's "preset +
override" UX model.

- Source: [arXiv paper](https://arxiv.org/abs/2602.08838)

### Thayer's Energy/Tension Model — Better Than Russell for Lighting

Thayer reframed Russell's valence/arousal as **energy** and **tension** (or stress), which may
be more useful for SCUE since lighting design cares more about energy/tension than
pleasant/unpleasant. Key finding from Farbood (MIT): **65% of participants said loudness alone
does NOT correspond to perceived tension change.** Energy is multi-dimensional — RMS alone is
insufficient. Must combine spectral flux, onset density, bass energy, and centroid.

### ETC Eos Priority Model — Industry Standard for Cue Stacking

ETC Eos (the industry-standard lighting console) uses:
- **10 priority levels** per submaster/playback
- **Ownership is per-parameter, not per-channel** (intensity and color can be owned by
  different sources)
- **Background cue lists** provide fallback values when no other source controls a parameter
- **Assert** forces a cue to actively output all stored values (overrides tracking)
- **Stomp** — when a higher-priority playback takes over, the lower-priority one is "stomped"
- **Tracking** — parameters that don't change continue at their previous value

This maps directly to SCUE's Layer 3 blending system. Layer 2's priority field should be
designed with this model in mind.

- Source: [ETC Control Philosophy whitepaper](https://www.etcconnect.com/workarea/DownloadAsset.aspx?id=10737461850)

### Ableton Link — Interop Opportunity

SCUE's bridge already implements most of what Beat Link Trigger does. Exposing an Ableton Link
endpoint would allow external visual tools (Resolume, TouchDesigner, VDMX) to sync to SCUE's
timing. This is a low-effort, high-value interop feature for later milestones.

- Source: [Ableton Link GitHub](https://github.com/Ableton/link)

---

## Open Questions for Future Research

1. **Transition blending** — When two decks are active during a DJ mix, how should cues from
   both tracks interact? The current spec says weight-based blending, but this needs real-world
   testing.

2. **Set-level narrative** — Should there be a "macro" layer above per-track cues that tracks
   the energy arc of an entire DJ set? This could prevent visual fatigue (same high energy for
   90 minutes) and create intentional ebbs.

3. **User feedback loop** — music-reactive-lighting's reinforcement learning from human
   sentiment labels is interesting. Could SCUE have a "thumbs up/down" during a set that
   adjusts cue weights over time?

4. **Fakeout handling** — Fakeout drops (build → silence → real drop) are already detected by
   Layer 1. How should Layer 2 handle them? Suppress the fake section_change? Emit a special
   "fakeout" cue that Layer 3 can use for a dramatic blackout?

5. **Cross-track pattern recognition** — If the same track structure appears in multiple songs
   (common in EDM), can cue rules be learned from one track and applied to similar ones?
