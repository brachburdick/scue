# SCUE — Architecture Plan

## What This App Does

SCUE automates lighting, laser, and visual cues for live DJ sets. It analyzes tracks offline, tracks playback state in real time via the Pro DJ Link protocol (through an embedded beat-link bridge), generates semantic music events, maps those events to abstract effects, and outputs control signals to hardware via standard protocols (DMX/Art-Net, OSC, MIDI). The goal: a single DJ can run a full light/laser/visual show with zero manual cue triggering.

The system is organized into five layers (0–4), a React/TypeScript frontend, and a project-based storage model. Each layer has a defined interface contract, can be tested in isolation, and communicates with adjacent layers through typed data structures.

---

## Guiding Principles

These apply to every layer and every PR.

- **Each layer is a standalone service with a defined interface.** Layers communicate through typed event streams or request/response APIs. No layer reaches into another layer's internals.
- **Test each layer in isolation before integrating.** Every layer must have a mock/stub mode that feeds it synthetic input so it can be developed and verified independently.
- **Prefer declarative configuration over code changes.** Effect definitions, fixture profiles, and routing tables should be data (JSON/YAML), not hardcoded logic. Users and developers should be able to change behavior without touching source code.
- **Fail gracefully under real-time pressure.** Missed deadlines are worse than approximate answers. Every real-time path must have a fallback (e.g., hold last known state, fall back to beat-reactive defaults).
- **Incremental delivery.** Each layer has a Minimum Viable version that proves the concept before investing in the full version.
- **Types are contracts.** Every data structure that crosses a layer boundary or the frontend/backend boundary has a defined type (Python dataclass on the backend, TypeScript interface on the frontend). These types are documented in `docs/CONTRACTS.md`. Changing a type requires updating both sides and their tests.

---

## Layer 0 — Beat-Link Bridge

### Purpose

Provide SCUE with full access to the Pro DJ Link protocol via Deep Symmetry's `beat-link` Java library, managed as an embedded subprocess. The bridge speaks Pro DJ Link natively and streams structured data to SCUE over a local WebSocket.

### Background (ADR-005)

Direct Pro DJ Link UDP parsing (the approach in the original POC) only gets basic data: BPM, pitch, beat position, play state. The full protocol — track metadata, waveform data, cue points, memory points, phrase analysis, hot cues, rekordbox color assignments — requires the deep protocol implementation in `beat-link`. Running beat-link-trigger (the GUI app) as a separate process is unacceptable UX. The solution: embed the `beat-link` library (not the trigger app) as a managed subprocess.

### Why a Subprocess

Three options were considered:

1. **JPype / Py4J (call Java from Python directly):** Technically possible but fragile. JVM-in-process complicates debugging, crash isolation, and memory management. A beat-link bug crashing the JVM would take down the entire SCUE process.
2. **Port beat-link to Python:** beat-link is ~30K lines of Java implementing a complex reverse-engineered protocol. Porting it is years of work and creates a permanent maintenance fork.
3. **Managed subprocess + local WebSocket:** Clean process boundary. If the bridge crashes, SCUE can restart it. Updates are a JAR swap. Communication is typed JSON over WebSocket, which both sides handle natively. **This is the choice.**

### Bridge Architecture

The bridge is a small Java application (single JAR) that:
1. Starts beat-link's `DeviceAnnouncement` listener and `VirtualCdj` instance
2. Connects to the Pro DJ Link network
3. Subscribes to all available data streams (beat, status, metadata, waveform, etc.)
4. Translates each event into a typed JSON message
5. Streams those messages to SCUE over a local WebSocket (e.g., `ws://localhost:17400`)

SCUE's Python side:
1. At startup, checks for JRE availability
2. Launches the bridge JAR as a subprocess (`subprocess.Popen`)
3. Connects to the bridge's WebSocket
4. Monitors the subprocess health (restart on crash, with backoff)
5. Receives typed JSON messages and feeds them into Layer 1

### Bridge Message Types (v1.2.0 — ADR-012)

The bridge emits **5 message types** (real-time data only). Track metadata, beatgrids, waveforms, phrase analysis, and cue points are resolved by the Python side, not the bridge.

**Connection & device discovery:**
```
BridgeMessage {
  type: "device_found" | "device_lost"
  timestamp: float
  player_number: int | null
  payload: {
    device_name: string
    device_number: int
    device_type: "cdj" | "djm" | "rekordbox"
    ip_address: string
    uses_dlp: bool                  # true for DLP hardware (XDJ-AZ, Opus Quad, etc.)
  }
}

BridgeMessage {
  type: "bridge_status"
  timestamp: float
  player_number: null
  payload: {
    connected: bool
    devices_online: int
    version: string                 # "1.2.0"
    network_interface: string | null  # interface name the bridge bound to
    network_address: string | null    # IP address of bound interface
    interface_candidates: list | null # [{ name, address, type, score, selected }]
    warning: string | null            # set when configured interface unavailable
    error: string | null              # set on startup failures
  }
}
```

**Playback state (replaces raw UDP parsing):**
```
BridgeMessage {
  type: "player_status"
  timestamp: float
  player_number: int
  payload: {
    bpm: float                      # effective BPM (0.0 when paused)
    pitch: float                    # pitch adjustment percentage
    beat_within_bar: int            # 1–4
    beat_number: int                # absolute beat count
    playback_state: "playing" | "paused" | "cued" | "searching"
    is_on_air: bool                 # true only when fader up AND master not off
    track_source_player: int
    track_source_slot: "sd" | "usb" | "cd" | "collection"
    track_type: string
    rekordbox_id: int               # DLP track ID (may be unstable between pause/play on XDJ-AZ)
  }
}
```

**Beat events (real-time, high frequency):**
```
BridgeMessage {
  type: "beat"
  player_number: int
  payload: {
    beat_within_bar: int
    bpm: float
    pitch: float
  }
}
```

**Not emitted by bridge (resolved by Python side per ADR-012):**
- `track_metadata` — via rbox (DLP) or future extensions (legacy)
- `beat_grid` — via pyrekordbox ANLZ parser (DLP) or future extensions (legacy)
- `waveform_detail` — via pyrekordbox ANLZ parser (DLP) or future extensions (legacy)
- `phrase_analysis` — via pyrekordbox ANLZ parser (DLP) or future extensions (legacy)
- `cue_points` — via pyrekordbox ANLZ parser (DLP) or future extensions (legacy)

