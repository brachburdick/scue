# SCUE — Architecture Plan

## What This App Does

SCUE automates lighting, laser, and visual cues for live DJ sets. It analyzes tracks offline, tracks playback state in real time via Pioneer Pro DJ Link, generates semantic music events, maps those events to abstract effects, and outputs control signals to hardware via standard protocols. The goal: a single DJ can run a full light/laser/visual show with zero manual cue triggering.

---

## Guiding Principles

These apply to every layer and every PR.

- **Each layer is a standalone service with a defined interface.** Layers communicate through typed event streams or request/response APIs. No layer reaches into another layer's internals.
- **Test each layer in isolation before integrating.** Every layer must have a mock/stub mode that feeds it synthetic input so it can be developed and verified independently.
- **Prefer declarative configuration over code changes.** Effect definitions, fixture profiles, and routing tables should be data (JSON/YAML), not hardcoded logic. Users and developers should be able to change behavior without touching source code.
- **Fail gracefully under real-time pressure.** Missed deadlines are worse than approximate answers. Every real-time path must have a fallback (e.g., hold last known state, fall back to beat-reactive defaults).
- **Incremental delivery.** Each layer has a Minimum Viable version that proves the concept before investing in the full version.

---

## Layer 1 — Track Analysis & Live Tracking

### Purpose

Produce a structured, time-indexed description of a track's musical content, and maintain a real-time cursor into that data synchronized with DJ playback.

### Sub-layer 1A — Offline Track Analysis

**Input:** Audio file (WAV, MP3, FLAC, AIFF).
**Output:** A `TrackAnalysis` object stored in a local database (SQLite is fine to start).

The `TrackAnalysis` contains three tiers of data, built incrementally:

**Tier 1 — Section Segmentation (build this first)**
- Segment the track into labeled sections: `intro`, `verse`, `build`, `drop`, `breakdown`, `outro`.
- Each section has: `start_time`, `end_time`, `label`, `confidence`, `bar_count`, `expected_bar_count`, `irregular_phrase` (boolean).

**The 8-bar structural prior.** EDM tracks overwhelmingly follow an 8-bar (or multiple-of-8) phrase structure. The segmentation algorithm should use this as a strong prior:
- After initial boundary detection (via ML model or spectral change), snap candidate boundaries to the nearest 8-bar grid line. If a boundary is within ~1 bar of an 8-bar grid line, snap it. If it's far from any grid line, keep it but flag it.
- Score candidate segmentations by how well they fit 8-bar multiples. A segmentation that produces `[16, 8, 16, 32, 16, 8]` bars is more likely correct than `[15, 9, 17, 31, 15, 9]`.
- When a section does NOT land on an 8-bar multiple, flag it explicitly: `irregular_phrase: true`, `bar_count: 12`, `expected_bar_count: 8` (or 16). These are musically significant — they indicate fakeouts, extensions, or unusual arrangement choices that the cue system should handle specially.

**EDM flow model.** Use knowledge of typical EDM arrangement patterns as a labeling prior:
- Common flow patterns: `intro → verse → build → drop → breakdown → build → drop → outro`, or `intro → build → drop → breakdown → drop → outro`. The model should score section label sequences against known patterns and prefer labels that produce a valid flow.
- Constraints: a `build` is almost always followed by a `drop` (or a `fakeout` then `build`). A `drop` is almost always preceded by a `build`. An `intro` is always first. An `outro` is always last. If the raw detector labels a section in a way that violates these patterns, re-evaluate.
- Flag fakeout drops explicitly: if a `drop` section is ≤4 bars and is followed by a `build` or `breakdown`, tag it `fakeout: true`.
- These priors should be soft constraints (Bayesian or scoring-based), not hard rules. Unusual tracks exist, and the system should handle them gracefully with lower confidence scores rather than forcing a wrong label.

**Beatgrid source of truth.** The offline analysis produces its own beat/downbeat grid using librosa or similar. However, this is NOT the authoritative grid — see Sub-layer 1B for how Pioneer/rekordbox beatgrid data takes precedence at runtime. The offline grid is used during analysis as a working reference, and is replaced or corrected once Pioneer data becomes available.

- Store the offline-derived downbeat grid alongside the section data, but tag it as `source: "analysis"` so it can be compared against the Pioneer grid later.

**Tier 2 — Event Detection (build second)**
- Detect discrete musical events and store them as a time-indexed event list.
- Event types, in priority order:
  - `kick`, `snare`, `hihat`, `clap` — onset times + velocity (relative intensity).
  - `riser`, `faller` — start/end times + intensity curve (linear, exponential, etc.).
  - `stab` / `adlib` — one-shot events with onset time + intensity.
  - `arp` — note pattern as relative intervals (e.g., `[0, 4, 7, 12, 7]`), onset times of each note, and the overall rhythmic pattern (e.g., 16th notes, triplets).
  - `note_sequence` — for melodic phrases that aren't arps, store relative pitch contour and rhythm.
  - `effect_sweep` — filter sweeps, panning oscillation, etc. Store: parameter name, start/end times, start/end values, curve shape.
- Instrument grouping (stretch goal): cluster events that likely come from the same source (e.g., "this kick and this slightly-different kick are the same drum"). Use timbral similarity (MFCC distance or spectral centroid). This is a nice-to-have for Tier 2 but not blocking.

