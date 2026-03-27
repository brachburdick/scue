# Layer 2 — Cue Generation Architecture Diagram

## System Context

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                            LAYER 1 OUTPUT                              │
 │                                                                        │
 │  DeckMix { cursors: [WeightedCursor, ...] }                           │
 │    ├── cursor.current_section    (label, progress, bars, fakeout)      │
 │    ├── cursor.next_section       (lookahead for anticipation)          │
 │    ├── cursor.upcoming_events    (kicks, snares, risers, stabs, ...)   │
 │    ├── cursor.current_features   (energy, mood, danceability)          │
 │    ├── cursor.beat_position      (beat_in_bar, bar_in_section, bpm)    │
 │    └── cursor.playback_state     (is_playing, is_on_air, position)     │
 │                                                                        │
 │  Data Tiers:                                                           │
 │    FULL ─── ArrangementFormula + M7 events + energy curves             │
 │    PIONEER ─ PSSI phrases + beat grid + waveform (heuristic fill-in)   │
 │    BEAT ──── BPM + beat position only                                  │
 └──────────────────────────────────┬──────────────────────────────────────┘
                                    │
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                                                                         │
 │                        L A Y E R   2                                    │
 │                     Cue Generation Engine                               │
 │                                                                         │
 │    "What is happening musically, and how significant is it?"            │
 │                                                                         │
 └──────────────────────────────────┬──────────────────────────────────────┘
                                    │
                                    ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                            LAYER 3 INPUT                               │
 │                                                                        │
 │  CueEvent stream { type, intensity, significance, musical_context }    │
 │                                                                        │
 │    "What should that look like?"                                       │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 2 Internal Architecture

```
                         DeckMix (from Layer 1)
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │  Deck 1      │ │  Deck 2      │ │  Deck N      │
     │  Generator   │ │  Generator   │ │  Generator   │    Per-deck,
     │  (weight:0.7)│ │  (weight:0.3)│ │  (weight:0.0)│    independent
     └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
            │                │                │
            ▼                ▼                ▼
     ┌──────────────────────────────────────────────┐
     │              CUE MIXER                       │
     │                                              │
     │  • Instantaneous cues: scale by deck weight  │
     │  • Continuous cues: interpolate by weight     │
     │  • Section cues: highest-weight deck wins     │
     │  • Drop cues below weight threshold (0.1)     │
     └──────────────────┬───────────────────────────┘
                        │
                        ▼
               Merged CueEvent stream
                  → to Layer 3
```

---

## Per-Deck Generator (the core processing unit)

