# Research Findings: SuperTimecodeConverter Fit for SCUE

**Date:** 2026-03-22
**Status:** Research complete
**Depends on:** Layer 0 bridge work, Layer 4 output planning

---

## Questions Addressed

1. What does `fiverecords/SuperTimecodeConverter` actually provide?
2. Which SCUE problems could it help solve directly?
3. Is it a candidate replacement for any part of SCUE, or better treated as a sidecar/reference implementation?
4. What integration risks or mismatches matter most for SCUE's current architecture and XDJ-AZ-centric workflow?

---

## Executive Summary

`SuperTimecodeConverter` ("STC") is a strong fit for the part of SCUE that needs to turn DJ transport and mixer state into downstream show-control signals. It is a poor fit as a replacement for SCUE's core analysis and semantic cue-generation pipeline.

The highest-value overlap is:

- `Pro DJ Link / StageLinQ -> MTC / LTC / Art-Net timecode`
- per-track manual offsets and triggers
- DJM mixer parameter forwarding to `OSC / MIDI / Art-Net DMX`
- BPM forwarding to `Ableton Link`, MIDI Clock, and OSC

The lowest-overlap area is SCUE's differentiator:

- offline audio analysis
- Pioneer beatgrid enrichment for cue generation
- section/event/mood inference
- semantic cue stream generation

**Recommendation:** Treat STC as either:

1. a **sidecar app** for external timecode/show-control output, or
2. a **code/reference donor** for a future SCUE Layer 4 timecode/output module.

Do **not** treat it as a drop-in replacement for SCUE's Layer 1/2 architecture.

---

## What STC Actually Is

STC is a JUCE/C++ desktop application with a modular routing core centered on `TimecodeEngine`.

At the current inspected revision:

- Repository: `https://github.com/fiverecords/SuperTimecodeConverter`
- Inspected commit: `1d65e36911f8c3a0ccafc6002c6ac3fde381e137`
- Commit date: `2026-03-22 00:41:56 +0100`
- App version in source: `1.6.0`

Core capabilities documented in the repo:

- up to 8 independent timecode engines
- inputs: `Pro DJ Link`, `StageLinQ`, `MTC`, `Art-Net`, `LTC`, `System Time`
- outputs: `MTC`, `Art-Net timecode`, `LTC`, `Audio Thru`
- direct Pioneer Pro DJ Link implementation
- direct Denon StageLinQ implementation
- track-trigger routing and mixer-parameter routing
- optional Ableton Link tempo publishing

Relevant source files:

- `TimecodeEngine.h`
- `ProDJLinkInput.h`
- `DbServerClient.h`
- `TriggerOutput.h`
- `MtcOutput.h`
- `ArtnetOutput.h`
- `LtcOutput.h`
- `LinkBridge.h`
- `AppSettings.h`

---

## Strong Matches with SCUE

### 1. Layer 4 Timecode / Show-Control Output

This is the cleanest architectural match.

SCUE's architecture already plans protocol adapters for `DMX / Art-Net / OSC / MIDI` in Layer 4, but the domain docs are still placeholders:

- `docs/ARCHITECTURE.md`
- `scue/layer4/CLAUDE.md`
- `docs/domains/dmx-artnet-sacn.md`
- `docs/domains/osc-midi.md`

STC already solves several adjacent problems:

- drift-resistant `MTC` output using a high-resolution timer
- `Art-Net` timecode output
- `LTC` generation with pitch-aware timing
- per-output frame offsets for latency compensation
- shared output-device handling for multiple MIDI/timecode features

This makes STC a strong reference implementation for a future SCUE timecode adapter layer.

### 2. Manual Per-Track Overrides

STC's `TrackMap` is effectively a practical operator override system:

- track match by `artist + title`
- per-track timecode offset
- per-track BPM multiplier
- per-track triggers on load:
  - MIDI note
  - MIDI CC
  - OSC
  - Art-Net DMX

