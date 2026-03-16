# Milestones

## Current: Milestone 1 — Analysis Pipeline (Layer 1A, Tier 1)
Status: IN PROGRESS
Started: 2025-03

### What's done
- [x] ML boundary detection via allin1-mlx (Apple Silicon)
- [x] Ruptures change-point detection (KernelCPD) as secondary boundary detector
- [x] Boundary merging (allin1 primary + ruptures splits long sections)
- [x] EDM label classification heuristics (drop, build, fakeout, breakdown)
- [x] Downbeat quantization of section boundaries
- [x] Confidence scoring (allin1 + ruptures agreement)
- [x] RGB waveform visualizer (R=bass, G=mids, B=highs) via HTML5 Canvas
- [x] Section marker overlays on waveform
- [x] FastAPI server with upload, analysis, and audio streaming endpoints
- [x] Browser UI (track upload, analysis, waveform, JSON panel)

### Still needed for Milestone 1 completion
- [ ] 8-bar snapping pass (snap boundaries to nearest 8-bar grid line)
- [ ] EDM flow model (score section label sequences against known arrangement patterns)
- [ ] `bar_count` / `expected_bar_count` / `irregular_phrase` fields on sections
- [ ] `fakeout: true` flag on sections (currently relabels as "fakeout" label — unify)
- [ ] SQLite storage (currently returns results direct; no persistence between sessions)
- [ ] Track fingerprint (SHA256) as primary key
- [ ] Test suite against ≥5 reference tracks
- [ ] ≥80% section boundary accuracy within 1 bar on test tracks

### Blocking questions
- None currently

---

## Next: Milestone 2 — Live Cursor + Pioneer Enrichment (Layer 1B)
Status: IN PROGRESS (Pioneer connectivity plumbed; cursor logic not yet built)

### What's done
- [x] Pro DJ Link UDP parsing (ports 50000/50001)
- [x] Device discovery (keepalive packet parsing)
- [x] CDJ status parsing (BPM, pitch, beat number, flags)
- [x] macOS IP_BOUND_IF fix for broadcast reception on multi-interface machines
- [x] WebSocket bridge: Pioneer data → browser in real time
- [x] Live deck panels in browser UI (CH1/CH2, BPM, beat dots, flags)
- [x] pioneer_status / is_receiving stale-timeout logic

### Still needed for Milestone 2 completion
- [ ] `TrackCursor` dataclass (current section, next section, upcoming events, beat position)
- [ ] Cursor logic: map Pioneer playback position → section in stored TrackAnalysis
- [ ] Tempo scaling: scale event timestamps by (original_bpm / current_bpm)
- [ ] Pioneer enrichment pass: swap beatgrid/BPM/key, re-align boundaries, log divergences
- [ ] SQLite storage (prerequisite — from Milestone 1)
- [ ] DivergenceRecord logging
- [ ] Waveform cursor display (real-time playback position on waveform visualization)
- [ ] Mock Pro DJ Link packet replay tool (`tools/mock_prodjlink.py`)
- [ ] Tests with packet captures

---

## Backlog

### Milestone 3 — Cue Stream (Layer 2, section cues only)
Status: NOT STARTED
Deliverable: section_change, section_anticipation, section_progress, beat cues from live cursor. Display as real-time text log.

### Milestone 4 — Basic Effect Engine (Layer 3A + 3B, minimal)
Status: NOT STARTED
Deliverable: static, pulse, chase effects. Routing table maps beat→pulse, section_change→color change. 2D preview grid.

### Milestone 5 — DMX Output (Layer 4A + 4B)
Status: NOT STARTED
Deliverable: Simple venue config, DMX output via OLA or python-sacn. Real fixtures light up.

### Milestone 6 — End-to-End Demo
Status: NOT STARTED
Deliverable: Play a track on Pioneer, SCUE tracks playback, lights respond.

### Milestone 7 — Event Detection (Layer 1A, Tier 2)
Kick, snare, riser, faller, stab, arp detection.

### Milestone 8 — Full Cue Vocabulary
All Layer 2 cue types. More effects. Richer routing presets.

### Milestone 9 — OSC Visual Output (Layer 4B)
Resolume / TouchDesigner control.

### Milestone 10 — Real-Time User Override UI (Layer 4C)
Browser control surface: route muting, manual triggers, palette switching, master faders.

### Milestone 11 — Polish & Tier 3 Features
Mood/palette engine, Tier 3 track features, MIDI input, fixture library, etc.
