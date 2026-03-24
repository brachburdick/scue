# Proposal: Song Arrangement Engine

**Status:** PROPOSAL (not a spec — for operator review and refinement)
**Date:** 2026-03-24
**Task:** arrangement-engine-proposal
**Author:** Claude (research + design session with Brach)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Motivation & Problem Statement](#2-motivation--problem-statement)
3. [The Event Taxonomy — Evaluation & Proposal](#3-the-event-taxonomy--evaluation--proposal)
4. [Data Model](#4-data-model)
5. [Analysis Pipeline](#5-analysis-pipeline)
6. [Frontend Visualization](#6-frontend-visualization)
7. [Integration with Existing System](#7-integration-with-existing-system)
8. [Naming](#8-naming)
9. [Incremental Build Path](#9-incremental-build-path)
10. [Open Questions](#10-open-questions)
11. [Risk Assessment](#11-risk-assessment)

---

## 1. Executive Summary

The Song Arrangement Engine is a system that takes an audio track and produces a
structured representation of its compositional formula: what instruments are playing,
what patterns they form, how those patterns repeat and vary across sections, and how
the arrangement builds and releases energy.

It subsumes and extends the current M7 event detection and section analysis into a
unified model. The output serves two equal consumers: (1) Brach reviewing and
correcting arrangement data via a new Arrangement Page, and (2) Layer 2's cue engine
consuming rich musical context for automated lighting.

Key design decisions from operator input:
- **Three-tier compute:** Quick (<30s, no stems), Standard (1-2 min, stems + quick-on-stems),
  Deep (2-5 min, stems + ML models). Standard is the sweet spot.
- **Stem storage:** Save separated stem audio by default, configurable to derive-and-discard
- **M7 relationship:** M7 tools/methods are ingredients, not a separate system. The
  arrangement engine absorbs them into a unified pipeline the operator will tune.
- **Frontend:** A new Arrangement Page that absorbs the best of Analysis Viewer and
  Annotation Page, avoiding a retrofit homunculus.
- **Pattern naming:** Auto-generated descriptive names with human override.
- **Name:** Strata.

---

## 2. Motivation & Problem Statement

### What exists today

SCUE currently produces two tiers of analysis:

1. **Tier 1 — Sections:** intro, verse, build, drop, breakdown, fakeout, outro.
   Timestamps, bar counts, confidence. Produced by allin1-mlx + ruptures + EDM flow model.

2. **Tier 2 — Events:** Individual kicks, snares, claps, hi-hat patterns, risers,
   fallers, stabs. Produced by M7 heuristic detectors operating on the full stereo mix.

### What's missing

Neither tier captures **compositional structure** — the "formula" of how a track is built:

- **What instruments are playing where?** The bass drops out in the breakdown. Vocals
  appear only in verses. The arp starts in the build and continues through the drop.
  None of this is captured.

- **What patterns exist?** A "four-on-the-floor kick + offbeat clap" pattern repeats
  through the entire track except builds and breakdowns. An arp pattern repeats every
  2 bars in the drop. These repeat structures are invisible.

- **How do patterns vary?** The drum pattern in drop 2 has an extra hi-hat roll that
  wasn't in drop 1. The build adds percussion layers progressively. These variations
  carry the compositional intent.

- **What's the energy narrative?** The track builds energy through layering (adding
  instruments), density (faster patterns), and spectral range (wider frequency content).
  The arrangement engine should make this legible.

### Why this matters for SCUE

Layer 2 (cue generation) currently receives a flat list of upcoming events and a
section label. It has no concept of:
- "This is the moment the bass re-enters after an 8-bar breakdown"
- "This drum fill is a transition between pattern A and pattern B"
- "The arrangement is building — 3 new layers have entered in the last 4 bars"

These are the compositional moments that drive memorable lighting. Section labels
alone are too coarse; individual events are too fine. The arrangement formula
occupies the space between.

---

## 3. The Event Taxonomy — Evaluation & Proposal

### Current 4-category taxonomy (from annotation-followup.md)

1. **Song sections** — intro, verse, drop, etc.
2. **Continuous/sustained events** — risers, fallers, pads (have duration)
3. **One-off point events** — individual kicks, snares, stabs
4. **Groups of point events** — patterns that repeat

### Evaluation

This taxonomy is directionally correct but has gaps and ambiguities:

**Gap 1: Stem/layer activity.** "The bass is playing" isn't an event — it's a
continuous state of a stem. It doesn't fit cleanly as a "continuous event" (that
category was defined for risers/fallers which have clear start/end and a directional
character). Stem activity is more like a boolean state per layer that changes at
arrangement transitions.

**Gap 2: Arrangement transitions.** "The arp enters at bar 33" is neither a point
event nor a pattern — it's a structural moment where the arrangement changes. These
transitions are the highest-value signals for lighting and they're not captured.

**Gap 3: Energy/texture description.** The taxonomy describes *what happens* but not
*what it means compositionally*. A drum fill before a drop is different from a drum
fill in a verse — the arrangement context gives it meaning.

**Ambiguity: Where do fills go?** A drum fill is a "group of point events" but it's
also a one-off occurrence (it happens once at a specific place). It's really a
*deviation from a pattern*, which is a different concept from a *repeating pattern*.

### Proposed 5-concept model

Rather than a flat list of event categories, the arrangement engine should model
5 interconnected concepts:

```
1. SECTIONS      — temporal regions with labels (existing)
2. LAYERS        — stem-based channels (drums, bass, vocals, synths, fx)
3. EVENTS        — atomic occurrences within a layer (kicks, notes, onsets)
4. PATTERNS      — named repeating groups of events within a layer
5. TRANSITIONS   — moments where the arrangement changes
                   (layer enters/exits, pattern changes, fills)
```

How they compose:

```
Track
 └─ Sections[]          "drop 1 (bars 17-32)"
     └─ each section has...
         ├─ active Layers[]      "drums: active, bass: active, vocals: absent"
         ├─ active Patterns[]    "kick-4otf, hihat-16ths, bass-ostinato-A"
         └─ Transitions[]        "bass enters at bar 17, fill at bar 32"

Layer
 └─ activity timeline    "present from bar 5 to bar 48, absent bars 49-56, returns bar 57"
 └─ Events[]             atomic hits/notes within this layer
 └─ Patterns[]           repeating event groups within this layer

Pattern
 └─ template: Events[]   "kick on 1, clap on 2+4, hihat on every 8th"
 └─ instances[]          "bars 17-24 (exact), bars 25-32 (variation: extra hat roll)"
 └─ deviations[]         fills, drops, one-off variations

Transition
 └─ type                 "layer_enter" | "layer_exit" | "pattern_change" |
                         "fill" | "energy_shift" | "breakdown_start"
 └─ context              which layer, which patterns, energy direction
```

**OPEN QUESTION for operator:** This 5-concept model is the proposal's strongest
opinion. Does the section→layer→pattern→transition hierarchy feel right? Or should
layers and patterns be more orthogonal (not nested under sections)?

---

## 4. Data Model

### 4.1 Python Dataclasses (Layer 1)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Stems / Layers
# ---------------------------------------------------------------------------

class StemType(str, Enum):
    """Coarse stem categories from source separation."""
    DRUMS = "drums"
    BASS = "bass"
    VOCALS = "vocals"
    OTHER = "other"          # catch-all for synths, keys, guitars, fx


class LayerRole(str, Enum):
    """Semantic role a layer plays in the arrangement."""
    RHYTHM = "rhythm"        # drums, percussion
    BASSLINE = "bassline"    # bass
    LEAD = "lead"            # lead vocal, lead synth
    PAD = "pad"              # sustained harmonic texture
    ARPEGGIO = "arpeggio"    # repeating melodic figure
    FX = "fx"                # risers, fallers, impacts, sweeps
    VOCAL = "vocal"          # any vocal content
    UNKNOWN = "unknown"


@dataclass
class StemAnalysis:
    """Analysis results for a single separated stem."""
    stem_type: StemType
    audio_path: str | None = None       # path to saved stem file (None if discarded)
    layer_role: LayerRole = LayerRole.UNKNOWN
    activity: list[ActivitySpan] = field(default_factory=list)
    events: list[AtomicEvent] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    energy_curve: list[float] = field(default_factory=list)  # per-bar energy


# ---------------------------------------------------------------------------
# Activity (layer presence/absence)
# ---------------------------------------------------------------------------

@dataclass
class ActivitySpan:
    """A contiguous region where a layer is active (audible)."""
    start: float             # seconds
    end: float               # seconds
    bar_start: int
    bar_end: int
    energy: float            # average energy in this span (0.0-1.0)
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Atomic Events
# ---------------------------------------------------------------------------

@dataclass
class AtomicEvent:
    """A single musical occurrence within a layer.

    Extends the existing MusicalEvent with stem attribution and richer metadata.
    Backward-compatible: can be converted to/from MusicalEvent.
    """
    type: str                           # "kick" | "snare" | "clap" | "note" | etc.
    timestamp: float                    # seconds
    duration: float | None = None       # None for instantaneous
    intensity: float = 0.5              # 0.0-1.0
    stem: StemType | None = None        # which stem this came from
    pitch: str | None = None            # e.g. "C4", None for unpitched
    beat_position: int | None = None    # 0-15 (16th-note slot in bar)
    bar_index: int | None = None        # which bar (0-based)
    confidence: float = 0.5
    source: str = "detector"            # "detector" | "adt" | "amt" | "manual"
    payload: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

class PatternType(str, Enum):
    DRUM_GROOVE = "drum_groove"         # repeating drum pattern
    ARPEGGIO = "arpeggio"               # repeating melodic figure
    BASSLINE = "bassline"               # repeating bass figure
    CHORD_PROGRESSION = "chord_prog"    # repeating harmonic sequence
    VOCAL_PHRASE = "vocal_phrase"        # repeating vocal motif
    PERCUSSION_FILL = "perc_fill"       # deviation from groove (NOT repeating)
    CUSTOM = "custom"


@dataclass
class PatternTemplate:
    """The archetypal version of a pattern — what it looks like in its 'normal' form.

    For a drum groove: the kick/snare/hat layout of one cycle.
    For an arp: the note sequence of one cycle.
    """
    events: list[AtomicEvent]           # events relative to pattern start (t=0)
    duration_bars: int                  # how many bars one cycle takes
    duration_seconds: float             # at the track's BPM
    signature: str = ""                 # hash or compact representation for comparison


@dataclass
class PatternInstance:
    """One occurrence of a pattern in the track."""
    bar_start: int
    bar_end: int                        # exclusive
    start: float                        # seconds
    end: float
    variation: str = "exact"            # "exact" | "minor" | "major" | "fill"
    variation_description: str = ""     # human-readable: "extra hat roll bars 3-4"
    confidence: float = 0.5


@dataclass
class Pattern:
    """A named, repeating musical figure.

    The template is the 'canonical' version. Instances are where it appears.
    Patterns can have variations — instances that mostly match but differ in
    specific ways (fills, embellishments, drops).
    """
    id: str                             # unique within the track, e.g. "drum-groove-A"
    name: str                           # auto-generated, human-overridable
    pattern_type: PatternType
    stem: StemType | None = None
    template: PatternTemplate = field(default_factory=PatternTemplate)
    instances: list[PatternInstance] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # e.g. ["four-on-the-floor", "offbeat-clap"]


# ---------------------------------------------------------------------------
# Transitions (arrangement changes)
# ---------------------------------------------------------------------------

class TransitionType(str, Enum):
    LAYER_ENTER = "layer_enter"         # a stem/layer becomes active
    LAYER_EXIT = "layer_exit"           # a stem/layer drops out
    PATTERN_CHANGE = "pattern_change"   # groove A → groove B
    FILL = "fill"                       # brief deviation (drum fill, pickup)
    ENERGY_SHIFT = "energy_shift"       # notable energy level change
    BREAKDOWN_START = "breakdown"       # multiple layers exit simultaneously
    DROP_IMPACT = "drop_impact"         # multiple layers enter simultaneously


@dataclass
class ArrangementTransition:
    """A moment where the arrangement changes."""
    type: TransitionType
    timestamp: float                    # seconds
    bar_index: int
    section_label: str                  # which section this occurs in
    layers_affected: list[StemType] = field(default_factory=list)
    patterns_affected: list[str] = field(default_factory=list)  # pattern IDs
    energy_delta: float = 0.0           # -1.0 to +1.0
    description: str = ""               # auto-generated: "bass enters, kick pattern changes"
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# The Arrangement Formula — the top-level output
# ---------------------------------------------------------------------------

@dataclass
class SectionArrangement:
    """What's happening in a specific section, arrangement-wise."""
    section_label: str
    section_start: float
    section_end: float
    active_layers: list[StemType]       # which stems are audible
    active_patterns: list[str]          # pattern IDs active in this section
    transitions: list[ArrangementTransition]  # transitions within/at boundaries
    energy_level: float                 # 0.0-1.0, average energy
    energy_trend: str                   # "rising" | "falling" | "stable" | "peak" | "valley"
    layer_count: int = 0                # number of active layers (for quick density read)


@dataclass
class ArrangementFormula:
    """Complete arrangement analysis for a single track.

    This is the top-level output of the arrangement engine. It captures
    the compositional logic: what layers exist, what patterns they contain,
    where those patterns play, and how the arrangement evolves.
    """
    fingerprint: str                    # same as TrackAnalysis.fingerprint
    version: int = 1

    # Stem-level analysis
    stems: list[StemAnalysis] = field(default_factory=list)

    # All patterns found in the track (across all stems)
    patterns: list[Pattern] = field(default_factory=list)

    # Per-section arrangement summary
    sections: list[SectionArrangement] = field(default_factory=list)

    # All transitions (sorted by timestamp)
    transitions: list[ArrangementTransition] = field(default_factory=list)

    # Track-level summary
    total_layers: int = 0
    total_patterns: int = 0
    arrangement_complexity: float = 0.0  # derived metric: pattern variety * transition density
    energy_narrative: str = ""           # auto-generated: "builds to drop at bar 32, breaks at 48"

    # Pipeline metadata
    pipeline_tier: str = "quick"        # "quick" | "standard" | "deep"
    stem_separation_model: str = ""     # e.g. "htdemucs" or "none"
    compute_time_seconds: float = 0.0
    created_at: float = 0.0
```

### 4.2 TypeScript Types (Frontend)

```typescript
// frontend/src/types/arrangement.ts

export type StemType = "drums" | "bass" | "vocals" | "other";
export type LayerRole = "rhythm" | "bassline" | "lead" | "pad" | "arpeggio" | "fx" | "vocal" | "unknown";
export type PatternType = "drum_groove" | "arpeggio" | "bassline" | "chord_prog" | "vocal_phrase" | "perc_fill" | "custom";
export type TransitionType = "layer_enter" | "layer_exit" | "pattern_change" | "fill" | "energy_shift" | "breakdown" | "drop_impact";

export interface ActivitySpan {
  start: number;
  end: number;
  bar_start: number;
  bar_end: number;
  energy: number;
  confidence: number;
}

export interface AtomicEvent {
  type: string;
  timestamp: number;
  duration: number | null;
  intensity: number;
  stem: StemType | null;
  pitch: string | null;
  beat_position: number | null;
  bar_index: number | null;
  confidence: number;
  source: string;
  payload: Record<string, unknown>;
}

export interface PatternTemplate {
  events: AtomicEvent[];
  duration_bars: number;
  duration_seconds: number;
  signature: string;
}

export interface PatternInstance {
  bar_start: number;
  bar_end: number;
  start: number;
  end: number;
  variation: "exact" | "minor" | "major" | "fill";
  variation_description: string;
  confidence: number;
}

export interface Pattern {
  id: string;
  name: string;
  pattern_type: PatternType;
  stem: StemType | null;
  template: PatternTemplate;
  instances: PatternInstance[];
  tags: string[];
}

export interface ArrangementTransition {
  type: TransitionType;
  timestamp: number;
  bar_index: number;
  section_label: string;
  layers_affected: StemType[];
  patterns_affected: string[];
  energy_delta: number;
  description: string;
  confidence: number;
}

export interface SectionArrangement {
  section_label: string;
  section_start: number;
  section_end: number;
  active_layers: StemType[];
  active_patterns: string[];
  transitions: ArrangementTransition[];
  energy_level: number;
  energy_trend: "rising" | "falling" | "stable" | "peak" | "valley";
  layer_count: number;
}

export interface ArrangementFormula {
  fingerprint: string;
  version: number;
  stems: StemAnalysis[];
  patterns: Pattern[];
  sections: SectionArrangement[];
  transitions: ArrangementTransition[];
  total_layers: number;
  total_patterns: number;
  arrangement_complexity: number;
  energy_narrative: string;
  pipeline_tier: "quick" | "standard" | "deep";
  stem_separation_model: string;
  compute_time_seconds: number;
  created_at: number;
}

export interface StemAnalysis {
  stem_type: StemType;
  audio_path: string | null;
  layer_role: LayerRole;
  activity: ActivitySpan[];
  events: AtomicEvent[];
  patterns: Pattern[];
  energy_curve: number[];
}
```

### 4.3 Relationship to Existing Models

| Existing Model | Arrangement Engine Equivalent | Migration Path |
|---|---|---|
| `Section` | `SectionArrangement` (extends with layers, patterns, energy) | Additive — Section still exists, SectionArrangement wraps it |
| `MusicalEvent` | `AtomicEvent` (adds stem, pitch, bar_index, source) | AtomicEvent can convert to/from MusicalEvent for backward compat |
| `DrumPattern` | `Pattern` with `PatternType.DRUM_GROOVE` | DrumPattern's slot arrays become the `PatternTemplate.events` |
| `TrackAnalysis` | Gains an `arrangement: ArrangementFormula` field | Additive — existing fields untouched |
| `TrackCursor.upcoming_events` | Extended with arrangement context | `upcoming_events` stays as `list[MusicalEvent]`; new `arrangement_context` field added |

**Key compatibility principle:** Each tier's ArrangementFormula is stored as a
separate JSON file — `strata/{fingerprint}.quick.json`,
`strata/{fingerprint}.standard.json`, etc. — alongside the existing analysis JSON.
Standard tier does NOT overwrite quick tier data. The `TrackAnalysis` dataclass
gains an optional `strata: dict[str, ArrangementFormula] | None` field (keyed by
tier name) that's loaded on demand, not embedded in the main analysis file.

### 4.4 Ground Truth Annotation

The existing ground truth system (`scue/api/ground_truth.py`) works with flat event
lists. The arrangement engine needs richer annotation:

- **Pattern annotation:** Define a pattern template, mark where it repeats, flag variations
- **Layer activity annotation:** Mark where stems enter/exit
- **Transition annotation:** Label arrangement change points

This extends the annotation JSON schema:

```json
{
  "fingerprint": "abc123",
  "events": [...],              // existing: flat event list
  "patterns": [...],            // NEW: Pattern objects
  "layer_activity": {           // NEW: per-stem activity spans
    "drums": [{"start": 0.0, "end": 180.0}, ...],
    "bass": [{"start": 15.0, "end": 160.0}, ...]
  },
  "transitions": [...],        // NEW: ArrangementTransition objects
  "metadata": {
    "annotator": "brach",
    "pipeline_tier_used": "deep"
  }
}
```

---

## 5. Analysis Pipeline

### 5.0 On Accuracy vs. Over-Engineering

The operator's concern: "I'm worried about being able to produce a result that is
good enough whatsoever, rather than over-engineering and wasting resources."

**Critique of that worry — it's partly right and partly wrong:**

The worry is **right** in that the deep tier (ADT models, AMT, few-shot heads) is
speculative until we prove the simpler stuff works. Building a YourMT3+-powered
note-level transcription pipeline before we know if basic pattern repetition
detection is useful would be classic over-engineering.

The worry is **wrong** in one important respect: stem separation is not the
speculative part. Stem separation is the single highest-leverage step because it
*reframes the problem*. Running the existing M7 heuristic detectors on a clean
drum stem is categorically easier than running them on a full mix. The research is
unambiguous on this. The "standard" tier (stems + existing tools) is not over-
engineering — it's using the right decomposition.

**The three-tier design directly addresses this tension:**
- **Quick:** Prove the data model and UI work. Zero new ML. Ship fast.
- **Standard:** Add stem separation and re-run existing tools per stem. This is
  the expected sweet spot — moderate compute, significant accuracy gain.
- **Deep:** Add dedicated ML models per stem. Only pursue if standard tier hits a
  ceiling.

The operator can always dial back from deep → standard once accuracy is characterized.
The tiers share the same output schema, so the frontend and Layer 2 don't care which
tier produced the data.

### 5.1 Pipeline Overview

```
                     ┌─────────────────────────────────────┐
                     │ EXISTING PIPELINE (unchanged)        │
                     │ Steps 1-8: load, features, beats,    │
                     │ sections, scoring, waveform           │
                     └──────────────────┬──────────────────┘
                                        │
              ┌──────────────────────────┴──────────────────────────┐
              │                                                      │
    QUICK (<30s)              STANDARD (1-2 min)        DEEP (2-5 min)
    No new deps               Stems + existing tools    Stems + ML models
              │                         │                        │
   ┌──────────┴──────┐     ┌───────────┴──────────┐   ┌────────┴────────┐
   │ A. M7 detectors │     │ F. Stem separation    │   │ F. Stem sep     │
   │ B. Energy/act   │     │    (HT Demucs)        │   │ G. ADT on drums │
   │ C. Patterns     │     │                        │   │    AMT on other │
   │ D. Transitions  │     │ G. Per-stem QUICK      │   │    crepe on bass│
   │ E. Assembly     │     │    Run A-D on each     │   │ H-K. same as    │
   └─────────────────┘     │    separated stem      │   │    standard but  │
                           │    (M7 heuristics on   │   │    with ML event │
                           │    drum stem, energy   │   │    detection     │
                           │    analysis on bass    │   └─────────────────┘
                           │    stem, etc.)         │
                           │                        │
                           │ H. Layer activity      │
                           │    (per-stem RMS)      │
                           │ I. Pattern merge       │
                           │    (cross-stem)        │
                           │ J. Transitions         │
                           │    (stem-aware)        │
                           │ K. Assembly            │
                           └────────────────────────┘
```

### 5.2 Quick Tier Details (< 30 seconds)

The quick tier uses **no new dependencies** — only existing M7 infrastructure +
additional analysis of features already computed. It produces a coarser but still
useful arrangement formula.

**Stage A: Existing M7 detectors**
- Run percussion heuristic/RF, riser, faller, stab detectors (already implemented)
- Takes ~1-2s (already measured)

**Stage B: Energy/activity analysis**
- Compute per-band (low/mid/high) RMS envelopes at bar resolution
- Compute onset density per bar (from existing onset_strength)
- Compute spectral flux per bar
- Produces "pseudo-layer activity" by thresholding band energy:
  - Low band > threshold → "bass-like activity"
  - Mid band > threshold → "mid-range activity"
  - High band > threshold → "hi-freq activity"
- ~500ms additional compute

**Stage C: Pattern discovery**
- Take M7 DrumPattern objects → convert to Pattern model
- Compare consecutive bar patterns for repetition (cosine similarity on slot vectors)
- Group identical/near-identical bars into Pattern instances
- Auto-name based on content: "kick-4otf-clap-2+4" (four-on-the-floor kick, clap on 2 and 4)
- ~200ms

**Stage D: Transition detection**
- At each section boundary: compute energy delta (bar before vs bar after)
- Detect onset density jumps > threshold
- Detect band energy changes (bass disappears, high-freq enters)
- Classify transition types based on direction and magnitude
- ~100ms

**Stage E: Assembly**
- Compose all results into ArrangementFormula
- Generate energy_narrative string
- Compute arrangement_complexity
- ~50ms

**Quick tier total: ~2-3s on top of existing analysis (~4s). Total: ~6-7s per track.**

### 5.3 Standard Tier Details (1-2 minutes)

The standard tier is the expected sweet spot. It adds stem separation and then
**re-runs the quick tier's analysis on each separated stem**. This is the key
insight: we don't need new ML models to get a major accuracy boost — we just need
to give the existing tools cleaner input.

**Stage F: Stem separation**
- Model: HT Demucs (htdemucs_ft fine-tuned variant)
- Output: drums, bass, vocals, other stems as WAV files
- Save to `stems/{fingerprint}/` directory (configurable)
- ~30-60s on M-series Mac

**Stage G: Per-stem quick analysis**
This is the new tier's core idea: run the quick tier's stages A-D on each stem
independently, then merge.

- **Drums stem:** Run M7 percussion heuristic/RF on the isolated drum audio.
  The same beat-synchronous slot classification, but without bass/synth bleed
  confusing the energy bands. Expected: significantly better kick/snare/clap
  discrimination and hi-hat pattern detection.
- **Bass stem:** Run energy/activity analysis on the bass stem. Onset detection
  is now clean (no kick interference). Simple pitch tracking via `pyin` (already
  in librosa). Produces bass activity spans and bass note events.
- **Vocals stem:** RMS-based activity detection on the clean vocal stem. Onset
  density analysis for vocal chop/stutter detection. Phrase boundary estimation
  from RMS envelope valleys.
- **Other stem:** Energy/activity analysis. Onset detection for synth/arp events.
  Riser/faller detection on this stem is much cleaner (no drum transients to
  confuse the centroid slope). Stab detection with better harmonic ratio.

Each stem produces its own events, patterns, and activity spans. ~15-30s total
for per-stem analysis (4 stems, each running a subset of quick-tier stages).

**Stage H: Layer activity analysis**
- Per-stem RMS envelope → activity spans (active/inactive regions)
- Smooth with hysteresis to avoid rapid toggling
- Each stem gets an `activity: list[ActivitySpan]` timeline
- This is where "bass enters at bar 16" comes from
- ~5s

**Stage I: Pattern merge**
- Merge per-stem patterns into a unified pattern list
- Cross-reference patterns across stems (e.g., "when drum-groove-A is active,
  bass-ostinato-A is also always active" → they're part of the same arrangement block)
- ~2s

**Stage J: Transition detection (stem-aware)**
- Re-analyze transitions with per-stem activity data
- "bass enters" / "vocals drop out" / "new percussion layer added"
- Much richer than quick tier's band-energy approximation
- ~2s

**Stage K: Assembly**
- Compose all stem results into ArrangementFormula
- Generate stem-aware energy_narrative
- Update pipeline_tier to "standard"
- ~50ms

**Standard tier total: ~1-2 min per track.**

**Why this tier matters:** It gets ~80% of the deep tier's value for ~30% of the
compute. The M7 heuristics are already decent — their main weakness is operating on
a dense full mix. Stem separation removes that weakness. You don't need a fancy ADT
model to count kicks when the drum stem is clean.

### 5.4 Deep Tier Details (2-5 minutes)

The deep tier replaces the standard tier's "M7 heuristics on stems" with dedicated
ML models per stem. Only pursue this if the standard tier's accuracy hits a ceiling.

**Stages F-K are the same as standard tier, except Stage G uses ML models:**

**Stage G (deep): Per-stem ML event detection**
- **Drums:** ADT model on drum stem → atomic hit grid at tatum resolution.
  7+ drum classes (kick, snare, clap, hihat_closed, hihat_open, tom, crash, ride,
  perc_other). Velocity estimation. Fill detection as groove deviation.
- **Bass:** `crepe` or `pyin` pitch tracking (more precise than standard tier's
  simple pitch tracking). Note-level bass transcription.
- **Vocals:** Dedicated vocal melody extraction model. Phrase segmentation.
  Lyric presence detection.
- **Other:** YourMT3+ or similar AMT for note-level multi-instrument transcription.
  Arp pattern detection from note streams. Instrument activity classification.
- ~60-180s depending on model complexity

**Stage H (deep): Pattern refinement**
- ADT-derived drum patterns have 7+ classes vs 3-4 from heuristics
- AMT-derived melodic patterns have actual note sequences
- Few-shot classification for custom fill subtypes
- ~10-30s

**Deep tier total: ~2-5 min per track.**

### 5.4 Offline vs. Real-Time Split

| Stage | Offline (analysis) | Real-time (live) |
|---|---|---|
| Stem separation | Yes | No |
| Per-stem event detection | Yes | No |
| Pattern discovery | Yes | No |
| Transition detection | Yes | No |
| Energy/activity curves | Yes (precomputed) | Yes (interpolated from precomputed) |
| "Current pattern" lookup | N/A | Yes (binary search into pattern instances) |
| "Next transition" lookup | N/A | Yes (binary search into transitions) |
| Layer activity at time T | N/A | Yes (check ActivitySpans) |

The live path is pure lookup — all arrangement data is precomputed. The TrackCursor
gains new fields to surface arrangement context at the current playback position.

### 5.6 Models & Libraries Needed

| Purpose | Quick Tier | Standard Tier | Deep Tier |
|---|---|---|---|
| Stem separation | N/A | `demucs` (PyTorch, ~2GB) | Same |
| Drum transcription | M7 heuristic/RF (existing) | Same, on drum stem | ADT model (TBD) |
| Bass pitch tracking | N/A | `pyin` via librosa (existing) | `crepe` or `pyin` |
| Vocal activity | N/A | RMS + onset on vocal stem | Dedicated VAD model |
| Music transcription | N/A | N/A | **Future:** YourMT3+ |
| Pattern matching | Cosine similarity (numpy) | Same | Same + DTW |

**Compute budget:**
- Quick: 6-7s total (fits within existing analysis time budget)
- Standard: 1-2 min total (the expected default for serious analysis)
- Deep: 2-5 min total (only if standard hits a ceiling)

### 5.7 Configuration

```yaml
# config/strata.yaml

pipeline:
  default_tiers: ["quick", "standard"]  # run both by default
  save_stems: true           # save separated stem audio files
  stems_dir: "stems/"        # relative to project data dir

quick_tier:
  # Uses existing M7 detectors + additional energy analysis
  energy_bar_resolution: 1   # bars per energy sample
  pattern_similarity_threshold: 0.85  # cosine sim for "same pattern"
  transition_energy_threshold: 0.3    # min energy delta to flag
  min_pattern_repeats: 2              # min instances to call it a pattern

standard_tier:
  # Stem separation + existing tools re-run per stem
  separation_model: "htdemucs_ft"    # demucs model variant
  bass_pitch_method: "pyin"          # "pyin" | "crepe" (both in librosa)
  vocal_activity_threshold: 0.05     # RMS threshold for "vocal present"
  activity_hysteresis_bars: 2        # min bars before toggling activity

deep_tier:
  # ML models per stem (only if standard hits ceiling)
  drum_adt_model: "tbd"              # Phase research deliverable
  bass_pitch_method: "crepe"         # more precise than pyin
  amt_model: "tbd"                   # YourMT3+ or similar, future

pattern_naming:
  auto_name_patterns: true
  include_stem: true          # prefix with stem name
  include_rhythm: true        # describe rhythmic pattern
  max_name_length: 40
```

---

## 6. Frontend Visualization

### 6.1 Philosophy: The Strata Page

Per operator direction: create a new Strata Page that absorbs the best of the
Analysis Viewer and Annotation Page without retrofitting. This becomes the primary
way to interact with track analysis data.

**One page, two modes:**
- **View mode** (default): Read-only display of the full arrangement formula.
  Browse tracks, inspect patterns, review analysis quality. No edit affordances.
- **Edit mode** (toggled): Adds click-to-select, pattern editing, transition
  marking, event correction, unsaved-changes tracking, save/discard. Same layout,
  same components — edit mode adds interactive affordances on top.

The existing Analysis Viewer and Annotation Page remain as simpler, focused tools
until the Strata page's edit mode fully subsumes their functionality.

### 6.2 Tier Comparison

Both quick and standard tiers run by default (see Section 5). The Strata page
must support comparing results across tiers:

- **Tier selector** in the toolbar switches which tier's output is displayed
- The arrangement map, pattern list, transitions, and energy narrative all update
  to reflect the selected tier
- A **comparison mode** overlays differences: patterns that changed, transitions
  that were added/removed, layer activity that shifted
- Standard tier does NOT overwrite quick tier data — both are stored and
  independently accessible
- The `ActiveEventState` hook (used by `LiveEventDisplay` and live deck monitor)
  needs a tier parameter to select which tier's events to surface during playback

**Storage implication:** Each tier gets its own file:
- `strata/{fingerprint}.quick.json`
- `strata/{fingerprint}.standard.json`
- `strata/{fingerprint}.deep.json` (if deep tier is ever run)

### 6.3 Page Layout: `/strata`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Track Picker]  Title - Artist  128 BPM  Cm  6:32                          │
│ Tier: [Quick | *Standard*]  [View | Edit]  [Analyze ▾]                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ WAVEFORM (full track, zoomable/scrollable)                                  │
│ ████████████████████████████████████████████████████████████████████████████ │
│ ▼ section bands                                                             │
│ [  intro  ][  build  ][    drop 1    ][ breakdown ][  build  ][  drop 2  ] │
│                                                                             │
│ ▼ beatgrid lines (adaptive zoom — existing feature)                         │
│ | . . . | . . . | . . . | . . . | . . . | . . . | . . . | . . . |         │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ARRANGEMENT MAP (swim-lane view, vertically stacked per layer)              │
│                                                                             │
│ drums  ┃ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
│        ┃ [kick-4otf-A     ] [kick-4otf-A      ][groove-B ] [kick-4otf-A  ] │
│        ┃              ^fill                ^fill                            │
│ bass   ┃      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓          │
│        ┃      [bass-ostinato-A                                   ]          │
│ vocals ┃                                             ▓▓▓▓▓▓▓▓▓▓▓           │
│        ┃                                             [vocal-hook ]          │
│ synths ┃           ▓▓▓▓▓▓▓▓       ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓           │
│        ┃           [arp-A  ]       [pad-B              ][arp-A  ]          │
│ fx     ┃        ▓▓▓      ▓▓▓                       ▓▓▓      ▓▓▓           │
│        ┃        [riser]  [fall]                     [riser]  [fall]        │
│                                                                             │
│ ▼ transitions (marked at swim-lane boundaries)                              │
│           ↑bass   ↑drop    ↓breakdown  ↑bass    ↑drop                      │
│                                                                             │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ PATTERN DETAIL               │ ARRANGEMENT SUMMARY                          │
│                               │                                              │
│ Selected: kick-4otf-A         │ Sections: 6                                  │
│ Type: drum_groove             │ Layers: 5 (drums, bass, vocals, synths, fx)  │
│ Stem: drums                   │ Patterns: 7                                  │
│ Duration: 1 bar (4 beats)     │ Transitions: 12                              │
│ Instances: 24 (3 with fills)  │ Complexity: 0.72                             │
│                               │                                              │
│ Template:                     │ Energy narrative:                             │
│ K . . . K . . . K . . . K    │ "Intro builds with drums + bass. Build adds  │
│ . . . . S . . . . . . . S    │  riser + arp. Drop 1: full arrangement.      │
│ H . H . H . H . H . H . H   │  Breakdown strips to vocals + pad. Build 2   │
│                               │  re-enters bass + riser. Drop 2: groove B    │
│ Sections: drop1, drop2, verse │  with extra fill variation."                  │
│ Variations: 3 fills           │                                              │
│                               │ Pipeline: quick | 6.2s                       │
│ [Edit Name] [Edit Template]   │ [Run Deep Analysis]                          │
└──────────────────────────────┴──────────────────────────────────────────────┘
```

### 6.4 Key Visual Components

**ArrangementMap** (swim-lane view)
- One horizontal lane per layer/stem
- Time-aligned with waveform above (shared x-axis, shared zoom/scroll)
- Pattern instances shown as colored blocks within lanes
- Pattern names as labels on blocks
- Fills/variations marked with accent indicators
- Transitions marked as vertical lines with arrows and labels
- Layer activity shown as lane background (filled = active, empty = silent)
- Click a pattern block → select it → show details in Pattern Detail panel
- Click between patterns → show transition details

**PatternEditor** (in Pattern Detail panel)
- Visual grid showing the pattern template (like a drum machine sequencer)
- For drum patterns: rows = instruments, columns = 16th-note positions
- For melodic patterns: piano-roll-like representation
- Edit mode: modify the template, mark variations
- "Apply to sections" workflow from annotation-followup item #4

**LiveEventDisplay** integration
- The existing `useActiveEvents` hook extends to include arrangement context
- During playback: highlight current pattern in ArrangementMap
- Flash transitions as they occur
- Show "current layer state" in the summary panel

### 6.5 Modifications to Existing Pages

| Page | Change | Rationale |
|---|---|---|
| Analysis Viewer (`/analysis`) | Keep as-is for now. Eventually sunset or reduce to "quick glance" view. | Arrangement Page supersedes it for serious analysis work. |
| Annotation Page (`/annotation`) | Keep for ground truth event annotation. Add "Export to Arrangement" button. | Event-level annotation is still needed; arrangement annotation is a superset. |
| Detector Tuning (`/dev/detectors`) | Keep as-is. Useful for M7 detector development. | Dev tool, separate concern. |
| Sidebar | Add "Arrangement" link under main nav. | New primary page. |

### 6.6 Reusable Components

The Arrangement Page should reuse and extend:
- `WaveformCanvas` — shared waveform renderer (already used in 3 places)
- `drawBeatgridLines` — adaptive beatgrid overlay (already extracted)
- `useActiveEvents` — live playback state computation
- `LiveEventDisplay` — event flash indicators
- Section color map, event color map

New shared components needed:
- `ArrangementMap` — swim-lane pattern visualization
- `PatternGrid` — drum machine / piano-roll style pattern display
- `TransitionMarker` — visual indicator for arrangement transitions
- `EnergyTimeline` — per-bar energy curve overlay

---

## 7. Integration with Existing System

### 7.1 Layer 1 → Layer 2 (Cue Generation)

The `TrackCursor` contract (the Layer 1→2 interface) needs extension:

```python
@dataclass
class TrackCursor:
    # ... existing fields unchanged ...
    current_section: SectionInfo
    next_section: SectionInfo | None
    upcoming_events: list[MusicalEvent]
    current_features: TrackCursorFeatures
    beat_position: BeatPosition
    playback_state: PlaybackState

    # NEW: arrangement context
    arrangement_context: ArrangementContext | None = None


@dataclass
class ArrangementContext:
    """Real-time arrangement state at the current playback position."""
    active_layers: list[StemType]           # which stems are currently audible
    current_patterns: list[str]             # pattern IDs currently active
    next_transition: TransitionPreview | None  # upcoming arrangement change
    energy_level: float                     # 0.0-1.0
    energy_trend: str                       # "rising" | "falling" | "stable"
    layer_count: int                        # how many layers are active
    bars_since_last_transition: int         # how long since last change
    bars_until_next_transition: int | None  # how long until next change


@dataclass
class TransitionPreview:
    """Preview of an upcoming arrangement transition."""
    type: TransitionType
    timestamp: float
    time_until: float                       # seconds
    bars_until: int
    description: str                        # "bass enters in 4 bars"
    energy_delta: float
```

This gives Layer 2's cue engine access to compositional context:
- "The bass is about to enter" → trigger a lighting cue
- "We're 2 bars from a transition, energy is rising" → start building effect
- "4 layers are active, this is a peak moment" → maximize brightness/movement

### 7.2 Layer 2 → Layer 3 (Effects)

The existing `CueEvent` model already has `musical_context: MusicalContext`. This
should be extended:

```python
@dataclass
class MusicalContext:
    # ... existing fields ...
    section_label: str
    section_progress: float
    track_energy: float
    track_mood: str

    # NEW
    active_layer_count: int = 0
    energy_trend: str = "stable"
    current_patterns: list[str] = field(default_factory=list)
    transition_proximity: float | None = None  # 0.0-1.0, how close to next transition
```

### 7.3 useActiveEvents Hook Extension

The `useActiveEvents` hook gains strata awareness. Since both quick and standard
tiers coexist, the hook accepts a tier parameter to select which tier's data
to use for event lookups:

```typescript
// Extended signature
function useActiveEvents(
  currentTime: number | null,
  events: EventInput[],
  sections: Section[],
  beats: number[],
  downbeats: number[],
  options?: {
    recentWindow?: number;
    previewCount?: number;
    strataTier?: "quick" | "standard" | "deep";  // NEW: which tier's strata to use
    strata?: ArrangementFormula | null;            // NEW: pre-loaded strata data
  }
): ActiveEventState | null

// Extended return type
interface ActiveEventState {
  // ... existing fields ...
  currentTime: number;
  activeSections: Section[];
  recentEvents: FiredEvent[];
  upcomingEvents: EventPreview[];
  phrase: PhraseInfo | null;

  // NEW
  arrangement: ActiveArrangement | null;
}

interface ActiveArrangement {
  activeLayers: StemType[];
  currentPatterns: PatternPreview[];
  nextTransition: TransitionPreview | null;
  energyLevel: number;
  energyTrend: "rising" | "falling" | "stable";
  layerCount: number;
  tier: "quick" | "standard" | "deep";  // which tier produced this data
}
```

### 7.4 Changes to interfaces.md

New section needed:

```markdown
## Layer 1 Arrangement Engine -> Layer 2: ArrangementContext

ArrangementContext is an optional field on TrackCursor. If the track has
arrangement analysis, it provides compositional context. If not, it's null
and Layer 2 falls back to section-only cues.

## Backend -> Frontend: Strata REST API

| Endpoint | Method | Purpose |
|---|---|---|
| /api/tracks/{fp}/strata | GET | Get all tier results (quick, standard, deep) |
| /api/tracks/{fp}/strata/{tier} | GET | Get specific tier's arrangement formula |
| /api/tracks/{fp}/strata/{tier} | PUT | Save edited arrangement for a tier |
| /api/tracks/{fp}/strata/analyze | POST | Trigger strata analysis (body: {tiers: ["quick","standard"]}) |
| /api/tracks/{fp}/stems | GET | List available stem files |
| /api/tracks/{fp}/stems/{stem_type} | GET | Stream stem audio file |
```

### 7.5 What Needs Refactoring vs. What's Additive

| Change | Type | Scope |
|---|---|---|
| `ArrangementFormula` dataclass + serialization | Additive | New file: `scue/layer1/strata/models.py` |
| Strata analysis pipeline | Additive | New file: `scue/layer1/strata/engine.py` |
| Pattern discovery logic | Additive | New file: `scue/layer1/strata/patterns.py` |
| Transition detection | Additive | New file: `scue/layer1/strata/transitions.py` |
| Stem separation wrapper | Additive | New file: `scue/layer1/strata/stems.py` |
| `TrackCursor` + `ArrangementContext` | Extends | Modify: `scue/layer1/models.py` |
| `TrackAnalysis.arrangement` field | Extends | Modify: `scue/layer1/models.py` |
| API endpoints | Additive | New file: `scue/api/arrangement.py` |
| Frontend Arrangement Page | Additive | New files in `frontend/src/pages/`, `components/arrangement/` |
| Frontend types | Additive | New file: `frontend/src/types/arrangement.ts` |
| `useActiveEvents` extension | Extends | Modify: `frontend/src/hooks/useActiveEvents.ts` |
| M7 detectors | Unchanged | Used as ingredients in quick tier |
| Existing Section analysis | Unchanged | Arrangement wraps sections, doesn't replace |
| Waveform rendering | Unchanged | Reused as-is |

**No existing code is deleted.** Everything is additive or extends with backward-compatible optional fields.

---

## 8. Naming

**Name: Strata.**

*Layers of sound, stratified.*

- "Strata analysis" — the process
- "Track strata" — the output
- `StrataEngine` — the class
- `scue/layer1/strata/` — the package
- `config/strata.yaml` — the configuration
- `/strata` — the frontend page route
- Evokes geological layers, which maps well to stems/layers
- Short, memorable, easy to type
- Natural extension: "stratum" for a single layer

---

## 9. Incremental Build Path

### Phase 0: Foundation (1-2 sessions)
**What:** Data model + per-tier storage + API skeleton + minimal frontend page
- Define and implement `ArrangementFormula` and related dataclasses
- Per-tier file storage: `strata/{fp}.quick.json`, `strata/{fp}.standard.json`
- Implement serialization/deserialization with tier key
- Create `scue/layer1/strata/` package structure
- Create `/api/tracks/{fp}/strata` endpoints (GET all tiers, GET by tier, POST analyze)
- Create minimal `/strata` page with track picker + tier selector + empty state
- **Deliverable:** The data shape and per-tier storage exist end-to-end

### Phase 1: Quick Tier — Pattern Discovery (2-3 sessions)
**What:** Turn existing M7 output into patterns + transitions
- Stage A: Wire existing M7 detectors as Strata engine input
- Stage B: Energy/activity analysis from existing features
- Stage C: Pattern discovery from DrumPattern data (repetition detection, auto-naming)
- Stage D: Transition detection from energy deltas at section boundaries
- Stage E: Assembly into ArrangementFormula
- **Deliverable:** `POST /api/tracks/{fp}/strata/analyze` produces a quick-tier formula
  with drum patterns, transitions, and energy narrative. Frontend shows it.

### Phase 2: Strata Page — Core Views (2-3 sessions)
**What:** The swim-lane arrangement map, pattern detail, and tier comparison
- ArrangementMap component (swim-lane view, time-aligned with waveform)
- Pattern blocks rendered in lanes with names and variation markers
- Transition markers
- Pattern detail panel (template grid, instance list, variation descriptions)
- Energy timeline overlay
- Arrangement summary panel
- **Tier selector + comparison:** Switch between quick/standard output. Highlight
  differences (patterns added/changed, transitions detected by one tier but not the other).
- View/Edit mode toggle (Edit mode is stub in Phase 2 — just the toggle and
  "coming soon" indicator. Real editing is Phase 4.)
- **Deliverable:** Full visual representation of both tiers' arrangement formulas
  with comparison support

### Phase 3: Standard Tier — Stem Separation + Per-Stem Quick (2-3 sessions)
**What:** Add HT Demucs stem separation and re-run quick-tier tools per stem
- `scue/layer1/strata/stems.py` — Demucs wrapper
- Stem file storage/management
- Per-stem quick analysis (M7 heuristics on drum stem, energy on bass stem, etc.)
- Layer activity detection (per-stem RMS with hysteresis)
- Cross-stem pattern merge
- Stem-aware transition detection
- Stem audio streaming API endpoint
- **Deliverable:** `POST /api/tracks/{fp}/strata/analyze?tier=standard` produces
  stem-attributed events, layer activity, and refined patterns.
- **New dependency:** `demucs` (PyTorch-based, ~2GB model download)
- **This is the expected sweet spot.** Evaluate accuracy here before deciding
  whether the deep tier is needed.

### Phase 4: Strata Editing & Annotation (2-3 sessions)
**What:** Human correction of arrangement data
- Pattern template editing (drum machine grid for drums, piano roll for melodic)
- Pattern instance management (add/remove/modify instances)
- "Apply pattern to sections" workflow (from annotation-followup #4)
- Transition editing (add/remove/reclassify)
- Layer activity correction
- Ground truth format extensions
- **Deliverable:** Full annotation/correction workflow for strata data

### Phase 5: TrackCursor + Layer 2 Integration (1-2 sessions)
**What:** Surface strata context in real-time playback
- Extend TrackCursor with ArrangementContext
- Extend useActiveEvents with arrangement data
- LiveEventDisplay shows arrangement context
- Live Deck Monitor shows active patterns + transitions
- **Deliverable:** Live cue engine has access to compositional context

### Phase 6: Deep Tier — ML Per-Stem Events (2-3 sessions, only if needed)
**What:** Replace standard tier's heuristic-on-stem approach with dedicated ML models
- ADT model on drum stem (model selection is a Phase 6 research task)
- Bass note-level transcription via crepe
- Vocal melody extraction
- AMT on "other" stem (YourMT3+ or similar)
- **Gate:** Only pursue if standard tier accuracy is insufficient for cue generation.
  Evaluate standard tier output on 10+ reference tracks before committing to this phase.
- **Deliverable:** Deep-tier strata with ML-derived events. Compare accuracy vs standard.

### Phase 7: Advanced Pattern Analysis (future, 3+ sessions)
**What:** ML-powered pattern analysis, few-shot detection
- Music-specific SSL embeddings (MERT/MuQ) for pattern similarity
- Few-shot pattern classification for custom event types
- Grouped event detection (fills as deviations from groove baselines)
- **Deliverable:** State-of-the-art arrangement analysis

### Phase 8: Cross-Track Arrangement Comparison (future)
**What:** Compare arrangement formulas across tracks
- Pattern library (reusable patterns across tracks)
- "Find tracks with similar arrangement" for set preparation
- Arrangement template suggestions for new tracks
- **Deliverable:** Library-level strata intelligence

---

## 10. Open Questions

### For the operator

**OQ-1: Taxonomy depth.** The 5-concept model (sections, layers, events, patterns,
transitions) — does this feel right? Or does it need another concept? The proposal
leaves "stem activity as a 5th category" as an open question per your answer. In the
data model, stem activity is modeled as `ActivitySpan` within `StemAnalysis`, which is
essentially a per-layer state timeline. Is this the right home for it, or should
activity be more prominent?

**OQ-2: Pattern granularity.** Should the engine detect ONLY drum patterns initially
(since those are highest-confidence from M7), or also attempt bass/melodic patterns
in the quick tier? The quick tier can detect "something repeating in the mid band"
from energy analysis, but it can't attribute it to a specific instrument without stems.

**OQ-3: The "other" stem.** HT Demucs gives us drums, bass, vocals, other. The
"other" bucket contains synths, keys, guitars, pads, FX, and everything else. For
EDM, this is often the most compositionally interesting stem (arps, leads, pads).
Should Phase 3+ include a second-pass separation of "other" into sub-layers, or
should we rely on event detection within the "other" stem to infer sub-layers?

**OQ-4: Ground truth for arrangement.** The existing annotation tool works with flat
event lists. Arrangement annotation is more complex (patterns, instances, variations).
Should we build a dedicated arrangement annotation workflow, or extend the existing
annotation page? The proposal assumes a dedicated workflow in Phase 5.

**OQ-5: Arrangement Page vs. unified page.** You said the arrangement page should
"absorb" the analysis viewer and annotation page. Should this be a single page with
mode switching (view/annotate/arrange), or genuinely three separate pages where the
arrangement page is the "full" view?

**~~OQ-6:~~ RESOLVED.** Both quick and standard tiers run by default. Each tier's
output is stored independently (no overwrite). UI supports tier switching and
comparison. Batch implications: 50 tracks at quick+standard = ~75-100 minutes
(dominated by stem separation). Acceptable for offline prep.

### Technical

**TQ-1: Demucs on Apple Silicon.** Demucs runs on PyTorch. PyTorch supports MPS
(Metal Performance Shaders) on Apple Silicon. Need to verify: does htdemucs_ft
work on MPS, and what's the actual performance? The 30-60s estimate is from
benchmarks on CUDA GPUs; MPS may be faster or slower.

**TQ-2: ADT model selection.** The drum research identifies several candidates but
doesn't pick one. Phase 4 needs a concrete model choice. The few-shot ADT paper
is promising but may be hard to run on Apple Silicon. Need a research spike.

**TQ-3: ArrangementFormula storage size.** The full formula (stems, events, patterns,
transitions) could be large. Need to estimate per-track JSON size and decide if
arrangement data should be in the main analysis JSON or a separate file. The proposal
assumes a separate file.

**TQ-4: Pattern similarity metric.** Cosine similarity on 16th-note slot vectors
works for drum patterns but not for melodic patterns. Need to define a pattern
similarity metric that works across types. DTW (Dynamic Time Warping) is the standard
for melodic similarity but is expensive.

---

## 11. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Demucs too slow on Apple Silicon | Medium | High (blocks deep tier) | Profile early in Phase 3. Fallback: lighter model (demucs_ft vs htdemucs_ft) or CPU-optimized variant. |
| Quick tier patterns too noisy | Medium | Medium | Quick tier is explicitly "coarse but useful." Deep tier refines. Operator tunes thresholds. |
| ADT model not available for Apple Silicon | Low-Medium | High (blocks Phase 4) | Multiple candidates exist. Worst case: use M7 heuristics on drum stem (still better than full-mix). |
| Arrangement Page scope creep | High | Medium | Each phase has a defined deliverable. Phase 2 is "view only." Editing is Phase 5. |
| Pattern naming auto-generation is bad | Medium | Low | Names are human-overridable. Start simple, iterate based on operator feedback. |
| Data model too complex | Low | High | Start with quick tier (simpler data). Extend for deep tier. Don't build all fields at once. |
| TrackCursor contract change blocked | Low | High | ArrangementContext is optional (None default). No breaking change. But still requires interfaces.md update + Brach approval per change protocol. |
| Stem storage disk usage | Low | Medium (50MB/track * N tracks) | Configurable. Default save, option to discard. Could add LRU eviction for oldest stems. |

---

## Appendix A: Compact Arrangement Formula Example

For a typical 6-minute EDM track:

```json
{
  "fingerprint": "a1b2c3...",
  "version": 1,
  "pipeline_tier": "quick",
  "stems": [],
  "patterns": [
    {
      "id": "drum-groove-A",
      "name": "kick-4otf-clap-2+4",
      "pattern_type": "drum_groove",
      "stem": "drums",
      "template": {
        "events": [
          {"type": "kick", "beat_position": 0},
          {"type": "kick", "beat_position": 4},
          {"type": "kick", "beat_position": 8},
          {"type": "kick", "beat_position": 12},
          {"type": "clap", "beat_position": 4},
          {"type": "clap", "beat_position": 12}
        ],
        "duration_bars": 1,
        "signature": "K...K.C.K...K.C."
      },
      "instances": [
        {"bar_start": 0, "bar_end": 16, "variation": "exact"},
        {"bar_start": 16, "bar_end": 31, "variation": "exact"},
        {"bar_start": 31, "bar_end": 32, "variation": "fill",
         "variation_description": "snare roll last 2 beats"},
        {"bar_start": 40, "bar_end": 64, "variation": "exact"}
      ],
      "tags": ["four-on-the-floor", "offbeat-clap"]
    }
  ],
  "sections": [
    {
      "section_label": "intro",
      "section_start": 0.0,
      "section_end": 30.0,
      "active_layers": ["drums"],
      "active_patterns": ["drum-groove-A"],
      "transitions": [],
      "energy_level": 0.3,
      "energy_trend": "rising",
      "layer_count": 1
    },
    {
      "section_label": "build",
      "section_start": 30.0,
      "section_end": 45.0,
      "active_layers": ["drums", "bass"],
      "active_patterns": ["drum-groove-A", "bass-ostinato-A"],
      "transitions": [
        {"type": "layer_enter", "timestamp": 30.0, "bar_index": 16,
         "layers_affected": ["bass"], "description": "bass enters",
         "energy_delta": 0.2}
      ],
      "energy_level": 0.6,
      "energy_trend": "rising",
      "layer_count": 2
    }
  ],
  "transitions": [
    {"type": "layer_enter", "timestamp": 30.0, "bar_index": 16,
     "section_label": "build", "layers_affected": ["bass"],
     "description": "bass enters", "energy_delta": 0.2},
    {"type": "fill", "timestamp": 58.1, "bar_index": 31,
     "section_label": "build", "patterns_affected": ["drum-groove-A"],
     "description": "drum fill before drop", "energy_delta": 0.1}
  ],
  "total_layers": 5,
  "total_patterns": 7,
  "arrangement_complexity": 0.72,
  "energy_narrative": "Intro: drums only, building. Build: bass enters, riser. Drop 1: full arrangement with arp. Breakdown: vocals + pad only. Build 2: bass re-enters, riser. Drop 2: groove B with extra fill."
}
```

---

## Appendix B: Research Summary

Key findings from the 6 research documents that inform this proposal:

1. **Arrangement formula extraction requires a stacked pipeline** (not a single model):
   separation → atomic events → pattern grouping → arrangement assembly.

2. **Stem separation is strong enough to be a building block** but not ground truth.
   EDM is one of the hardest genres. 4-stem (VDBO) is reliable; fine-grained is not.

3. **Drum events are dramatically easier on separated drum stems.** ADT on drum stems
   is the right first target for the deep tier.

4. **Fills are grouped deviations from groove baselines**, not raw acoustic primitives.
   They must be detected as a second pass over atomic hit streams.

5. **Few-shot learning is best at the fill subtype / custom event layer**, not at the
   core kick/snare/hat level.

6. **Pattern naming should be auto-generated from content** (e.g., slot signatures,
   rhythmic descriptions) with human override.

7. **SongFormer** is a potential alternative to allin1-mlx for section analysis
   (Windows-compatible, Transformer-based) but requires CUDA. Not yet integrated.

8. **M7's beat-synchronous classification approach** is fundamentally sound and should
   be preserved as the quick-tier drum detector. Stem separation makes it better, not
   obsolete.