This is relevant to SCUE even if SCUE never adopts SMPTE-centric workflows. It suggests a useful fallback/control surface pattern:

- known track -> apply saved operator metadata immediately
- fire venue macros on track load
- compensate for playback/display/system latency per song when needed

### 3. DJM Mixer State as Show Control

STC's `MixerMap` is directly relevant to SCUE's "DJ intent" side:

- channel faders
- crossfader
- EQ / FX / assign data
- VU data
- routing to OSC, MIDI CC, MIDI Note, and Art-Net DMX

This is a meaningful complement to SCUE's music-driven cue engine. Even if SCUE stays analysis-first, mixer gestures are high-value control signals for:

- deck-weight inference
- deck-side assignment
- video or laser routing
- performer-intent overrides

### 4. Denon / StageLinQ as Future Expansion

STC includes substantial StageLinQ support, including:

- deck state
- metadata
- waveform/performance data on the Denon side
- mixer/fader information

SCUE is currently Pioneer-first. If Denon support becomes important later, STC is a strong research/code reference.

---

## Weak Matches / Non-Matches

### 1. It Does Not Replace SCUE's Core Value

STC does not solve SCUE's main problem:

- offline analysis of raw audio files
- section detection
- event detection
- cue generation
- effect mapping at the semantic level

SCUE's architecture is centered on:

- Layer 1: analysis + playback tracking
- Layer 2: music -> semantic cues
- Layer 3: cues -> abstract visual outputs

STC is centered on:

- transport conversion
- timecode generation
- trigger routing
- mixer/control forwarding

Those are complementary systems, not interchangeable ones.

### 2. Pioneer Metadata Coverage Appears Oriented Toward Control/UI, Not Enrichment

From the inspected source, STC's Pioneer path clearly handles:

- player discovery
- playhead / absolute position
- BPM / pitch / actual speed
- track metadata
- artwork
- preview waveform
- DJM mixer state

What is **not** evident in the Pioneer path:

- Pioneer beatgrid extraction for SCUE-style enrichment
- phrase analysis ingestion for cue generation
- cue-point ingestion as a first-class semantic input

By contrast, SCUE already has explicit architecture and research around:

- beatgrid enrichment
- ANLZ parsing
- cue points
- phrase analysis
- DLP-aware metadata resolution

Relevant SCUE references:

- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/bridge-java-spec.md`
- `research/findings-xdj-az-blt-metadata-2026-03.md`
- `research/findings-waveform-trackid.md`

### 3. Desktop App, Not Headless Service

STC is built as a desktop JUCE application, not as:

- a daemon
- a local API server
- a reusable CLI-first process
- an embeddable library boundary intended for external consumers

That makes "integrate STC into SCUE" expensive unless the plan is simply "run STC separately beside SCUE."

The source layout reinforces this:

- `Main.cpp`
- `MainComponent.h`
- `MainComponent.cpp`

There is no obvious headless control plane exposed for SCUE to consume.

---

## Best Use Cases for SCUE

### Option A: Sidecar Companion App

Use STC unchanged beside SCUE when the immediate goal is:

- feed external SMPTE consumers
- synchronize Resolume / grandMA / video systems quickly
- calibrate latency with per-output offsets
- expose raw DJM controls to downstream systems without waiting for SCUE Layer 4

This is the fastest path to value.

### Option B: Code / Design Reference for SCUE Layer 4

Borrow patterns, not the application:

- per-output frame offsets
- dedicated timecode transport objects
- drift-resistant timer design
- shared MIDI handle strategy
- track-map override model
- mixer-map routing model
- crossfader-side auto-follow

This is likely the best long-term SCUE fit.

### Option C: Temporary Show-Control Bridge During SCUE Build-Out

Use SCUE as the "brain" and STC as the "transport/utilities" layer while SCUE's own output stack matures.

This makes sense if the current bottleneck is external synchronization rather than analysis.

---

## Integration Risks and Caveats

### 1. Virtual CDJ Player Number Conflict

This is the biggest immediate operational risk.

STC's Pro DJ Link implementation uses a Virtual CDJ identity with player number `5` by default:

- `ProDJLinkInput.h`: `kDefaultVCDJNumber = 5`

SCUE's bridge also defaults to player number `5`:

- `config/bridge.yaml`: `player_number: 5`
- `docs/bridge-java-spec.md`: `--player-number` default `5`

If both run on the same Pro DJ Link network and both claim player `5`, they are likely to conflict.

**Practical implication:** if STC is run alongside SCUE, one of them should move to player `6`.

### 2. XDJ-AZ Support Looks Promising but Not Fully Proven

STC's README explicitly lists tested Pioneer hardware as:

- `CDJ-3000`
- `CDJ-3000X`
- `DJM-900NXS2`
- `DJM-V10`
- `DJM-A9`

It says XDJ-series hardware "should work" but is not verified.

This matters because SCUE is currently very XDJ-AZ aware, and SCUE has already accumulated DLP-specific lessons:

- XDJ-AZ DLP metadata differences
- dbserver considerations
- XDJ-AZ track-change quirks
- DLP namespace reconciliation

So STC should be treated as **promising on XDJ-AZ, but unverified**, not assumed production-ready for that hardware.

### 3. Architectural Mismatch with SCUE's Layer Boundary Goals

SCUE wants:

- Python backend
- typed contracts
- analysis JSON as source of truth
- cue engine and output engine decoupled from hardware details

STC's design is excellent for a single native operator-facing app, but it is not obviously shaped around SCUE's backend/service contract model.

This increases the cost of deep integration relative to selective reuse.

### 4. Pioneer Enrichment Path Still Belongs to SCUE

Even if STC is adopted as a sidecar, SCUE should keep ownership of:

- ANLZ ingestion
- beatgrid source-of-truth logic
- divergence logging
- Layer 1 enrichment
- Layer 2 semantic cue generation

That is where SCUE has domain-specific leverage.

---

## Recommended Next Steps

### Near-Term Recommendation

If the current pain is external sync and show-control interoperability, test STC as a sidecar first.

Suggested goal for the test:

1. keep SCUE responsible for analysis and cue generation
2. run STC only for external transport/control outputs
3. move SCUE or STC off player `5` before testing
4. validate XDJ-AZ compatibility before depending on it

### Medium-Term Recommendation

When SCUE starts serious Layer 4 build-out, use STC as a design reference for:

- MTC output
- LTC output
- Art-Net timecode output
- manual track override maps
- mixer routing maps
- latency-calibration UI/UX

### Explicit Non-Recommendation

Do not pause SCUE's own analysis/enrichment/cue architecture in favor of trying to bend STC into that role. The overlap is too small in the areas where SCUE is differentiated.

---

## Bottom-Line Verdict

**Usefulness to SCUE: HIGH, but narrowly targeted.**

- **High value for:** external sync, show-control plumbing, output calibration, DJM-driven control, future Layer 4 design
- **Low value for:** replacing SCUE's analysis pipeline, enrichment pipeline, or semantic cue engine

The most accurate mental model is:

> STC is a strong transport/control companion for SCUE, not a substitute for SCUE.

---

## Evidence Reviewed

### STC Repository

- README
- `Main.cpp`
- `MainComponent.h`
- `TimecodeEngine.h`
- `ProDJLinkInput.h`
- `DbServerClient.h`
- `TriggerOutput.h`
- `MtcOutput.h`
- `ArtnetOutput.h`
- `LtcOutput.h`
- `LinkBridge.h`
- `AppSettings.h`
- `StageLinQDbClient.h`

### SCUE Repository

- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/bridge-java-spec.md`
- `docs/bridge/INTEGRATION.md`
- `config/bridge.yaml`
- `scue/layer4/CLAUDE.md`
- `research/findings-xdj-az-blt-metadata-2026-03.md`
- `research/findings-prodj-link-live-data.md`
- `research/findings-waveform-trackid.md`