```
                    TrackCursor (single deck)
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
  ┌───────────────┐ ┌──────────────┐  ┌──────────────────┐
  │ CONTEXT       │ │ EVENTS       │  │ STATE            │
  │ COMPUTER      │ │ (from cursor)│  │ (from last tick) │
  │               │ │              │  │                  │
  │ • section     │ │ • kicks      │  │ • prev section   │
  │ • energy      │ │ • snares     │  │ • prev bar       │
  │ • exertion    │ │ • risers     │  │ • anticipation   │
  │ • tension     │ │ • stabs      │  │   fired flag     │
  │ • arousal     │ │ • hihats     │  │ • energy history │
  │ • valence     │ │ • arps       │  │ • exertion avg   │
  │ • confidence  │ │ • ...        │  │                  │
  │ • data_tier   │ │              │  │                  │
  └───────┬───────┘ └──────┬───────┘  └────────┬─────────┘
          │                │                   │
          └────────────────┼───────────────────┘
                           │
                           ▼
  ╔════════════════════════════════════════════════════════╗
  ║              GENERATOR PIPELINE                       ║
  ║                                                       ║
  ║  Each generator is a pure function:                   ║
  ║  (cursor, state, context, config) → [CueEvent]       ║
  ║                                                       ║
  ║  ┌─────────────────────────────────────────────┐      ║
  ║  │ 1. SECTION GENERATOR                        │      ║
  ║  │    • section_change  (on transition)        │      ║
  ║  │    • section_anticipation  (N bars before)  │      ║
  ║  │    • energy_level  (per bar, with trend)    │      ║
  ║  └─────────────────────────────────────────────┘      ║
  ║  ┌─────────────────────────────────────────────┐      ║
  ║  │ 2. PERCUSSION GENERATOR                     │      ║
  ║  │    • kick  (from events or inferred)        │      ║
  ║  │    • snare  (from events)                   │      ║
  ║  │    • [future: hihat, perc_pattern_change]   │      ║
  ║  └─────────────────────────────────────────────┘      ║
  ║  ┌─────────────────────────────────────────────┐      ║
  ║  │ 3. MELODIC GENERATOR  [future]              │      ║
  ║  │    • riser, faller, stab, arp_*             │      ║
  ║  └─────────────────────────────────────────────┘      ║
  ║  ┌─────────────────────────────────────────────┐      ║
  ║  │ 4. AMBIENT GENERATOR  [future]              │      ║
  ║  │    • mood_shift, impact (composite)         │      ║
  ║  └─────────────────────────────────────────────┘      ║
  ╚════════════════════════╤══════════════════════════════╝
                           │
                           ▼
  ┌────────────────────────────────────────────────────────┐
  │              SIGNIFICANCE SCORER                       │
  │                                                        │
  │  For each raw cue event:                               │
  │                                                        │
  │  significance = base_weight[type]                      │
  │               × section_weight[section]                │
  │               × exertion_factor                        │
  │               × confidence                             │
  │                                                        │
  │  Example:                                              │
  │    kick in drop:  0.8 × 1.5 × 1.0 × 1.0 = 1.20  ✓   │
  │    kick in break: 0.8 × 0.7 × 1.8 × 1.0 = 1.01  ✓   │
  │    hihat in drop: 0.2 × 0.8 × 0.5 × 1.0 = 0.08  ✗   │
  │                                     threshold: 0.1     │
  │                                                        │
  │  Below threshold → demoted to metadata (not discarded) │
  │  Above threshold → promoted to CueEvent                │
  └────────────────────────┬───────────────────────────────┘
                           │
                           ▼
  ┌────────────────────────────────────────────────────────┐
  │              RATE LIMITER                              │
  │                                                        │
  │  Per-type minimum intervals:                           │
  │    section_change:    0ms   (never limited)            │
  │    section_anticip:   0ms   (never limited)            │
  │    kick:            100ms   (max ~10/sec)              │
  │    snare:           200ms   (max ~5/sec)               │
  │    hihat:           500ms   (max ~2/sec)               │
  │    energy_level:   1000ms   (once per second)          │
  │    riser:             0ms   (continuous, not limited)   │
  │                                                        │
  │  Within each window: keep highest-significance event   │
  └────────────────────────┬───────────────────────────────┘
                           │
                           ▼
               Per-deck CueEvent list
                (to Cue Mixer above)
```

---

## CueEvent — What Layer 3 Receives

```
  ┌──────────────────────────────────────────────────────────────┐
  │  CueEvent                                                    │
  │                                                              │
  │  id:            "cue_00042"                                  │
  │  type:          "section_change"                             │
  │  timestamp:     1711407600.123                               │
  │  duration:      null  (instantaneous)                        │
  │  intensity:     0.95                                         │
  │  significance:  1.42                                         │
  │  priority:      10  (never dropped under load)               │
  │  deck_number:   1                                            │
  │                                                              │
  │  payload: {                                                  │
  │    from_label:    "build",                                   │
  │    to_label:      "drop",                                    │
  │    is_impact:     true,                                      │
  │    is_fakeout:    false,                                     │
  │    energy_delta:  0.6                                        │
  │  }                                                           │
  │                                                              │
  │  musical_context: {                                          │
  │    section_label:    "drop",                                 │
  │    section_progress: 0.0,                                    │
  │    track_energy:     0.9,        ◄── absolute (from analysis)│
  │    energy_exertion:  1.5,        ◄── relative (vs rolling avg│)
  │    energy_trend:     "peak",                                 │
  │    tension:          0.1,        ◄── just released (post-drop│)
  │    arousal:          0.9,        ◄── Russell/Thayer          │
  │    valence:          0.7,        ◄── Russell/Thayer          │
  │    track_mood:       "euphoric",                             │
  │    data_tier:        "full",     ◄── quality indicator       │
  │    confidence:       0.95,       ◄── how much to trust this  │
  │    palette_lock:     true        ◄── suppress palette flicker│
  │  }                                                           │
  │                                                              │
  │  demoted_events: [               ◄── sub-threshold events    │
  │    {type: "hihat", intensity: 0.3, ...},                     │
  │    {type: "arp_note", intensity: 0.2, ...}                   │
  │  ]                                                           │
  └──────────────────────────────────────────────────────────────┘
```

---

## Tiered Data Flow