### Synthetic Device Recovery

The Java bridge emits `device_found` once per device during `initBeatLink()`, before the Python WebSocket client may be connected. If the Python side misses these events (late connect, reconnect after crash), `devices` stays empty even though `player_status` data is streaming.

The adapter handles this with `_ensure_device_from_player()`: when a `player_status` message arrives for an unknown player number, a synthetic `DeviceInfo` is created from available data and `on_device_change` is fired. This ensures the devices dict stays populated regardless of `device_found` timing. Future improvement: add state replay to the Java bridge's `BridgeWebSocketServer.onOpen()`.

### Pioneer Traffic vs Bridge Liveness

The bridge manager tracks two separate timestamps:
- `_last_message_time` — updated by ALL WebSocket messages (including `bridge_status` heartbeats). Used for bridge liveness detection.
- `_last_pioneer_message_time` — updated only by Pioneer hardware messages (`device_found`, `player_status`, `beat`, etc.). Used for `is_receiving` in the `pioneer_status` WebSocket message.

This split prevents bridge heartbeats from inflating `is_receiving` when no Pioneer hardware data is actually arriving.

### Decoupling Strategy

The bridge is treated as a replaceable data source. Layer 1 does not import from the bridge directly — it consumes `BridgeMessage` objects through an adapter in `scue/bridge/adapter.py` that normalizes bridge data into Layer 1's internal types. If beat-link is ever replaced, only the adapter changes.

The bridge JAR is stored in `lib/beat-link-bridge.jar` and is NOT compiled from source as part of SCUE's build. It is a pre-built artifact. The bridge's Java source lives in a separate directory (`bridge-java/`) with its own build process (Gradle or Maven). This separation is intentional — the Java side has a different toolchain, different release cadence, and should be updatable by dropping in a new JAR.

### Fallback Behavior

The `FallbackParser` (`bridge/fallback.py`) provides degraded-mode operation using direct UDP parsing. It is wired into `BridgeManager` and activates automatically in two scenarios:

1. **No JRE or JAR:** If the bridge cannot start at all (`no_jre` or `no_jar` state), the manager transitions directly to `fallback` mode.
2. **Repeated crashes:** After `max_crash_before_fallback` consecutive bridge crashes (default: 3), the manager gives up on the bridge and falls back to UDP parsing.

In fallback mode, basic data is available (BPM, beat position, play state) but device discovery, on-air status, and rekordbox_id are unavailable. The `mode` field in `to_status_dict()` reflects `"fallback"` vs `"bridge"`, and the frontend displays a degraded-mode indicator.

### Testing Strategy