**Tier 3 — Track-Level Features (build third)**
- Overall energy curve (loudness over time, smoothed).
- Valence/mood heuristic (major/minor key detection, tempo, spectral brightness).
- Danceability / drive metric.
- Key and key changes.
- These are coarse descriptors used by Layer 3 to set the "mood" of the effect palette. They do not need to be frame-accurate.

**Implementation notes:**
- The existing POC already uses librosa + allin1-mlx + ruptures. Continue with these.
- For Tier 1 section segmentation: run the ML boundary detector first (allin1-mlx), then apply the 8-bar snapping pass, then run the flow model labeler. These are sequential refinement stages, not a single model.
- For Tier 2 event detection: librosa.onset for percussive events; a dedicated riser/faller detector can use spectral flux over longer windows; arp detection can use pitch tracking (librosa.pyin or crepe) plus onset alignment.
- Store results as JSON blobs keyed by a track fingerprint (audio hash). Re-analysis should be idempotent — same file produces same result.
- Analysis is offline and can be slow. Optimize later.

**Pioneer enrichment pass (runs once per track, first time it's loaded on a deck):**
The first time SCUE sees a track played via Pro DJ Link, it receives Pioneer/rekordbox metadata including BPM, beatgrid, key, and (if available) rekordbox's own phrase analysis. SCUE should use this data to refine the offline analysis:
- **Beatgrid:** Replace the librosa-derived beatgrid with the Pioneer beatgrid. The DJ has likely hand-corrected this in rekordbox — it is more reliable. Re-align all Tier 1 section boundaries and Tier 2 event timestamps to the Pioneer grid. Store the updated analysis as a new version in the database (do not overwrite the original — keep both).
- **BPM:** Use Pioneer's BPM as the authoritative base BPM for tempo scaling calculations.
- **Key:** Use Pioneer's key detection as the reference key.
- **Rekordbox phrase analysis (if available):** Some Pioneer hardware exposes rekordbox's own phrase/section data. If available, compare it against SCUE's section labels. Where they agree, increase SCUE's confidence score. Where they disagree, log the divergence (see below).
- **Divergence log:** For every field where SCUE's analysis differs from Pioneer/rekordbox data, log a `DivergenceRecord` to the database:
  ```
  DivergenceRecord {
    track_id:       track fingerprint
    field:          "beatgrid" | "bpm" | "key" | "section_boundary" | "section_label"
    scue_value:     what SCUE computed
    pioneer_value:  what Pioneer/rekordbox reported
    resolution:     "pioneer_adopted" | "scue_kept" | "manual_override"
    timestamp:      when this was recorded
  }
  ```
  This log is essential for tuning. Over time, patterns in the divergence log will reveal whether SCUE's detectors are systematically wrong in specific ways (e.g., "SCUE consistently places drop boundaries 1 beat early" or "SCUE labels breakdowns as verses 40% of the time"). This data feeds directly into improving the detection algorithms.

**Testing strategy:**
- Unit tests for each detector against hand-labeled test tracks. Start with 3–5 tracks spanning genres (melodic techno, dubstep, house, DnB, trance).
- A visual QA tool (already partially built — the RGB waveform with section markers) to sanity-check results by eye/ear.

---

### Sub-layer 1B — Live Playback Tracking

**Input:** Pro DJ Link UDP packets from Pioneer hardware (ports 50000/50001).
**Output:** A `PlaybackState` object updated in real time, plus a `TrackCursor` that maps the current playback position into the pre-analyzed `TrackAnalysis`.

**Pioneer as metadata authority.** The Pro DJ Link stream provides beatgrid, BPM, key, and (depending on hardware/firmware) rekordbox phrase data. These are treated as the primary source of truth for timing and musical metadata — they have been verified or corrected by the DJ in rekordbox. SCUE's own offline analysis (librosa-derived beatgrid, BPM, key) serves as the initial working model and as a fallback when Pioneer data is unavailable, but is superseded by Pioneer data once received.

When a track is first loaded on a deck and Pioneer metadata arrives:
1. Trigger the **Pioneer enrichment pass** described in Sub-layer 1A. This updates the stored `TrackAnalysis` with the Pioneer beatgrid, BPM, and key, re-aligns section boundaries and events, and logs any divergences.
2. The `TrackCursor` always reads from the enriched (Pioneer-aligned) analysis if available, falling back to the raw offline analysis if the enrichment pass hasn't run yet (e.g., track was analyzed offline but never played on Pioneer hardware).

The `PlaybackState` contains:
- Per deck: current track ID, BPM, pitch/tempo adjustment, beat-within-bar (1–4), playback position (time), play/pause/cue state.
- Master deck identification (which deck is live).
- Crossfader position (if available from the protocol).

The `TrackCursor` provides:
- `current_section`: which section is playing right now, plus progress through it (0.0–1.0).
- `next_section`: what's coming next, and time until transition.
- `upcoming_events`: a sliding window of the next N events from the Tier 2 event list, time-adjusted for current tempo.
- `current_features`: interpolated Tier 3 features for the current position.

**Tempo adaptation:** The event timestamps from offline analysis are at the track's original BPM. The cursor must scale all timestamps by `(original_bpm / current_bpm)` to account for the DJ's pitch fader. This is a simple linear scaling — apply it everywhere timestamps are read.

**Effect/filter resilience:** The cursor tracks position, not audio content. It does not listen to the audio output of the mixer. This means mixer effects (reverb, delay, filter sweeps) and EQ changes do not confuse the tracking. The cursor simply follows the playback position reported by Pro DJ Link. If effects are applied, the cues fire as if the clean track were playing — which is correct behavior, since the DJ is adding effects on top intentionally.

**Key adaptation (stretch goal):** If the DJ uses key sync or pitch-shifts significantly, note the key offset and pass it downstream so Layer 3 can adjust color mappings if desired.

**Testing strategy:**
- Mock the Pro DJ Link UDP stream with recorded packet captures. Play back captured sessions and verify the cursor tracks correctly.
- Test tempo changes: capture a session where the DJ pitches a track up/down and verify event timestamps scale correctly.
- Test deck switching: verify the cursor follows the master/active deck.
- Test enrichment pass: analyze a track offline, then feed Pioneer metadata for the same track. Verify that the stored `TrackAnalysis` is updated with Pioneer beatgrid/BPM/key, section boundaries are re-aligned, and a `DivergenceRecord` is logged for every field that differed.
- Test fallback: verify the cursor works correctly with an un-enriched analysis (Pioneer data not yet available).

---

## Layer 2 — Cue Generation (Music → Semantics)

### Purpose

Transform the raw `TrackCursor` output into a stream of **semantic cue events** that describe musical meaning, not hardware instructions. This layer knows everything about music and nothing about lights.

### The Cue Event Model

Every cue event is a typed message with a common header:

```
CueEvent {
  id:             unique event ID
  type:           string (see taxonomy below)
  timestamp:      when this event fires (absolute time or beat position)
  duration:       how long the event lasts (null for instantaneous)
  intensity:      0.0–1.0 (how "strong" this event is)
  musical_context: {
    section_label:    current section (verse, build, drop, etc.)
    section_progress: 0.0–1.0 (how far into the current section)
    track_energy:     0.0–1.0 (from Tier 3 energy curve)
    track_mood:       string (dark, euphoric, melancholic, aggressive, etc.)
  }
  payload:        type-specific data (see below)
}
```

### Cue Type Taxonomy

**Section cues (generated from Tier 1):**
- `section_change` — fires when a new section begins. Payload: `{ from_label, to_label, is_fakeout }`. This is the highest-priority cue — it drives the biggest visual changes.
- `section_anticipation` — fires N beats/seconds before an upcoming section change. Payload: `{ upcoming_label, beats_until, is_fakeout }`. Allows Layer 3 to start building intensity before a drop, for instance.
- `section_progress` — continuous (fires every beat or every bar). Payload: `{ bars_elapsed, bars_total, progress }`. Allows smooth ramping effects within a section.

**Rhythmic cues (generated from Tier 2 percussion events):**
- `beat` — fires on every beat. Payload: `{ beat_in_bar (1–4), is_downbeat }`.
- `kick` — fires on kick hits. Payload: `{ velocity }`.
- `snare` — fires on snare hits. Payload: `{ velocity }`.
- `percussion_pattern_change` — fires when the drum pattern density changes (e.g., snare doubles from every 4 beats to every 2 beats). Payload: `{ element, old_interval, new_interval }`.

**Melodic/harmonic cues (generated from Tier 2 tonal events):**
- `arp_start` / `arp_note` / `arp_end` — for arpeggios. Payload includes `{ note_index, interval_from_root, total_notes, pattern }`.
- `riser` / `faller` — for sweeps and builds. Payload: `{ progress (0.0–1.0), curve_type }`. These fire continuously from start to end.
- `stab` — for one-shot melodic hits. Payload: `{ velocity }`.

**Effect cues (generated from Tier 2 effect events):**
- `sweep` — for filter/panning/modulation sweeps. Payload: `{ parameter, value (0.0–1.0), direction }`. Fires continuously.
- `impact` — synthesized cue for big moments (e.g., the first beat of a drop). Payload: `{ magnitude }`. Generated by combining section_change + high energy + kick coincidence.

**Ambient cues (generated from Tier 3):**
- `mood_shift` — fires when the track-level mood changes meaningfully. Payload: `{ from_mood, to_mood }`.
- `energy_level` — continuous, fires every bar. Payload: `{ energy (0.0–1.0), trend (rising/falling/stable) }`.

### Cue Priority

When the downstream system is overloaded, cues are dropped in this order (lowest priority first): `energy_level`, `mood_shift`, `section_progress`, `beat`, `sweep`, `arp_note`, `percussion_pattern_change`, then everything else. `section_change` and `impact` are never dropped.

### Implementation Notes

- This layer is a pure function: `(TrackCursor state) → [CueEvent]`. It runs on every tick (every beat, or every ~10ms, whichever is more appropriate — start with every beat).
- No state beyond the current `TrackCursor` snapshot. This makes it trivially testable.
- The `section_anticipation` cue requires looking ahead in the `TrackAnalysis` data, which the `TrackCursor.next_section` already provides.
- The `impact` cue is a heuristic composite: fire it when `section_change` to a `drop` coincides with a high-velocity `kick` and high `track_energy`. Tune the threshold by ear.

### Testing Strategy

- Feed recorded `TrackCursor` sequences (captured from Layer 1 tests) through Layer 2 and snapshot the cue output.
- Validate cue timing against hand-annotated "expected cue" files for test tracks.
- Build a simple cue visualizer (text log or timeline graphic) to visually inspect output during development.

---

## Layer 3 — Effect Engine (Semantics → Abstract Output)

### Purpose

Map semantic cue events to abstract visual/lighting instructions. This layer knows about visual concepts (color, brightness, movement, speed) but not about specific hardware (not about DMX channels, pixel addresses, or laser ILDA frames).

This is the most architecturally complex layer. It has four sub-components.

---

### Sub-layer 3A — Effect Library

An **effect** is a parameterized generator function that produces abstract output over time. Effects are not one-shot actions — they are running processes that can be modulated.

Each effect operates on one or more **abstract channels**:
- `brightness` (0.0–1.0)
- `color` (HSV or RGB, 0.0–1.0 per component)
- `position` (normalized 0.0–1.0 across the fixture group's spatial extent, 1D or 2D)
- `beam_width` (0.0–1.0, for lasers/moving heads)
- `strobe_rate` (Hz, 0 = off)
- `visual_trigger` (a discrete signal for video/visual content switches)

An effect definition looks like this (stored as JSON/YAML):

```yaml
effect:
  name: "chase"
  description: "Sequential activation across fixture positions"
  parameters:
    speed:        { type: float, min: 0.1, max: 20.0, default: 1.0, unit: "hz" }
    width:        { type: float, min: 0.05, max: 1.0, default: 0.2 }
    direction:    { type: enum, values: [forward, reverse, bounce], default: forward }
    color:        { type: color, default: [1.0, 0.0, 0.0] }
    intensity:    { type: float, min: 0.0, max: 1.0, default: 1.0 }
  output_channels: [brightness, color, position]
```

The effect's runtime logic is a function: `(time, parameters) → { channel: value }` for each fixture in the group. The chase effect, for instance, computes a brightness peak that moves across the position axis at the given speed.

**Starter effect library (build these first):**
- `static` — solid color/brightness, no movement. The baseline.
- `pulse` — brightness ramps up then decays. Parameters: attack, sustain, decay, intensity. Good for beats/kicks.
- `chase` — sequential activation across positions. Good for arps, runners.
- `strobe` — rapid on/off. Parameters: rate, duty cycle. Good for drops, impacts.
- `sweep` — smooth movement across position axis. Good for panning effects, risers/fallers.
- `breathe` — slow sinusoidal brightness oscillation. Good for verses, low-energy sections.
- `rainbow` — color cycling. Parameters: speed, saturation, brightness.
- `blackout` — everything off. Used for fakeout drops, dramatic pauses.
- `full_send` — max brightness, max saturation, max strobe. The "drop hits" effect.

More effects can be added as data files without code changes.

---

### Sub-layer 3B — Routing Table

The routing table is the user-facing configuration that connects cue types to effect instances on specific output groups. It is the answer to "what happens when a kick fires?"

A route looks like this:

```yaml
route:
  name: "kick_pulse_on_pars"
  trigger:
    cue_type: "kick"
    conditions:                          # optional filters
      musical_context.section_label: [drop, build]
      intensity: { min: 0.5 }
  effect: "pulse"
  parameter_bindings:
    intensity: "cue.intensity"           # bind effect param to cue data
    attack: 0.02                         # fixed value (seconds)
    decay: 0.15
    color: "palette.accent"              # bind to current color palette
  target_group: "pars_all"               # which fixtures (defined in Layer 4)
  priority: 5                            # for the blending system
  blend_mode: "HTP"                      # highest takes precedence
```

Key concepts:
- **Parameter bindings** can be fixed values, references to cue event data, or references to the current palette/mood state.
- **Conditions** filter which cues trigger the route. A kick during a verse might trigger a gentle pulse; a kick during a drop triggers a strobe. These are separate routes with different conditions.
- **Target groups** are named sets of fixtures defined in Layer 4's venue configuration. The routing table references them by name, never by hardware address.
- The user edits this table to customize the show.

**Default routing presets:** Ship a few complete routing tables as starting points ("EDM club," "melodic/emotional," "aggressive/bass"). Users modify from there.

---

### Sub-layer 3C — Priority & Blending System

Multiple routes can target the same fixture group simultaneously. The blending system resolves conflicts.

Rules:
- Each active effect instance has a **priority** (integer, higher = wins ties).
- **HTP (Highest Takes Precedence):** For brightness/intensity, the highest value wins. This is the default and the safe choice — it means adding more effects never makes things dimmer.
- **LTP (Latest Takes Precedence):** For color and position, the most recently triggered effect wins. This prevents color mud from mixing incompatible hues.
- Effects have a **lifetime.** When the triggering cue ends (or the effect's duration expires), the effect fades out over a configurable release time. This prevents hard cuts.
- A `section_change` cue can optionally **flush** all active effects and start fresh, which is useful for dramatic transitions (build → drop).

The blending system outputs, per fixture group, a set of abstract channel values every tick.

---

### Sub-layer 3D — Palette & Mood Engine

Rather than hardcoding colors in every route, maintain a **current palette** that shifts based on track mood and section.

A palette contains:
- `primary`, `secondary`, `accent` colors
- `base_brightness` (0.0–1.0)
- `base_speed_multiplier` (affects how fast effects run)
- `strobe_allowed` (boolean — no strobes during a mellow verse)

The mood engine updates the palette based on `mood_shift` and `energy_level` cues from Layer 2. For instance:
- High energy + euphoric mood → bright, saturated, warm palette, high speed multiplier
- Low energy + melancholic mood → dim, desaturated, cool palette, low speed multiplier
- Drop section → unlock strobes, max brightness ceiling, accent color intensifies

Palettes can be defined as presets and the user can override them. The routing table's `"palette.accent"` references resolve against the current palette at render time.

---

### Testing Strategy for Layer 3

- Unit test each effect generator: feed it synthetic time sequences and assert the output channels are correct.
- Unit test the blending system: feed it overlapping effects with known priorities and verify the merge output.
- Integration test: feed Layer 2 cue streams into Layer 3 and capture the abstract output. Visualize it as a timeline heatmap (position on Y axis, time on X axis, color = output color, brightness = output brightness). This is your primary QA tool for tuning.
- Build a "preview mode" early: a simple 2D grid visualization (in the browser, using the existing HTML5 canvas) that renders the abstract output in real time without any hardware. This is essential for development and for users who want to preview before connecting hardware.

---

## Layer 4 — Output & Hardware (Abstract → Physical)

### Purpose

Translate abstract channel values from Layer 3 into hardware-specific control signals, and provide venue/fixture configuration.

This layer has two distinct sub-components.

---

### Sub-layer 4A — Venue Configuration

A **venue file** (JSON/YAML) describes the physical setup:

```yaml
venue:
  name: "My Setup"

  fixture_definitions:
    - id: "generic_rgb_par"
      channels:
        - { name: "red", type: "color_r", range: [0, 255] }
        - { name: "green", type: "color_g", range: [0, 255] }
        - { name: "blue", type: "color_b", range: [0, 255] }
        - { name: "dimmer", type: "brightness", range: [0, 255] }
      channel_count: 4

    - id: "moving_head_spot"
      channels:
        - { name: "pan", type: "position_x", range: [0, 255] }         # coarse
        - { name: "pan_fine", type: "position_x_fine", range: [0, 255] }
        - { name: "tilt", type: "position_y", range: [0, 255] }
        - { name: "tilt_fine", type: "position_y_fine", range: [0, 255] }
        - { name: "dimmer", type: "brightness", range: [0, 255] }
        - { name: "red", type: "color_r", range: [0, 255] }
        - { name: "green", type: "color_g", range: [0, 255] }
        - { name: "blue", type: "color_b", range: [0, 255] }
        - { name: "strobe", type: "strobe_rate", range: [0, 255] }
      channel_count: 9

  fixtures:
    - name: "Par 1"
      definition: "generic_rgb_par"
      dmx_universe: 1
      dmx_start_address: 1
      position: { x: 0.0, y: 0.0 }    # normalized position in the venue (0.0–1.0)
      groups: ["pars_all", "pars_left"]

    - name: "Par 2"
      definition: "generic_rgb_par"
      dmx_universe: 1
      dmx_start_address: 5
      position: { x: 0.25, y: 0.0 }
      groups: ["pars_all", "pars_left"]

    # ... more fixtures ...

  groups:
    - name: "pars_all"
      description: "All par cans"
    - name: "pars_left"
      description: "Left-side par cans"
    - name: "movers"
      description: "All moving heads"
    - name: "lasers"
      description: "All laser fixtures"
    - name: "visuals"
      description: "Video output targets"
```

Key concepts:
- **Fixture definitions** are reusable templates that describe a fixture type's DMX channel layout and map each channel to an abstract channel type. This is the translation layer between Layer 3's abstract channels and DMX byte values.
- **Fixture instances** reference a definition and add physical details: DMX address, spatial position, group membership.
- **Groups** are named sets referenced by Layer 3's routing table. The user defines groups based on physical layout ("pars_left," "pars_right," "pars_all," "movers," "lasers").
- **Position** (normalized 0.0–1.0) is what Layer 3's `position` channel maps to. When a chase effect sweeps from 0.0 to 1.0, it activates fixtures in order of their position value. This is how spatial effects work without Layer 3 knowing anything about physical locations.

**Fixture definition libraries:** Ship a library of common fixture profiles (generic RGB par, generic RGBW par, common moving heads, common laser controllers). Users add their own for specific hardware.

---

### Sub-layer 4B — Output Protocol Adapters

Each adapter takes the per-fixture abstract channel values and translates them to a specific protocol:

**DMX512 / Art-Net / sACN (lights and DMX-controlled lasers):**
- The fixture profile maps abstract channels to DMX channel offsets.
- The adapter packs all fixture values into DMX universe frames (512 bytes each) and sends them at ~44Hz (DMX refresh rate).
- Use OLA (Open Lighting Architecture) as the backend — it handles Art-Net, sACN, USB-DMX dongles (like the Enttec DMXIS or OpenDMX), and many more interfaces. OLA runs as a daemon on the Mac and exposes a simple API. This avoids writing protocol-level code.
- Alternative: python-sacn or python-artnet for a lighter-weight solution if OLA is too heavy.

**ILDA (lasers, stretch goal):**
- For ILDA-native laser controllers, the adapter translates position/color into ILDA point streams.
- Most affordable DJ lasers are DMX-controlled, not ILDA. Start with DMX laser support (many laser fixtures accept DMX for pattern selection, color, position, speed). ILDA is a later optimization.

**OSC (visuals — Resolume, TouchDesigner, VDMX, etc.):**
- The adapter sends OSC messages to visual software running on the same machine or network.
- OSC is the standard protocol for programmatic control of visual software.
- Map abstract channels to OSC addresses. Example: `/visuals/clip/trigger`, `/visuals/effect/intensity`, `/visuals/color/r`.
- Each visual software has its own OSC address scheme. The adapter's configuration maps SCUE's abstract channels to the target software's specific addresses.

**MIDI (alternative for visuals and some lighting):**
- Some visual software and lighting controllers prefer MIDI.
- The adapter translates abstract channel values to MIDI CC messages or note-on/off.
- Lower priority than OSC but useful as a fallback.

**The important design constraint:** Layer 3 writes to abstract channels. It never knows which protocol adapter will consume the output. Adding a new protocol adapter requires zero changes to Layers 1–3.

---

### Sub-layer 4C — User Override Interface

The user needs to intervene in real time during a live set. This is a UI concern, but the underlying architecture must support it.

Capabilities:
- **Mute/unmute routes:** Temporarily disable a routing table entry (e.g., "stop the lasers from reacting to arps"). This is a boolean toggle on each route.
- **Solo a group:** Only this group outputs; everything else goes dark. Useful for dramatic moments.
- **Override effect parameters:** Temporarily force an effect's speed, color, or intensity to a manual value. When released, it snaps back to the cue-driven value.
- **Trigger manual cues:** Fire a one-shot effect (e.g., a strobe burst) from a button, pad, or MIDI controller.
- **Switch palette:** Swap to a different color palette on the fly.
- **Blackout / full-on:** Master brightness override.

These overrides are injected into the blending system (Sub-layer 3C) at the highest priority level, so they always win over automated cues.

The UI for this can be a browser-based control surface (grid of buttons and faders) accessible on a tablet or phone, or it can accept MIDI input from a physical controller. Both should be supported.

---

### Testing Strategy for Layer 4

- Unit test fixture profile translation: given abstract channel values and a fixture definition, assert the correct DMX byte values.
- Unit test protocol adapters against mock receivers: send Art-Net/sACN/OSC packets to a local listener and verify content.
- Build a "virtual venue" visualizer: a 2D (or simple 3D) browser-based rendering of the fixture layout that displays the output in real time. Each fixture is a colored dot/bar. This is the primary testing tool and also a useful feature for users (preview mode).
- Test with real hardware only after virtual venue tests pass. Start with a single DMX universe and a few par cans.

---

## Build Order & Milestones

This ordering ensures each milestone is testable and demoable before moving on.

### Milestone 1 — Analysis Pipeline (Layer 1A, Tier 1 only)

Deliverable: Given an audio file, produce labeled sections with bar counts and phrase irregularity flags. Store in database. Visualize with existing RGB waveform tool.

Test: Analyze 5 test tracks. Manually verify section labels against the actual track. ≥80% section boundary accuracy within 1 bar.

### Milestone 2 — Live Cursor + Pioneer Enrichment (Layer 1B)

Deliverable: Connect to Pioneer hardware (or mock UDP stream). Display a real-time cursor on the waveform visualization showing current section, progress, and next section. On first track load, run the Pioneer enrichment pass — swap in Pioneer beatgrid/BPM/key, re-align sections, log divergences.

Test: Play a pre-analyzed track on a CDJ (or mock the packets). Verify the cursor stays in sync. Adjust tempo ±8% and verify events still align. Verify the divergence log captures differences between SCUE's offline analysis and Pioneer's metadata. Verify the cursor reads from the enriched analysis after enrichment runs.

### Milestone 3 — Cue Stream (Layer 2, section cues only)

Deliverable: Generate `section_change`, `section_anticipation`, `section_progress`, and `beat` cues from the live cursor. Display them as a real-time text log in the browser.

Test: Play a track and verify section cues fire at the correct times. Verify anticipation cues fire N beats before transitions.

### Milestone 4 — Basic Effect Engine (Layer 3A + 3B, minimal)

Deliverable: Implement `static`, `pulse`, and `chase` effects. Build a routing table that maps `beat` → `pulse` and `section_change` → color change. Output abstract channel values.

Test: Feed synthetic cue streams and verify output values. Build the 2D preview grid.

### Milestone 5 — DMX Output (Layer 4A + 4B, DMX only)

Deliverable: Define a simple venue (a few par cans). Translate abstract output to DMX via OLA or python-sacn. Light up real fixtures.

Test: Verify colors match. Verify chase direction matches fixture position order. Verify timing feels right at different BPMs.

### Milestone 6 — End-to-End Demo

Deliverable: Play a pre-analyzed track on Pioneer hardware. SCUE tracks playback, generates section/beat cues, runs effects, and controls lights in real time.

Test: DJ a short set (2–3 tracks) and evaluate whether the light show is coherent and responsive. This is a subjective evaluation — invite a friend to watch.

### Milestone 7 — Event Detection (Layer 1A, Tier 2)

Deliverable: Add kick, snare, riser, faller, stab, and arp detection to the analysis pipeline.

Test: Verify events against hand-labeled tracks.

### Milestone 8 — Full Cue Vocabulary

Deliverable: Generate all cue types from Layer 2. Add more effects to the library. Build richer routing presets.

### Milestone 9 — OSC Visual Output (Layer 4B)

Deliverable: Add OSC adapter. Control Resolume or TouchDesigner from SCUE.

### Milestone 10 — Real-Time User Override UI (Layer 4C)

Deliverable: Browser-based control surface with route muting, manual cue triggers, palette switching, and master faders.

### Milestone 11 — Polish & Tier 3 Features

Deliverable: Add mood/palette engine, Tier 3 track features, MIDI input for physical control, fixture definition library, etc.

---

## Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Backend / orchestration | **FastAPI (Python)** | Already in use in POC. Good async support for WebSockets and real-time event loops. |
| Audio analysis | **librosa, allin1-mlx** | Already proven in POC. |
| Database | **SQLite** | Single-machine app. No need for a server DB. Keyed by track fingerprint. |
| Real-time event bus | **In-process async queues (asyncio.Queue)** | All layers run on the same machine. No need for a message broker. If performance demands it later, consider ZeroMQ. |
| Browser UI | **Vanilla HTML/JS + Canvas, or lightweight framework (Svelte/React)** | The existing POC uses plain HTML5 canvas. Stick with it until complexity demands a framework. WebSocket connection to FastAPI for real-time updates. |
| DMX output | **OLA or python-sacn** | OLA if you need multi-protocol support. python-sacn if you want minimal dependencies. |
| OSC output | **python-osc** | Lightweight, well-maintained. |
| Configuration format | **YAML** | Human-readable, supports comments. JSON as alternative. |
| Effect definitions | **YAML files loaded at startup** | Declarative. No code changes to add effects. |
| Fixture profiles | **YAML files** | Same pattern. Ship a library, users extend it. |

---

## Architecture Diagram (Conceptual)

```
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 1                                 │
│                                                              │
│  ┌────────────────────┐     ┌───────────────────────┐        │
│  │  1A: Offline        │     │  1B: Live Tracking     │       │
│  │  Track Analysis     │     │  (Pro DJ Link UDP)     │       │
│  │                     │     │                        │       │
│  │  Audio → TrackAnalysis   │  Packets → PlaybackState│       │
│  │  (stored in SQLite) │────▶│  + TrackCursor         │       │
│  └────────────────────┘     └──────────┬────────────┘        │
│                                        │                     │
└────────────────────────────────────────┼─────────────────────┘
                                         │ TrackCursor
                                         ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 2                                 │
│               Cue Generation                                 │
│                                                              │
│        TrackCursor → [CueEvent stream]                       │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │ CueEvent stream
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 3                                 │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐  │
│  │ 3A:      │  │ 3B:          │  │ 3C:      │  │ 3D:     │  │
│  │ Effect   │  │ Routing      │  │ Blend &  │  │ Palette │  │
│  │ Library  │  │ Table        │  │ Priority │  │ & Mood  │  │
│  │          │◀─│              │─▶│          │  │ Engine  │  │
│  └──────────┘  └──────────────┘  └─────┬────┘  └─────────┘  │
│                      ▲                 │                     │
│                      │ user override   │                     │
│                 (Layer 4C)             │                     │
│                                        │ abstract channels   │
└────────────────────────────────────────┼─────────────────────┘
                                         │ per-fixture {brightness,
                                         │  color, position, ...}
                                         ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 4                                 │
│                                                              │
│  ┌──────────────┐    ┌──────────────────────────────────┐    │
│  │ 4A: Venue    │    │ 4B: Protocol Adapters             │   │
│  │ Config       │───▶│                                   │   │
│  │ (fixtures,   │    │  DMX/Art-Net/sACN → lights        │   │
│  │  groups,     │    │  OSC → visual software             │  │
│  │  profiles)   │    │  MIDI → controllers                │  │
│  └──────────────┘    │  ILDA → lasers (stretch)           │  │
│                      └──────────────────────────────────┘    │
│  ┌────────────────────────────────────────────┐              │
│  │ 4C: User Override UI (browser / MIDI in)   │              │
│  └────────────────────────────────────────────┘              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## File/Directory Structure (Suggested)

```
scue/
├── README.md
├── config/
│   ├── venues/                    # Venue configuration files
│   │   └── my_setup.yaml
│   ├── routing/                   # Routing table presets
│   │   ├── edm_club.yaml
│   │   └── melodic.yaml
│   ├── effects/                   # Effect definitions
│   │   ├── pulse.yaml
│   │   ├── chase.yaml
│   │   └── ...
│   ├── fixtures/                  # Fixture profile library
│   │   ├── generic_rgb_par.yaml
│   │   ├── generic_rgbw_par.yaml
│   │   └── ...
│   └── palettes/                  # Color palette presets
│       ├── warm_euphoric.yaml
│       └── dark_minimal.yaml
├── scue/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point
│   ├── layer1/
│   │   ├── __init__.py
│   │   ├── analysis.py            # Offline track analysis (1A)
│   │   ├── enrichment.py          # Pioneer enrichment pass (beatgrid swap, re-alignment)
│   │   ├── divergence.py          # DivergenceRecord logging & query
│   │   ├── detectors/             # Individual event detectors
│   │   │   ├── sections.py        # ML boundary detection + 8-bar snapping
│   │   │   ├── flow_model.py      # EDM arrangement pattern scorer/labeler
│   │   │   ├── percussion.py
│   │   │   ├── melodic.py
│   │   │   ├── effects.py
│   │   │   └── features.py
│   │   ├── models.py              # TrackAnalysis, Section, Event, DivergenceRecord dataclasses
│   │   ├── db.py                  # SQLite storage (versioned analyses + divergence log)
│   │   ├── tracking.py            # Live playback tracking (1B)
│   │   ├── prodjlink.py           # Pro DJ Link UDP parser
│   │   └── cursor.py              # TrackCursor logic (reads enriched analysis if available)
│   ├── layer2/
│   │   ├── __init__.py
│   │   ├── cue_engine.py          # Main cue generation loop
│   │   ├── cue_types.py           # CueEvent dataclass + taxonomy
│   │   └── generators/            # Per-cue-type generator functions
│   │       ├── section_cues.py
│   │       ├── rhythmic_cues.py
│   │       ├── melodic_cues.py
│   │       └── ambient_cues.py
│   ├── layer3/
│   │   ├── __init__.py
│   │   ├── effect_engine.py       # Main effect processing loop
│   │   ├── effects/               # Effect generator implementations
│   │   │   ├── base.py            # Abstract base effect class
│   │   │   ├── pulse.py
│   │   │   ├── chase.py
│   │   │   └── ...
│   │   ├── routing.py             # Routing table loader + matcher
│   │   ├── blender.py             # Priority/blending system
│   │   ├── palette.py             # Palette & mood engine
│   │   └── models.py              # AbstractOutput, ChannelValues dataclasses
│   ├── layer4/
│   │   ├── __init__.py
│   │   ├── venue.py               # Venue config loader
│   │   ├── fixture_profile.py     # Fixture definition + channel mapping
│   │   ├── output_manager.py      # Coordinates all adapters
│   │   ├── adapters/
│   │   │   ├── base.py            # Abstract adapter interface
│   │   │   ├── dmx.py             # DMX/Art-Net/sACN via OLA or python-sacn
│   │   │   ├── osc.py             # OSC output
│   │   │   └── midi.py            # MIDI output
│   │   └── override.py            # User override state management
│   └── ui/
│       ├── static/                # Browser UI files
│       └── websocket.py           # WebSocket handlers for UI
├── tests/
│   ├── fixtures/                  # Test audio files, packet captures, etc.
│   ├── test_layer1/
│   ├── test_layer2/
│   ├── test_layer3/
│   └── test_layer4/
└── tools/
    ├── analyze_track.py           # CLI: analyze a track
    ├── mock_prodjlink.py          # CLI: replay captured DJ Link packets
    ├── cue_visualizer.py          # CLI/web: visualize cue stream
    └── venue_preview.py           # CLI/web: 2D venue preview
```

---

## Open Questions (Decide Before Building)

1. **Tick rate for the real-time loop.** Beat-synchronized ticks (variable rate depending on BPM) vs. fixed-rate ticks (e.g., 40Hz / every 25ms)? Beat-synced is musically natural but complicates the timer logic. Fixed-rate is simpler and provides smoother output for continuous effects. Recommendation: fixed-rate main loop (40Hz) with beat events injected from the cursor. Effects that need beat sync reference the beat grid, not the tick rate.

2. **Multi-deck blending.** When two tracks are playing during a transition, does SCUE track both and blend the cue streams? Or does it only follow the "master" deck? Starting with master-only is simpler. Full dual-deck support requires a cue-stream mixer, which is significant complexity.

3. **Latency budget.** What's the acceptable end-to-end latency from a musical event occurring to the light responding? For beat-reactive effects, ≤20ms is ideal, ≤50ms is acceptable, >100ms is noticeable. The main latency sources are: Pro DJ Link packet interval (~50ms), cue generation (should be <1ms), effect computation (should be <1ms), DMX output (depends on interface). Anticipation-based cues (section changes, risers) sidestep this because they fire ahead of time.

4. **Effect authoring.** Are YAML-defined effects sufficient, or will users need to write custom effect code (Python or JS)? Start with YAML + built-in effect types. Add a scripting API later if the built-in types are too limiting.

5. **Visual software integration depth.** Does SCUE just send triggers/parameters to Resolume/TouchDesigner (which run their own effects), or does SCUE generate actual video frames? Recommendation: triggers/parameters only. SCUE controls what visual content plays and modulates its parameters, but the visual software handles rendering. This avoids reinventing a video engine.