```
  ┌─────────────────────────────────────────────────────────────────┐
  │ FULL TIER  (offline analysis + M7 detectors)                    │
  │                                                                 │
  │  ArrangementFormula ──► sections, transitions, stems, patterns  │
  │  M7 Detectors ────────► kicks, snares, risers, stabs, arps     │
  │  Energy curves ───────► per-bar energy, trend                   │
  │  Drum patterns ───────► expanded to per-beat events at runtime  │
  │                                                                 │
  │  confidence: 0.8–1.0                                            │
  │  All generators active. Full context. Best show.                │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ PIONEER TIER  (PSSI phrases + beat grid + waveform, no audio)   │
  │                                                                 │
  │  Pioneer phrases ─────► section labels (intro/build/drop/etc)   │
  │  Beat grid ───────────► beat positions, downbeats               │
  │  Section heuristics ──► energy (drop=0.9, break=0.3)           │
  │                         trend (build=rising, drop=peak)         │
  │                         arousal/valence (from lookup table)      │
  │  Kick ────────────────► inferred from downbeat + section type   │
  │                                                                 │
  │  confidence: 0.3–0.6  (heuristic, flagged)                     │
  │  Section + beat + kick generators. Heuristic context.           │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ BEAT TIER  (BPM + beat position only, no phrases)               │
  │                                                                 │
  │  Beat grid ───────────► beat positions, downbeats               │
  │  Kick ────────────────► inferred from every downbeat            │
  │  Energy ──────────────► flat 0.5 (unknown)                      │
  │                                                                 │
  │  confidence: 0.1–0.3                                            │
  │  Beat + kick only. Minimal context. "Something is better        │
  │  than nothing" — at least beat-reactive.                        │
  └─────────────────────────────────────────────────────────────────┘
```

---

## Context Computer Detail

```
  ┌──────────────────────────────────────────────────────────────┐
  │  CONTEXT COMPUTER                                            │
  │                                                              │
  │  Runs once per tick. Computes MusicalContext from cursor.     │
  │                                                              │
  │  ┌────────────────────────────────────────────┐              │
  │  │ ABSOLUTE VALUES  (from cursor directly)     │              │
  │  │                                             │              │
  │  │  section_label ← cursor.current_section     │              │
  │  │  section_progress ← cursor.section.progress │              │
  │  │  track_energy ← cursor.features.energy      │              │
  │  │  track_mood ← cursor.features.mood          │              │
  │  │  data_tier ← inferred from available data   │              │
  │  └────────────────────────────────────────────┘              │
  │                                                              │
  │  ┌────────────────────────────────────────────┐              │
  │  │ DERIVED VALUES  (computed by L2)            │              │
  │  │                                             │              │
  │  │  energy_exertion ← energy / rolling_avg     │              │
  │  │    (rolling_avg updated per bar,            │              │
  │  │     window = configurable, default 8 bars)  │              │
  │  │                                             │              │
  │  │  energy_trend ← compare energy to N bars ago│              │
  │  │    rising:  delta > +threshold              │              │
  │  │    falling: delta < -threshold              │              │
  │  │    peak:    energy > 0.8 AND trend was rising│             │
  │  │    valley:  energy < 0.3 AND trend was falling│            │
  │  │    stable:  |delta| < threshold             │              │
  │  │                                             │              │
  │  │  tension ← f(section_label, progress,       │              │
  │  │              upcoming_events, riser_active)  │              │
  │  │    build sections: tension = progress²       │              │
  │  │    riser active: tension += riser.progress   │              │
  │  │    drop hit: tension snaps to 0.0            │              │
  │  │    breakdown: tension = 0.1 (relaxed)        │              │
  │  │                                             │              │
  │  │  arousal ← f(energy, onset_density, bpm)    │              │
  │  │  valence ← f(mood, key_mode, spectral_bright)│             │
  │  │    (MVP: use section heuristic lookup table) │              │
  │  │                                             │              │
  │  │  confidence ← min(data_tier_base, field_confs)│            │
  │  │                                             │              │
  │  │  palette_lock ← arousal > 0.7               │              │
  │  └────────────────────────────────────────────┘              │
  └──────────────────────────────────────────────────────────────┘
```

---

## Configuration Stack (layered, user-overridable)