- Unit test the adapter: feed mock `BridgeMessage` JSON and verify Layer 1 receives correct internal types.
- Integration test: start the bridge subprocess against a mock Pro DJ Link network (or recorded packet captures replayed via beat-link's built-in tools).
- Health monitoring test: kill the bridge subprocess and verify SCUE detects the failure, falls back gracefully, and restarts the bridge.

### Device Library Plus Workaround (ADR-012)

Pioneer hardware splits into two database formats: **DeviceSQL** (legacy `export.pdb`) used by CDJ-2000NXS2, CDJ-3000, etc., and **Device Library Plus** (encrypted `exportLibrary.db`) used by XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X. The track IDs are different namespaces — beat-link's MetadataFinder returns wrong metadata on DLP hardware.

In v1.2.0, all metadata finders (MetadataFinder, BeatGridFinder, WaveformFinder, CrateDigger, AnalysisTagFinder) are **stripped from the bridge JAR**. The bridge provides real-time playback data only. Metadata is resolved by the Python side:

```
Legacy hardware (CDJ-2000NXS2, CDJ-3000, etc.):
  Future: Python reads export.pdb directly (not yet implemented)

DLP hardware (XDJ-AZ, Opus Quad, etc.):
  USB mount → rbox.OneLibrary(exportLibrary.db) for DB metadata
           → pyrekordbox/anlz_parser for ANLZ files (beat grid, cues, phrases)
           → TrackAnalysis

Both paths produce identical TrackAnalysis records.
Layer 1 and above don't know or care which path was used.
```

The bridge detects DLP hardware from `DeviceAnnouncement` device name and sets `uses_dlp: true` in the `device_found` message. The Python adapter uses this flag to choose the correct metadata resolution path. beat-link provides all real-time playback data (BPM, pitch, beat position, on-air, beat events, rekordbox_id) which works correctly on all hardware.

**Constraint:** The USB must be physically accessible to the SCUE computer (mounted via hub or copied before the set).

---

## Layer 1 — Track Analysis & Live Tracking

### Purpose

Produce a structured, time-indexed description of a track's musical content, and maintain a real-time cursor into that data synchronized with DJ playback.

### Sub-layer 1A — Offline Track Analysis

**Input:** Audio file (WAV, MP3, FLAC, AIFF).
**Output:** A `TrackAnalysis` object stored as a JSON file in the project's `tracks/` directory and indexed in the SQLite cache.

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
- Store results as JSON files in the project's `tracks/` directory, keyed by a track fingerprint (SHA256 audio hash). Re-analysis should be idempotent — same file produces same result.
- Analysis is offline and can be slow. Optimize later.

**Pioneer enrichment pass (runs once per track, first time it's loaded on a deck):**
The first time SCUE sees a track played via Pro DJ Link (through the beat-link bridge), it receives Pioneer/rekordbox metadata including BPM, beatgrid, key, and (if available) rekordbox's own phrase analysis. SCUE should use this data to refine the offline analysis:
- **Beatgrid:** Replace the librosa-derived beatgrid with the Pioneer beatgrid. The DJ has likely hand-corrected this in rekordbox — it is more reliable. Re-align all Tier 1 section boundaries and Tier 2 event timestamps to the Pioneer grid. Store the updated analysis as a new version (do not overwrite the original — keep both).
- **BPM:** Use Pioneer's BPM as the authoritative base BPM for tempo scaling calculations.
- **Key:** Use Pioneer's key detection as the reference key.
- **Rekordbox phrase analysis (if available):** Some Pioneer hardware exposes rekordbox's own phrase/section data via beat-link. If available, compare it against SCUE's section labels. Where they agree, increase SCUE's confidence score. Where they disagree, log the divergence (see below).
- **Divergence log:** For every field where SCUE's analysis differs from Pioneer/rekordbox data, log a `DivergenceRecord`:
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

**Input:** Normalized bridge data from Layer 0 (beat-link bridge adapter).
**Output:** A `PlaybackState` object updated in real time, a `TrackCursor` per active deck, and a `DeckMix` that describes the current mix state (which decks are active and their relative weights).

Layer 1B maintains a TrackCursor for **every active deck simultaneously**, not just the master. The bridge streams per-player data, and Layer 1B maintains a cursor for each player that has a track loaded and is playing. This is the data path that enables multi-deck blending downstream — even though Layer 2 initially only uses the master deck's cursor, the infrastructure tracks all decks from day one.

**Pioneer as metadata authority.** The beat-link bridge provides beatgrid, BPM, key, phrase data, waveforms, cue points, and track metadata. These are treated as the primary source of truth for timing and musical metadata — they have been verified or corrected by the DJ in rekordbox. SCUE's own offline analysis (librosa-derived beatgrid, BPM, key) serves as the initial working model and as a fallback when bridge data is unavailable, but is superseded by bridge data once received.

When a track is first loaded on a deck and bridge metadata arrives:
1. Trigger the **Pioneer enrichment pass** described in Sub-layer 1A. This updates the stored `TrackAnalysis` with the Pioneer beatgrid, BPM, and key, re-aligns section boundaries and events, and logs any divergences.
2. The `TrackCursor` always reads from the enriched (Pioneer-aligned) analysis if available, falling back to the raw offline analysis if the enrichment pass hasn't run yet.

The `PlaybackState` contains:
- Per deck: current track ID, BPM, pitch/tempo adjustment, beat-within-bar (1–4), playback position (time), play/pause/cue state, is-on-air status.
- Master deck identification (which deck is live).
- Crossfader position (if available from the protocol).

The `TrackCursor` provides (one instance per active deck):
- `player_number`: which physical deck this cursor tracks (1, 2, 3, 4).
- `current_section`: which section is playing right now, plus progress through it (0.0–1.0).
- `next_section`: what's coming next, and time until transition.
- `upcoming_events`: a sliding window of the next N events from the Tier 2 event list, time-adjusted for current tempo.
- `current_features`: interpolated Tier 3 features for the current position.

The `DeckMix` describes how multiple decks should be blended:
```
DeckMix {
  cursors: list[WeightedCursor]     # one per active deck
}

WeightedCursor {
  cursor: TrackCursor
  weight: float                     # 0.0–1.0, how much this deck contributes
  source: "on_air" | "crossfader" | "manual"  # how the weight was determined
}
```

**Weight calculation (ADR-006):**
- **Phase 1 (master-only):** The deck with `is_on_air == true` gets `weight: 1.0`. All other decks get `weight: 0.0`. If multiple decks are on-air (transition in progress), the most recently on-air deck gets 1.0 and others get 0.0. This is the simplest behavior and the starting point.
- **Phase 2 (crossfade blend):** When the DJM reports crossfader position or both decks are on-air simultaneously, weights are derived from the mix state. If crossfader data is available, weights are proportional to crossfader position (e.g., crossfader at 30% → deck A weight 0.7, deck B weight 0.3). If only on-air flags are available (no crossfader data), both on-air decks get equal weight (0.5/0.5) during the overlap, transitioning to 1.0/0.0 when one goes off-air.
- **Phase 3 (manual/advanced):** User can manually assign weights per deck from the override UI (Layer 4C). This enables creative routing like "deck A drives lights, deck B drives lasers."

The weight calculation strategy is selected in project config (`settings.mix_mode: "master_only" | "crossfade" | "manual"`). Default is `"master_only"`.

**Tempo adaptation:** The event timestamps from offline analysis are at the track's original BPM. The cursor must scale all timestamps by `(original_bpm / current_bpm)` to account for the DJ's pitch fader. This is a simple linear scaling — apply it everywhere timestamps are read.

**Effect/filter resilience:** The cursor tracks position, not audio content. It does not listen to the audio output of the mixer. This means mixer effects (reverb, delay, filter sweeps) and EQ changes do not confuse the tracking. The cursor simply follows the playback position reported by the bridge. If effects are applied, the cues fire as if the clean track were playing — which is correct behavior, since the DJ is adding effects on top intentionally.

**Key adaptation (stretch goal):** If the DJ uses key sync or pitch-shifts significantly, note the key offset and pass it downstream so Layer 3 can adjust color mappings if desired.

**Testing strategy:**
- Mock bridge messages with recorded data. Play back captured sessions and verify the cursor tracks correctly.
- Test tempo changes: capture a session where the DJ pitches a track up/down and verify event timestamps scale correctly.
- Test deck switching: verify the cursor follows the master/active deck.
- Test enrichment pass: analyze a track offline, then feed bridge metadata for the same track. Verify that the stored `TrackAnalysis` is updated with Pioneer beatgrid/BPM/key, section boundaries are re-aligned, and a `DivergenceRecord` is logged for every field that differed.
- Test fallback: verify the cursor works correctly with an un-enriched analysis (bridge data not yet available).

---

## Layer 2 — Cue Generation (Music → Semantics)

### Purpose

Transform the `DeckMix` (one or more weighted TrackCursors) into a single blended stream of **semantic cue events** that describe musical meaning, not hardware instructions. This layer knows everything about music and nothing about lights.

### Multi-Deck Input (ADR-006)

Layer 2's entry point receives a `DeckMix` — a list of `WeightedCursor` objects, one per active deck. Each cursor carries a `weight` (0.0–1.0) indicating how much that deck contributes to the output cue stream.

The cue engine runs each cursor through the full cue generation pipeline independently, producing a per-deck cue stream. Then a **cue mixer** combines them:

- **Instantaneous cues** (kick, snare, stab, beat, section_change, impact): Each cue's `intensity` is scaled by the deck's weight. A kick at velocity 0.8 from a deck at weight 0.5 produces a kick cue with intensity 0.4. Cues with intensity below a configurable threshold (default 0.1) are dropped — this prevents ghost cues from a nearly-silent outgoing deck.
- **Continuous cues** (riser, faller, sweep, section_progress, energy_level): Values are interpolated between decks weighted by their mix weights. If deck A (weight 0.7) has energy 0.9 and deck B (weight 0.3) has energy 0.4, the blended energy_level cue reports `0.7 * 0.9 + 0.3 * 0.4 = 0.75`.
- **Section cues** (section_change, section_anticipation): These fire from whichever deck has the higher weight at the moment of the transition. If both decks change sections simultaneously (rare), the higher-weighted deck wins. This prevents confusing double-transitions during a blend.
- **Mood cues** (mood_shift): During a blend between two tracks with different moods, the blended mood interpolates toward the incoming track's mood proportional to weight. This lets the palette engine smoothly transition colors during a DJ mix.

**Phase 1 (master-only):** The DeckMix contains one cursor at weight 1.0 (the master deck) and all others at weight 0.0. The cue mixer effectively passes through the master's cues unchanged. No blending logic runs. This is the starting implementation.

**Phase 2 (crossfade blend):** The DeckMix contains two cursors with weights that sum to ~1.0, changing over the duration of the DJ's transition. The cue mixer blends as described above. The light show smoothly transitions between tracks in sync with the audio mix.

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

- The cue engine's entry point signature is: `(DeckMix) → [CueEvent]`. Internally, it calls per-cursor generators and then the cue mixer.
- The per-cursor generation is a pure function: `(TrackCursor) → [CueEvent]`. No side effects, no state beyond the current input. This makes it trivially testable in isolation.
- The cue mixer is also a pure function: `(list[tuple[list[CueEvent], float]]) → [CueEvent]` (list of per-deck cue streams with their weights → merged stream).
- The `section_anticipation` cue requires looking ahead in the `TrackAnalysis` data, which the `TrackCursor.next_section` already provides.
- The `impact` cue is a heuristic composite: fire it when `section_change` to a `drop` coincides with a high-velocity `kick` and high `track_energy`. Tune the threshold by ear.

### Testing Strategy

- **Single-deck tests:** Feed a single TrackCursor (wrapped in a DeckMix at weight 1.0) through Layer 2 and snapshot the cue output. Validate timing against hand-annotated files. This tests the per-cursor generation pipeline.
- **Multi-deck blend tests:** Feed two TrackCursors with known content at varying weights (1.0/0.0, 0.5/0.5, 0.0/1.0) and verify that cue intensities scale correctly, continuous values interpolate, and section cues come from the dominant deck.
- **Transition simulation tests:** Feed a DeckMix where weights smoothly shift from deck A to deck B over N seconds. Verify there are no duplicate section_change cues, no intensity spikes, and the blend feels smooth.
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
- Build a "preview mode" early: a simple 2D grid visualization (in the browser) that renders the abstract output in real time without any hardware. This is essential for development and for users who want to preview before connecting hardware.

---

## Layer 4 — Output & Hardware (Abstract → Physical)

### Purpose

Translate abstract channel values from Layer 3 into hardware-specific control signals, and provide venue/fixture configuration.

This layer has three sub-components.

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
        - { name: "pan", type: "position_x", range: [0, 255] }
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
      position: { x: 0.0, y: 0.0 }
      groups: ["pars_all", "pars_left"]

    - name: "Par 2"
      definition: "generic_rgb_par"
      dmx_universe: 1
      dmx_start_address: 5
      position: { x: 0.25, y: 0.0 }
      groups: ["pars_all", "pars_left"]

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
- **Fixture definitions** are reusable templates that describe a fixture type's DMX channel layout and map each channel to an abstract channel type.
- **Fixture instances** reference a definition and add physical details: DMX address, spatial position, group membership.
- **Groups** are named sets referenced by Layer 3's routing table. The user defines groups based on physical layout.
- **Position** (normalized 0.0–1.0) is what Layer 3's `position` channel maps to. When a chase effect sweeps from 0.0 to 1.0, it activates fixtures in order of their position value.

**Fixture definition libraries:** Ship a library of common fixture profiles. Users add their own for specific hardware.

---

### Sub-layer 4B — Output Protocol Adapters

Each adapter takes the per-fixture abstract channel values and translates them to a specific protocol:

**DMX512 / Art-Net / sACN:** The fixture profile maps abstract channels to DMX channel offsets. The adapter packs all fixture values into DMX universe frames and sends at ~44Hz. Use OLA (Open Lighting Architecture) or python-sacn.

**ILDA (lasers, stretch goal):** For ILDA-native laser controllers. Start with DMX laser support first.

**OSC (visuals — Resolume, TouchDesigner, VDMX, etc.):** Send OSC messages to visual software. Map abstract channels to OSC addresses per target software configuration.

**MIDI:** Translate abstract channel values to MIDI CC messages or note-on/off. Lower priority than OSC.

**The important design constraint:** Layer 3 writes to abstract channels. It never knows which protocol adapter will consume the output. Adding a new protocol adapter requires zero changes to Layers 0–3.

---

### Sub-layer 4C — User Override Interface

Capabilities:
- **Mute/unmute routes:** Temporarily disable a routing table entry.
- **Solo a group:** Only this group outputs; everything else goes dark.
- **Override effect parameters:** Temporarily force an effect's speed, color, or intensity to a manual value.
- **Trigger manual cues:** Fire a one-shot effect from a button, pad, or MIDI controller.
- **Switch palette:** Swap to a different color palette on the fly.
- **Blackout / full-on:** Master brightness override.

These overrides are injected into the blending system (Sub-layer 3C) at the highest priority level, so they always win over automated cues. The UI for this is a browser-based control surface accessible on a tablet/phone, plus MIDI input from a physical controller.

---

### Testing Strategy for Layer 4

- Unit test fixture profile translation: given abstract channel values and a fixture definition, assert the correct DMX byte values.
- Unit test protocol adapters against mock receivers.
- Build a "virtual venue" visualizer: a 2D browser-based rendering of the fixture layout. This is the primary testing tool and a useful feature for users.
- Test with real hardware only after virtual venue tests pass.

---

## Project & Storage Model

### The Hybrid Model

**Project folders are the source of truth. SQLite is a derived cache.**

A SCUE project is a folder on disk:

```
my-dj-project/
├── project.yaml                     # Project metadata and settings
├── tracks/
│   ├── a1b2c3d4.json               # Track analysis (keyed by audio fingerprint)
│   ├── e5f6g7h8.json
│   └── ...
├── logs/
│   ├── scue.log                    # Rotating log file
│   └── errors.log                  # Persistent error log
└── cache/
    └── scue.db                     # SQLite index (derived, rebuildable)
```

**`project.yaml`:**
```yaml
project:
  name: "My DJ Library"
  created: "2025-03-15T00:00:00Z"
  version: 1

settings:
  analysis:
    max_parallel: 4
  bridge:
    port: 17400
  ui:
    theme: "dark"
```

**Track analysis files (`tracks/{fingerprint}.json`):** Each file contains the complete `TrackAnalysis` for one track. The filename is the SHA256 audio fingerprint. Copying analysis files between machines or projects Just Works. The JSON file is the authoritative record; SQLite is rebuilt from it.

**SQLite cache (`cache/scue.db`):** An index for fast queries (table view, search, filtering). Contains flattened track data (title, artist, BPM, key, analysis status, section summary). Does NOT contain full analysis detail. Rebuilt from `tracks/` directory on project open if stale, or on demand. If deleted, nothing is lost.

**Log storage:** Two tiers:
1. **In-memory ring buffer (for console).** Most recent 500 entries, served to frontend via WebSocket. FIFO, no disk I/O.
2. **Rotating log files (for history).** `logs/scue.log` via `RotatingFileHandler` (10MB, 3 rotations). `logs/errors.log` (persistent, not rotated). The Logs page reads from these files via backend endpoint with pagination and filtering.

---

## Frontend Architecture

### Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Language | **TypeScript (strict mode)** | Type safety, better AI-assisted coding, catches contract violations at compile time. |
| Framework | **React 19** | Brach's familiarity. Performance adequate for state display at 60fps. |
| Styling | **Tailwind CSS** | Utility-first, fast iteration, consistent design system. |
| Build tool | **Vite** | Fast HMR, first-class TS/React support. |
| State management | **Zustand** | Minimal boilerplate, TS-native, independent stores per concern. |
| Data fetching | **TanStack Query** | Handles caching, loading states, error states, refetching for REST endpoints. |
| Real-time data | **Native WebSocket + Zustand** | WS updates flow into Zustand stores. |
| Tables | **TanStack Table** | Headless, TS-first, virtualization for large libraries. |
| Desktop wrapper (future) | **Tauri** (not Electron) | ~10MB vs Electron's ~150MB+. Reuses exact same web frontend. Add when needed. |

### Frontend/Backend Communication

**REST API (HTTP):** For CRUD and non-real-time requests.
- `GET /api/tracks` — list all tracks in current project
- `GET /api/tracks/{id}` — get track details + analysis
- `POST /api/tracks/analyze` — upload and analyze tracks (returns job ID)
- `GET /api/tracks/analyze/{job_id}` — poll analysis job status
- `DELETE /api/tracks/{id}` — remove track from project
- `GET /api/projects` — list available projects
- `POST /api/projects` — create new project
- `PUT /api/projects/active` — switch active project
- `GET /api/bridge/status` — beat-link bridge health
- `GET /api/logs` — recent log entries (paginated)

**WebSocket (`ws://localhost:8000/ws`):** For real-time streaming.
```typescript
type WSMessage =
  | { type: "playback_state"; data: PlaybackState }
  | { type: "analysis_progress"; data: { track_id: string; progress: number; status: "analyzing" | "complete" | "error" } }
  | { type: "bridge_status"; data: BridgeStatus }
  | { type: "log_entry"; data: LogEntry }
  | { type: "alert"; data: { level: "info" | "warning" | "error"; message: string } }
```

### Application Shell & Layout

```
┌─────────────────────────────────────────────────────┐
│  Top bar (app name, project selector, bridge status) │
├────────────┬────────────────────────────────────────┤
│            │                                        │
│  Sidebar   │         Content Area                   │
│  (nav)     │         (routed pages)                 │
│            │                                        │
│  data      │                                        │
│    db      │                                        │
│    blt     │                                        │
│    enrich  │                                        │
│  logs      │                                        │
│  network   │                                        │
│            ├────────────────────────────────────────┤
│            │  Console (collapsible)                  │
│  [console] │  log stream, errors, status messages    │
└────────────┴────────────────────────────────────────┘
```

### Page Breakdown

**Tracks page (`/data/db`):** Primary data management view. Components: `TrackTable` (TanStack Table, sortable/filterable/virtualized), `TrackToolbar` (Choose Folder, Upload & Analyze, bulk actions), `AnalysisProgressBar` (appears during analysis, shows "Processing: 3/12"), `TrackRow` (states: normal, pending/spinner, error/red, selected/checkbox). Upload flow: file picker → `POST /api/tracks/analyze` → backend adds pending rows → WebSocket streams progress → rows update in real time → progress bar disappears on completion. Duplicate detection via audio fingerprint with confirmation dialog.

**BLT page (`/data/blt`):** Bridge status, device list, per-player detail (current track, BPM, pitch, beat position, on-air), bridge controls (start/stop/restart).

**Enrichment page (`/data/enrichment`):** Enrichment queue, enrichment history, divergence table (aggregated, filterable by field type).

**Logs page (`/logs`):** Historical log viewer with pagination, level/source filtering, text search.

**Network page (`/network`):** Network interface list, Pro DJ Link status, bridge WebSocket status, connection test button.

### Frontend Guiding Principles

1. **Types are the contract.** Every data structure crossing the FE/BE boundary has a TypeScript type in `src/types/`. These mirror Python dataclasses from `docs/CONTRACTS.md`.
2. **Stores are independent silos.** Each Zustand store manages one concern. No store imports another store.
3. **Pages are thin (<100 lines).** Compose feature components and connect to stores/hooks.
4. **Components are dumb.** Receive data via props, emit via callbacks. Feature components may use hooks; shared components are purely presentational.
5. **WebSocket is fire-and-forget.** Managed in `api/ws.ts`, dispatches to Zustand stores. Components never touch the WebSocket directly.
6. **No premature drag-and-drop optimization.** Keep layout components (Shell, Sidebar, Console) with explicit size props, not hardcoded CSS. Use `dnd-kit` later when editor mode is built.

---

## Build Order & Milestones

### Backend Milestones

#### Milestone 0 — Beat-Link Bridge (Layer 0)

Deliverable: Java bridge JAR that connects to Pro DJ Link network and streams typed JSON messages over local WebSocket. Python bridge manager that starts/stops/monitors the subprocess. Adapter that normalizes messages into Layer 1 types. Fallback to basic UDP parsing if bridge unavailable.

Test: Start bridge with CDJs on network (or mock). Verify device discovery, playback state, track metadata, and beat grid messages arrive. Kill bridge process → verify SCUE detects failure, falls back, and restarts.

#### Milestone 1 — Analysis Pipeline (Layer 1A, Tier 1 only)

Deliverable: Given an audio file, produce labeled sections with bar counts and phrase irregularity flags. Store as JSON in project folder. Index in SQLite cache. Visualize with existing RGB waveform tool.

Test: Analyze 5 test tracks. Manually verify section labels against the actual track. ≥80% section boundary accuracy within 1 bar.

#### Milestone 2 — Live Cursor + Pioneer Enrichment (Layer 1B)

Deliverable: Consume bridge data to build PlaybackState and TrackCursor. Display real-time cursor on waveform. On first track load, run Pioneer enrichment pass — swap in Pioneer beatgrid/BPM/key, re-align sections, log divergences.

Test: Play a pre-analyzed track on a CDJ. Verify cursor stays in sync. Adjust tempo ±8% and verify alignment. Verify divergence log captures differences.

#### Milestone 3 — Cue Stream (Layer 2, section cues only)

Deliverable: Generate `section_change`, `section_anticipation`, `section_progress`, and `beat` cues from the live cursor.

Test: Play a track and verify cues fire at correct times. Verify anticipation cues fire N beats before transitions.

#### Milestone 4 — Basic Effect Engine (Layer 3A + 3B, minimal)

Deliverable: Implement `static`, `pulse`, and `chase` effects. Build routing table. Output abstract channel values.

Test: Feed synthetic cue streams and verify output. Build 2D preview grid.

#### Milestone 5 — DMX Output (Layer 4A + 4B, DMX only)

Deliverable: Define a simple venue. Translate abstract output to DMX. Light up real fixtures.

Test: Verify colors, chase direction, timing at different BPMs.

#### Milestone 6 — End-to-End Demo

Deliverable: Play a pre-analyzed track on Pioneer hardware. SCUE tracks playback, generates cues, runs effects, controls lights in real time.

Test: DJ a short set (2–3 tracks). Subjective evaluation.

#### Milestone 7 — Event Detection (Layer 1A, Tier 2)

Deliverable: Add kick, snare, riser, faller, stab, and arp detection.

#### Milestone 8 — Full Cue Vocabulary

Deliverable: All cue types from Layer 2. More effects. Richer routing presets.

#### Milestone 9 — OSC Visual Output (Layer 4B)

Deliverable: OSC adapter. Control Resolume or TouchDesigner.

#### Milestone 10 — Real-Time User Override UI (Layer 4C)

Deliverable: Browser control surface with route muting, manual cues, palette switching, master faders.

#### Milestone 11 — Polish & Tier 3 Features

Deliverable: Mood/palette engine, Tier 3 track features, MIDI input, fixture definition library.

### Frontend Milestones (can run in parallel with backend)

#### Milestone FE-1 — Shell + Routing (no backend dependency)

Deliverable: Vite + React + TS + Tailwind scaffolded. Shell layout (sidebar, top bar, content outlet, console stub). React Router with all routes. Placeholder pages.

Test: App renders. Navigation works. Console toggles. Sidebar highlights active page.

#### Milestone FE-2 — WebSocket + Console + Bridge Status

Deliverable: WebSocket connection to FastAPI. Console displays live log stream. BLT page shows bridge status/devices. Top bar connection indicator.

Test: Backend running → console shows messages. Kill bridge → status updates → bridge restarts → status recovers.

#### Milestone FE-3 — Track Table (Read-Only)

Deliverable: Tracks page with TanStack Table (sorting, filtering, status indicators). Loads from `GET /api/tracks`.

Test: Pre-populate project. Table displays. Sort/filter works.

#### Milestone FE-4 — Upload & Analyze Flow

Deliverable: File picker → analyze → progress → completion. Duplicate detection dialog. Real-time row updates.

Test: Upload 5 tracks (1 duplicate). Dialog appears. Analyze. Progress updates. Corrupt file → error indicator.

#### Milestone FE-5 — Track Management + Projects

Deliverable: Multi-select, bulk delete, project folder selection, project switching.

#### Milestone FE-6 — Enrichment + Logs + Network Pages

Deliverable: All remaining pages with full functionality.

---

## Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Backend / orchestration | **FastAPI (Python)** | Already in use in POC. Good async support for WebSockets and real-time event loops. |
| Pro DJ Link protocol | **beat-link (Java library) via managed subprocess** | Full protocol access. Decoupled via WebSocket bridge. Updatable by JAR swap. (ADR-005) |
| Audio analysis | **librosa, allin1-mlx** | Already proven in POC. |
| Track data storage | **JSON files (source of truth) + SQLite (cache/index)** | Portable, inspectable. SQLite rebuilt from files. |
| Log storage | **Rotating log files + in-memory ring buffer** | No DB table overhead. Files for history, buffer for live console. |
| Real-time event bus | **In-process async queues (asyncio.Queue)** | All layers on same machine. Consider ZeroMQ if needed later. |
| Frontend framework | **React 19 with TypeScript (strict)** | Familiar, adequate performance, type safety for contracts. |
| Frontend build | **Vite** | Fast dev server, first-class TS/React. |
| Frontend styling | **Tailwind CSS** | Utility-first, fast iteration. |
| Frontend state | **Zustand** | Minimal boilerplate, TS-native, independent stores. |
| Frontend data fetching | **TanStack Query** | Cache, loading, error, refetch for REST. |
| Frontend tables | **TanStack Table** | Headless, TS-first, virtualization. |
| Desktop packaging (future) | **Tauri** | ~10MB vs Electron ~150MB. Same web frontend. |
| DMX output | **OLA or python-sacn** | OLA for multi-protocol, python-sacn for minimal deps. |
| OSC output | **python-osc** | Lightweight, well-maintained. |
| Configuration format | **YAML** | Human-readable, supports comments. |
| Effect definitions | **YAML files loaded at startup** | Declarative. No code changes to add effects. |
| Fixture profiles | **YAML files** | Same pattern. Ship a library, users extend. |

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 0 — Beat-Link Bridge              │
│                                                              │
│  ┌──────────────────────┐    ┌─────────────────────────┐     │
│  │  Java subprocess     │    │  Python adapter          │    │
│  │  (beat-link JAR)     │───▶│  (bridge/adapter.py)     │    │
│  │  WebSocket server    │    │  BridgeMessage → Layer 1  │   │
│  └──────────────────────┘    └──────────┬──────────────┘     │
│  Fallback: basic UDP parser             │                    │
└─────────────────────────────────────────┼────────────────────┘
                                          ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 1 — Analysis & Tracking           │
│                                                              │
│  ┌────────────────────┐     ┌───────────────────────┐        │
│  │  1A: Offline        │     │  1B: Live Tracking     │       │
│  │  Track Analysis     │     │  (via bridge data)     │       │
│  │  Audio → JSON files │────▶│  → PlaybackState       │       │
│  │  + SQLite cache     │     │  + TrackCursor per deck │       │
│  └────────────────────┘     │  + DeckMix              │       │
│                              └──────────┬────────────┘        │
└────────────────────────────────────────┼─────────────────────┘
                                         │ DeckMix (weighted cursors)
                                         ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 2 — Cue Generation                │
│  DeckMix → per-deck cues → cue mixer → [CueEvent stream]    │
└──────────────────────────┬───────────────────────────────────┘
                           │ CueEvent stream
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 3 — Effect Engine                 │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐  │
│  │ Effect   │  │ Routing      │  │ Blend &  │  │ Palette │  │
│  │ Library  │◀─│ Table        │─▶│ Priority │  │ & Mood  │  │
│  └──────────┘  └──────────────┘  └─────┬────┘  └─────────┘  │
└────────────────────────────────────────┼─────────────────────┘
                                         │ abstract channels
                                         ▼
┌──────────────────────────────────────────────────────────────┐
│                      LAYER 4 — Output & Hardware             │
│  ┌──────────────┐    ┌──────────────────────────────────┐    │
│  │ Venue Config │───▶│ Protocol Adapters                 │   │
│  └──────────────┘    │ DMX / OSC / MIDI                  │   │
│                      └──────────────────────────────────┘    │
│  ┌──────────────────────────────────────────┐                │
│  │ User Override UI                          │                │
│  └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    FRONTEND (React/TypeScript)                │
│                                                              │
│  ┌────────┐  ┌─────────────────────────────────────────┐     │
│  │Sidebar │  │ Pages: Tracks, BLT, Enrichment,         │     │
│  │ (nav)  │  │ Logs, Network                            │    │
│  │        │  ├─────────────────────────────────────────┤     │
│  │        │  │ Console (collapsible log stream)         │    │
│  └────────┘  └─────────────────────────────────────────┘     │
│  Communication: REST (CRUD) + WebSocket (real-time)          │
└──────────────────────────────────────────────────────────────┘
```

---

## File/Directory Structure

```
scue/
├── CLAUDE.md                              # Root agent instructions
├── LEARNINGS.md                           # Append-only mistake/correction log
├── README.md
├── docs/
│   ├── ARCHITECTURE.md                    # This document
│   ├── MILESTONES.md                      # Current status tracker
│   ├── DECISIONS.md                       # Architectural Decision Records
│   ├── CONTRACTS.md                       # Interface contracts between layers
│   ├── DIVERGENCE_ANALYSIS.md             # Pioneer vs SCUE divergence patterns
│   └── domains/                           # Domain knowledge reference files
│       ├── pro-dj-link.md                 # beat-link API, Pro DJ Link protocol
│       ├── edm-arrangement.md             # EDM track structure conventions
│       ├── audio-analysis.md              # librosa, DSP, detection patterns
│       ├── dmx-artnet-sacn.md             # DMX512, Art-Net, sACN protocols
│       ├── osc-midi.md                    # OSC and MIDI for visual control
│       ├── laser-safety.md                # Laser constraints, ILDA
│       └── live-networking.md             # Network topology for DJ + lighting
├── config/
│   ├── venues/                            # Venue configuration files
│   │   └── my_setup.yaml
│   ├── routing/                           # Routing table presets
│   │   ├── edm_club.yaml
│   │   └── melodic.yaml
│   ├── effects/                           # Effect definitions
│   │   ├── pulse.yaml
│   │   ├── chase.yaml
│   │   └── ...
│   ├── fixtures/                          # Fixture profile library
│   │   ├── generic_rgb_par.yaml
│   │   └── ...
│   └── palettes/                          # Color palette presets
│       ├── warm_euphoric.yaml
│       └── dark_minimal.yaml
├── lib/
│   └── beat-link-bridge.jar               # Pre-built bridge JAR
├── bridge-java/                           # Bridge Java source (separate build)
│   ├── build.gradle
│   └── src/
├── scue/
│   ├── __init__.py
│   ├── main.py                            # FastAPI app entry point
│   ├── bridge/                            # Layer 0
│   │   ├── __init__.py
│   │   ├── CLAUDE.md
│   │   ├── manager.py                     # Subprocess lifecycle
│   │   ├── adapter.py                     # BridgeMessage → Layer 1 types
│   │   ├── messages.py                    # BridgeMessage dataclasses
│   │   └── fallback.py                    # Basic UDP parser fallback
│   ├── layer1/
│   │   ├── __init__.py
│   │   ├── CLAUDE.md
│   │   ├── analysis.py                    # Offline track analysis (1A)
│   │   ├── enrichment.py                  # Pioneer enrichment pass
│   │   ├── divergence.py                  # DivergenceRecord logging & query
│   │   ├── detectors/
│   │   │   ├── sections.py                # ML boundary detection + 8-bar snapping
│   │   │   ├── flow_model.py              # EDM arrangement pattern scorer
│   │   │   ├── percussion.py
│   │   │   ├── melodic.py
│   │   │   ├── effects.py
│   │   │   └── features.py
│   │   ├── models.py                      # TrackAnalysis, Section, Event dataclasses
│   │   ├── db.py                          # SQLite cache (derived from JSON files)
│   │   ├── tracking.py                    # Live playback tracking (1B)
│   │   ├── deck_mix.py                    # DeckMix construction + weight calculation
│   │   └── cursor.py                      # TrackCursor logic
│   ├── layer2/
│   │   ├── __init__.py
│   │   ├── CLAUDE.md
│   │   ├── cue_engine.py
│   │   ├── cue_types.py
│   │   ├── deck_mixer.py                  # Blends per-deck cue streams by weight
│   │   └── generators/
│   │       ├── section_cues.py
│   │       ├── rhythmic_cues.py
│   │       ├── melodic_cues.py
│   │       └── ambient_cues.py
│   ├── layer3/
│   │   ├── __init__.py
│   │   ├── CLAUDE.md
│   │   ├── effect_engine.py
│   │   ├── effects/
│   │   │   ├── base.py
│   │   │   ├── pulse.py
│   │   │   ├── chase.py
│   │   │   └── ...
│   │   ├── routing.py
│   │   ├── blender.py
│   │   ├── palette.py
│   │   └── models.py
│   ├── layer4/
│   │   ├── __init__.py
│   │   ├── CLAUDE.md
│   │   ├── venue.py
│   │   ├── fixture_profile.py
│   │   ├── output_manager.py
│   │   ├── adapters/
│   │   │   ├── base.py
│   │   │   ├── dmx.py
│   │   │   ├── osc.py
│   │   │   └── midi.py
│   │   └── override.py
│   ├── api/                               # REST API endpoints
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── tracks.py
│   │   ├── projects.py
│   │   ├── bridge.py
│   │   └── logs.py
│   ├── project/                           # Project & storage management
│   │   ├── __init__.py
│   │   ├── manager.py                     # Project open/create/switch
│   │   ├── cache.py                       # SQLite cache build/rebuild
│   │   └── models.py                      # Project, ProjectConfig dataclasses
│   └── ui/
│       └── websocket.py                   # WebSocket handlers
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   ├── CLAUDE.md                          # FE-specific agent instructions
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── types/
│       │   ├── index.ts
│       │   ├── track.ts
│       │   ├── bridge.ts
│       │   ├── cue.ts
│       │   ├── project.ts
│       │   ├── ws.ts
│       │   └── log.ts
│       ├── stores/
│       │   ├── trackStore.ts
│       │   ├── playbackStore.ts
│       │   ├── bridgeStore.ts
│       │   ├── projectStore.ts
│       │   ├── uiStore.ts
│       │   └── logStore.ts
│       ├── api/
│       │   ├── client.ts
│       │   ├── tracks.ts
│       │   ├── projects.ts
│       │   ├── bridge.ts
│       │   └── ws.ts
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   ├── useTracks.ts
│       │   ├── useAnalysisProgress.ts
│       │   └── useKeyboardShortcuts.ts
│       ├── pages/
│       │   ├── TracksPage.tsx
│       │   ├── BLTPage.tsx
│       │   ├── EnrichmentPage.tsx
│       │   ├── LogsPage.tsx
│       │   └── NetworkPage.tsx
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── TopBar.tsx
│       │   │   ├── Console.tsx
│       │   │   └── Shell.tsx
│       │   ├── tracks/
│       │   │   ├── TrackTable.tsx
│       │   │   ├── TrackToolbar.tsx
│       │   │   ├── TrackRow.tsx
│       │   │   ├── AnalysisProgressBar.tsx
│       │   │   └── DuplicateDialog.tsx
│       │   ├── bridge/
│       │   │   ├── BridgeStatusCard.tsx
│       │   │   ├── DeviceList.tsx
│       │   │   └── PlayerDetail.tsx
│       │   ├── enrichment/
│       │   │   ├── EnrichmentLog.tsx
│       │   │   └── DivergenceTable.tsx
│       │   └── shared/
│       │       ├── Modal.tsx
│       │       ├── ConfirmDialog.tsx
│       │       ├── LoadingSpinner.tsx
│       │       ├── StatusBadge.tsx
│       │       ├── ProgressRing.tsx
│       │       └── EmptyState.tsx
│       └── utils/
│           ├── formatters.ts
│           └── constants.ts
├── tests/
│   ├── fixtures/                          # Test audio, packet captures, mock data
│   ├── test_bridge/
│   ├── test_layer1/
│   ├── test_layer2/
│   ├── test_layer3/
│   ├── test_layer4/
│   └── test_api/
└── tools/
    ├── analyze_track.py                   # CLI: analyze a track
    ├── mock_bridge.py                     # CLI: replay captured bridge messages
    ├── cue_visualizer.py                  # CLI/web: visualize cue stream
    └── venue_preview.py                   # CLI/web: 2D venue preview
```

---

## Open Questions (Decide Before Building)

1. **Tick rate for the real-time loop.** Beat-synchronized ticks (variable rate depending on BPM) vs. fixed-rate ticks (e.g., 40Hz / every 25ms)? Recommendation: fixed-rate main loop (40Hz) with beat events injected from the cursor.

2. **Multi-deck blending.** ~~When two tracks are playing during a transition, does SCUE track both and blend the cue streams?~~ **RESOLVED (ADR-006):** Layer 1B tracks all active decks simultaneously and produces a `DeckMix` with per-deck weights. Layer 2 receives the DeckMix, generates cues per-deck, and blends via a cue mixer. Phase 1 uses master-only (weight 1.0 for master, 0.0 for others). Phase 2 adds crossfade blending based on on-air/crossfader state.

3. **Latency budget.** Acceptable end-to-end latency: ≤20ms ideal, ≤50ms acceptable, >100ms noticeable. Anticipation-based cues sidestep this.

4. **Effect authoring.** YAML-defined effects sufficient, or will users need custom code? Start with YAML + built-in types.

5. **Visual software integration depth.** Triggers/parameters only (recommended) vs. generating video frames.

6. **Bridge message format versioning.** Should bridge messages include a `schema_version`? Recommendation: yes.

7. **Project portability scope.** Store only relative paths in project config. Reference analysis by fingerprint, not file path.

8. **Frontend offline capability.** Should frontend work if backend is unreachable? Recommendation: no. Single-machine app, don't add offline complexity.
