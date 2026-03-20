# Research Request: Bridge Data Strategy — Waveforms, DLP IDs, Data Flow & Fingerprinting Timeline

## Requesting Role
Orchestrator (on behalf of Brach)

## Context
SCUE's bridge layer currently handles two metadata paths (DLP vs legacy) per ADR-012. Before designing M3+ features that depend on richer bridge data (waveform display, robust track reconciliation, cue stream generation), we need answers on hardware-specific capability gaps, DLP ID reliability edge cases, the optimal data flow topology, and when audio fingerprinting should enter the pipeline.

## Specific Questions

### Q1: WaveformFinder availability on legacy CDJ-2000 / XDJ-XZ
1. Does `WaveformFinder.getInstance().requestWaveformDetailFrom(player)` succeed on CDJ-2000 (non-NXS, non-NXS2) hardware? What about CDJ-2000NXS (first gen Nexus)?
2. Does it succeed on XDJ-XZ? The XDJ-XZ is hybrid — it supports both legacy export.pdb and DLP exportLibrary.db. Which metadata path does it use by default, and does that affect WaveformFinder?
3. For DLP-only hardware (XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X) where we disabled WaveformFinder per ADR-012 — can we selectively re-enable WaveformFinder while keeping MetadataFinder off? Or is WaveformFinder's data also corrupted by the DLP ID namespace mismatch?
4. What does pyrekordbox or rbox expose for waveform data from ANLZ files (PWAV, PWV2, PWV3 tags)? Could we read waveforms from USB as a fallback for hardware where WaveformFinder fails?

### Q2: DLP track ID reliability and reconciliation strategy
1. On DLP hardware, `CdjStatus.getRekordboxId()` returns a DLP-namespace ID. We use this to look up tracks in rbox's `OneLibrary`. How stable is this ID across: (a) USB re-exports from rekordbox, (b) the same track on different USBs, (c) firmware updates on the hardware?
2. When a DJ uses two USBs simultaneously (one per deck), do the DLP IDs from each USB collide? i.e., can USB-A track #47 and USB-B track #47 be different tracks?
3. What reconciliation strategy should we use to match a DLP-identified track to our offline TrackAnalysis JSON files? Options: (a) DLP ID → rbox title/artist → fuzzy match to analysis DB, (b) DLP ID → rbox file path → SHA256 hash match, (c) DLP ID → ANLZ waveform fingerprint → match. Which is most reliable?
4. For legacy hardware where beat-link MetadataFinder works correctly, do `getRekordboxId()` IDs have the same stability characteristics, or are legacy DeviceSQL IDs more/less stable?

### Q3: Deck-first vs analysis-first data flow tradeoffs
1. **Deck-first flow:** A track is loaded on a deck → bridge reports it → SCUE looks up or triggers analysis. Pro: only analyze what's actually played. Con: cold-start latency on first play if not pre-analyzed.
2. **Analysis-first flow:** DJ imports tracks into SCUE project → batch analysis runs → when track loads on deck, analysis is already available. Pro: zero latency at play time. Con: may analyze tracks never played.
3. **Hybrid:** Batch pre-analyze the DJ's USB/collection, but also support deck-triggered on-demand analysis as fallback. What are the architectural implications for Layer 1B's TrackCursor? Does it need a "pending analysis" state?
4. Given that analysis takes ~3-4s/track (ADR-008) and a DJ set might use 20-40 tracks from a library of 500-2000, what's the cost/benefit of full pre-analysis vs on-demand?

### Q4: Audio fingerprinting implementation timeline
1. The fingerprinting doc (FUTURE_AUDIO_FINGERPRINTING.md) says "deferred to post-Milestone 11." Given our current milestone progress (see docs/MILESTONES.md), is there a natural earlier insertion point — e.g., as part of the USB scan/import flow in M3-M4?
2. Would a minimal constellation-map fingerprint (offline generation only, no live matching yet) be low-cost enough to add to the analysis pipeline now, so the database accumulates fingerprints for future use?
3. The "normalize at query time" tempo handling approach requires pitch data from the bridge. In degraded mode (no bridge, fingerprinting is the fallback), pitch data is unavailable. Does this create a chicken-and-egg problem, or is approach #3 (tempo-invariant hashes) the only viable path for degraded mode?
4. What Python libraries exist for constellation-map fingerprinting? (e.g., dejavu, audfprint, chromaprint/pyacoustid) Which would be suitable for SCUE's use case (local DB, ~2000 tracks, offline indexing + fast live query)?

## What Was Already Tried
- ADR-012 established the DLP vs legacy split and disabled MetadataFinder/WaveformFinder/etc. for DLP hardware. The open question is whether this was too aggressive (especially for WaveformFinder).
- LEARNINGS.md documents the DLP ID namespace mismatch and rbox ANLZ panic issues. The open question is ID stability across USB re-exports and multi-USB scenarios.
- FUTURE_AUDIO_FINGERPRINTING.md provides the algorithm design but no implementation timeline or library survey.

## What a Good Answer Looks Like
For each question group:
- **Q1:** A compatibility matrix (hardware model × beat-link finder class → works/broken/untested) with source citations (beat-link source, beat-link-trigger issues, DJ forums).
- **Q2:** Concrete reconciliation algorithm recommendation with pseudocode, covering single-USB and multi-USB scenarios. Identify which ID fields are stable vs volatile.
- **Q3:** Architecture recommendation (deck-first / analysis-first / hybrid) with a state diagram for TrackCursor showing the "pending" path. Quantified latency estimates.
- **Q4:** Library comparison table (library, last maintained, Python 3.11+ compat, tempo handling, DB backend, license). Timeline recommendation for when to add fingerprint generation to the pipeline.

## Relevant Files
- `docs/FUTURE_AUDIO_FINGERPRINTING (1).md` — fingerprinting algorithm design
- `LEARNINGS.md` — DLP ID issues, rbox panics, bridge pitfalls
- `docs/DECISIONS.md` — ADR-012 (DLP path), ADR-013 (pyrekordbox), ADR-005 (bridge architecture)
- `docs/bridge/PITFALLS.md` — beat-link and rbox library-specific findings
- `docs/ARCHITECTURE.md` — layer definitions and data flow
- `docs/CONTRACTS.md` — interface contracts between layers
- `docs/MILESTONES.md` — current progress (for fingerprinting timeline)
- `scue/bridge/` — bridge implementation (Java JAR + Python adapter)
- `scue/layer1/` — track analysis and live tracking