```
  ┌─────────────────────────────────────────────────────────┐
  │  LAYER 3: YAML Power-User Rules  [Phase 2+]            │
  │  config/cue-rules.yaml                                  │
  │                                                         │
  │  Full condition→action rules. Can override anything.    │
  │  - name: "my_custom_drop"                               │
  │    when: {section_change, to_label: drop, exertion>1.5} │
  │    then: {emit: impact, intensity: 1.0}                 │
  │                                                         │
  ├─────────────────────────────────────────────────────────┤
  │  LAYER 2: Emotional Space Tuning  [Phase 2+]           │
  │  config/mood-profiles.yaml                              │
  │                                                         │
  │  2D plane: energy × mood → behavior adjustments         │
  │  Users position genres/contexts on the plane.           │
  │                                                         │
  ├─────────────────────────────────────────────────────────┤
  │  LAYER 1: Presets  [Phase 1 / MVP]                      │
  │  config/cue-presets/                                     │
  │                                                         │
  │  Named presets with all tuning values:                   │
  │    edm-club.yaml                                        │
  │    melodic-chill.yaml                                   │
  │    dark-heavy.yaml                                      │
  │                                                         │
  │  Each preset defines:                                   │
  │    • base_weights per event type                        │
  │    • section_weights per section label                  │
  │    • transition_intensity matrix                        │
  │    • section_intensity_curves                           │
  │    • rate_limits per cue type                           │
  │    • significance_threshold                             │
  │    • anticipation_bars                                  │
  │    • exertion_window                                    │
  ├─────────────────────────────────────────────────────────┤
  │  LAYER 0: Hardcoded Defaults  [always present]          │
  │  Built into Python code                                 │
  │                                                         │
  │  Sane defaults so the system works with zero config.    │
  │  Every value has a hardcoded fallback.                  │
  └─────────────────────────────────────────────────────────┘

  Resolution order: YAML rules > mood tuning > preset > defaults
  (higher layers override lower layers)
```

---

## Rule Engine Evolution

```
  PHASE 1 (MVP)                 PHASE 2                    PHASE 3
  ─────────────                 ───────                    ───────

  Python functions              + YAML rules               + Python plugins
  in generators/                in config/cue-rules.yaml   in user_rules/

  ┌──────────────┐              ┌──────────────┐           ┌──────────────┐
  │ section_cues │              │ YAML rule    │           │ class Double │
  │   .generate()│              │ evaluator    │           │ DropDetector │
  │              │              │              │           │ (CuePlugin)  │
  │ if section   │              │ when:        │           │              │
  │   changed:   │              │   type: kick │           │ def evaluate │
  │   emit cue   │              │   section:   │           │   (cursor,   │
  │              │              │     drop     │           │    history): │
  │ hardcoded    │              │ then:        │           │   ...        │
  │ heuristics   │              │   boost: 1.5 │           │              │
  └──────────────┘              └──────────────┘           └──────────────┘

  Simple. Ships fast.           Tunable without code.      Anything goes.
  Covers 80% of cases.         User-editable.             Expert escape hatch.
                                Shareable presets.
```

---

## Timing Model

```
  Time ────────────────────────────────────────────────────►

  Layer 1 ticks at 40Hz (every 25ms)
       │    │    │    │    │    │    │    │    │    │
       ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼

  Layer 2 processes every tick, but emits selectively:

  Beat events ──────── on beat boundary (from cursor.beat_position)
       ▼         ▼         ▼         ▼
       B1        B2        B3        B4

  Section cues ──────── on section boundary
       ┃                                              ┃
    section_change                              section_change
    (build→drop)                                (drop→breakdown)

  Anticipation ──── fires once, N bars before section boundary
            ▲
       "drop in 4 bars"

  Energy/progress ── once per bar (on downbeat)
       ▼                   ▼                   ▼
    energy:0.6          energy:0.75          energy:0.9
    trend:rising        trend:rising         trend:peak

  Kick/snare ──── on detected event within current tick
       ▼    ▼         ▼              ▼    ▼
       K    S         K              K    S
       │              │
       └── rate-limited: if another kick within 100ms, keep higher significance
```

---

## Multi-Deck Blending Example

```
  Track A (outgoing):  drop ──────────────► breakdown ─────►
  Deck weight:         1.0 ─── 0.8 ─── 0.5 ─── 0.2 ─── 0.0

  Track B (incoming):  build ─────────────► drop ──────────►
  Deck weight:         0.0 ─── 0.2 ─── 0.5 ─── 0.8 ─── 1.0

                       ◄──── DJ transition (crossfade) ────►

  Blended cue stream:

  INSTANTANEOUS (kick):
    kick from A: intensity × 0.5 = 0.45   ← if > threshold, emit
    kick from B: intensity × 0.5 = 0.40   ← if > threshold, emit
    (both can fire — they're separate events)

  CONTINUOUS (energy_level):
    blended = A.energy × 0.5 + B.energy × 0.5
            = 0.9 × 0.5 + 0.6 × 0.5 = 0.75

  SECTION (section_change):
    Track B crosses build→drop at weight 0.8
    Track A is at weight 0.2 (below threshold)
    → section_change fires from Track B only (higher weight)
    → no duplicate transition
```
