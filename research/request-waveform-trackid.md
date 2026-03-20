# Research Request: Waveform Sources & Track ID Reliability

## Requesting Role
Orchestrator

## Context
SCUE is building two frontend screens (Analysis Viewer, Live Deck Monitor) that render Pioneer-style colored waveforms from analysis-sourced RGB 3-band data. The current approach uses offline analysis (librosa/allin1-mlx) to generate waveform data stored in TrackAnalysis JSON files. Track identification on live hardware uses `rekordbox_id` from beat-link, which is known to be unreliable on DLP hardware (XDJ-AZ, Opus Quad). We need to understand the full landscape of waveform data sources and track ID strategies before committing to architectural decisions that may be hard to reverse.

## Specific Questions

### Waveform Sources
1. What waveform data formats are stored in Pioneer ANLZ files (`.DAT`, `.EXT`)? Specifically: what are the tag types (e.g., `PWAV`, `PWV2`, `PWV3`, `PWV4`, `PWV5`, `PWV6`), their resolutions, color encodings, and which hardware/rekordbox versions produce each?
2. Can SCUE read Pioneer ANLZ waveform data directly from USB (via pyrekordbox or custom parser) as an alternative or supplement to analysis-generated waveforms? What would the resolution/quality comparison be vs our current 60 FPS RGB analysis waveform?
3. Does beat-link expose any waveform data via its Java API (e.g., `WaveformFinder`, `WaveformDetail`, `WaveformPreview`)? If so, what resolution and format? Is it usable on DLP hardware (XDJ-AZ)?

### Track ID Reliability
4. On DLP hardware (XDJ-AZ, Opus Quad, CDJ-3000X), what is the actual reliability of `rekordbox_id` from `CdjStatus.getRekordboxId()`? Specifically: does it correlate with `exportLibrary.db` row IDs or `export.pdb` IDs? Does it change on re-export? Is it stable within a single performance session?
5. What alternative track identification strategies exist beyond `rekordbox_id`? Evaluate: (a) file path from USB metadata, (b) title+artist string matching, (c) audio fingerprinting (Chromaprint/AcoustID), (d) ANLZ file hash. For each: reliability, latency, implementation complexity.
6. Is there a way to get the actual file path of the currently playing track from beat-link on DLP hardware? (MetadataFinder is known to return wrong metadata on DLP — see LEARNINGS.md.)

### Data Flow Direction
7. Should SCUE adopt a "deck-first" data flow (track appears on deck → resolve → fetch/generate analysis on-demand) or "analysis-first" (all tracks pre-analyzed from USB scan → deck just looks up)? What are the tradeoffs for latency, completeness, and user experience? Consider: not all tracks on a USB may be played, and on-demand analysis takes 3-8 seconds.

## What Was Already Tried
- Attempt 1: Read beat-link source code and documentation for `CdjStatus` fields. Found `getRekordboxId()` returns an ID but its namespace/stability on DLP is undocumented. `getTrackSourcePlayer()` and `getTrackSourceSlot()` are available.
- Attempt 2: Investigated `rbox` Rust library for USB metadata. Works for `exportLibrary.db` reading but panics on ANLZ files (see LEARNINGS.md). Switched to pyrekordbox for ANLZ parsing.

## What a Good Answer Looks Like
For each question, a specific factual answer with:
- Source (documentation URL, source code reference, or empirical test result)
- Confidence level (confirmed, likely, speculative)
- Recommendation for SCUE's architecture (if applicable)

For waveform questions: include data format details (byte layout, sample count, color encoding) so we can evaluate whether to parse them.
For track ID questions: include failure modes and edge cases (multi-USB, re-export, same track on multiple USBs).

## Relevant Files
- `LEARNINGS.md` — known issues with beat-link, rbox, DLP hardware
- `docs/ARCHITECTURE.md` — system architecture overview
- `docs/FUTURE_AUDIO_FINGERPRINTING (1).md` — existing audio fingerprinting design doc
- `scue/bridge/messages.py` — current PlayerStatusPayload parsing
- `scue/layer1/usb_scanner.py` — USB scan logic
- `scue/layer1/storage.py` — track_ids table, lookup_fingerprint()
- `research/dlp-track-id-reliability.md` — existing research on DLP track IDs (if present)
- `specs/feat-FE-live-deck-monitor/spec.md` — composite key design for track resolution
