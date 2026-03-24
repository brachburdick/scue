# Milestones

## Completed: Milestone FE-1 — Shell + Routing (no backend dependency)
Status: COMPLETE
Started: 2026-03-16
Completed: 2026-03-16

### Deliverables
- [x] Vite + React + TS + Tailwind scaffolded
- [x] Shell layout (sidebar, top bar, content outlet, console stub)
- [x] React Router with all routes
- [x] Placeholder pages (Tracks, BLT, Enrichment, Logs, Network)

### Acceptance criteria — all passing
- App renders
- Navigation works
- Console toggles
- Sidebar highlights active page

### Notes
- Used Vite 6 (not 8) due to Node 20.18 compatibility. Vite 8 requires Node 20.19+.
- Tailwind v3 (not v4) due to peer dependency conflicts with Vite 6.

---

## Completed: Milestone 1 — Analysis Pipeline (Layer 1A, Tier 1)
Status: COMPLETE
Started: 2026-03-16
Completed: 2026-03-16

### Deliverables
- [x] Section segmentation with allin1-mlx (+ librosa-only fallback)
- [x] 8-bar snapping pass
- [x] EDM flow model labeler
- [x] JSON file storage keyed by track fingerprint (SHA256)
- [x] SQLite cache (derived index)
- [x] Fakeout detection
- [x] RGB waveform computation (3-band: bass/mids/highs at 60fps)
- [x] Test suite against 5 reference tracks (57 tests, all passing)

### Acceptance Criteria — All Passing
- Pipeline analyzes audio → sections, beats, downbeats, features, waveform
- Sections are 8-bar snapped with irregular phrase flagging
- EDM flow model relabels to intro/verse/build/drop/breakdown/fakeout/outro
- JSON files persist as source of truth; SQLite is derived cache
- All 5 reference tracks produce valid section segmentations
- TrackAnalysis schema includes enrichment fields (null) from day one
- REST API: GET /api/tracks, GET /api/tracks/{fp}, POST /api/tracks/analyze
- CLI tool: python tools/analyze_track.py <path>

### Notes
- allin1-mlx gracefully skipped when not installed; falls back to librosa-only with ruptures
- Sections clamped: first starts at 0.0, last ends at track duration
- Running without allin1-mlx: confidence is lower (scaled by 0.7), all sections derived from ruptures change-point detection
- Pipeline takes ~3-4s per track on M-series Mac (without allin1-mlx)

---

## Research Complete: Waveform, Track ID, Bridge Data Strategy (2026-03-20)

**Status:** COMPLETE — 11 research findings produced across waveform sources, DLP track ID reliability, ANLZ formats, hardware topology, audio capture, fingerprinting, and bridge data strategy.

### Key Conclusions

**Waveform data:** Primary source: WaveformFinder via beat-link 8.1.0-SNAPSHOT (live, works on XDJ-AZ + all legacy; still broken on Opus Quad which has no dbserver). Fallback: USB ANLZ waveforms via pyrekordbox for all hardware (PWV7 on CDJ-3000+, PWV5 on NXS2, PWV3 on older). See ADR-014 (updated), ADR-017.

**DLP Track IDs:** Volatile across USB re-exports, collide across multiple USBs (mathematically guaranteed). Composite key `(source_player, source_slot, rekordbox_id)` is REQUIRED. Current `track_ids` table has a multi-USB bug. See ADR-015.

**beat-link DLP bug:** XDJ-AZ/CDJ-3000X return wrong data from ALL Finders (not just metadata). Root cause: `CdjStatus` constructor only flags `isFromOpusQuad`; XDJ-AZ takes else branch, DLP ID passes through unchanged. Recommended fix: Strategy D (SCUE translation layer, 2-4 days). See ADR-016.

**Audio capture:** Feasible via USB interface + sounddevice (~0.5ms per update). Informed source separation (known reference signals) far simpler than blind separation. Deferred to multi-deck Phase 2.

**Fingerprinting:** No suitable maintained library exists. Custom constellation-map implementation (~500-800 lines, 2-3 dev-days) recommended at M7.

### Actions Surfaced
- **HIGH:** Fix composite key bug in `track_ids` table (before Live Deck Monitor ships)
- **HIGH:** Add `DeckAnalysisState` enum for on-demand analysis fallback
- **MEDIUM:** Pioneer ANLZ waveform reading via pyrekordbox (instant display)
- **MEDIUM:** Dual-database USB scanning for mixed hardware
- **MEDIUM:** Stale-scan detection for re-exports
- **DEFERRED (M7):** Constellation-map fingerprint generation
- **DEFERRED:** Audio capture / Layer 0.5 prototype

---

## Current Backlog

### FE-Analysis-Viewer — Pioneer-style colored waveform with section overlays
**Status:** READY — spec complete, 8 tasks defined.
- Standalone page at `/analysis` with mini track table, WaveformCanvas (shared), section list, metadata panel
- WaveformCanvas renders SCUE RGB 3-band data (future: Pioneer ANLZ waveforms as instant fallback)
- Bidirectional section ↔ waveform interaction
- Build order: this feature first (provides shared WaveformCanvas for Live Deck Monitor)

### FE-Live-Deck-Monitor — 2-deck real-time waveform + cursor
**Status:** READY — spec complete, 7 tasks defined. Depends on Analysis Viewer (shared WaveformCanvas).
- Backend: `playback_position_ms` + source fields in bridge, composite key migration, resolve endpoint
- Frontend: auto-resolve composite key → fingerprint → analysis, auto-scrolling waveform with live cursor
- Research-driven: composite key for multi-USB safety, Pioneer waveform as instant fallback

### Milestone 3 — Cue Stream (Layer 2, section cues only)
**Status:** BLOCKED — waiting on FE-Analysis-Viewer + FE-Live-Deck-Monitor to validate data pipeline end-to-end.
- Spec complete: section_change, section_anticipation, section_progress, energy_level
- CueEngine + DeckCueGenerator architecture, 40 Hz tick rate, YAML config
- Proposed contract addition: `deck_number` field on CueEvent

---

## Backlog

### ~~Milestone FE-3 — Track Table (Read-Only)~~ → COMPLETE (2026-03-16)
- [x] TanStack Table with 10 sortable columns (Title, Artist, BPM, Key, Duration, Sections, Mood, Source, Analyzed, ID)
- [x] Client-side search filtering by title/artist
- [x] Mood badges (color-coded) and Source badges (analysis vs enriched)
- [x] TanStack Query integration with Vite API proxy
- [x] QueryClientProvider wired into app root
- [x] TypeScript types mirroring Python models (src/types/track.ts)

### ~~Milestone 0 — Beat-Link Bridge (Layer 0, Python Side)~~ → COMPLETE (2026-03-16)
- [x] `scue/bridge/messages.py` — BridgeMessage dataclass + 10 typed payload dataclasses
- [x] `scue/bridge/client.py` — WebSocket client with reconnection handling
- [x] `scue/bridge/adapter.py` — Stateful adapter: BridgeMessage → PlayerState (per-player accumulation)
- [x] `scue/bridge/fallback.py` — UDP fallback parser (ported from POC, emits BridgeMessage)
- [x] `scue/bridge/manager.py` — Subprocess lifecycle with graceful degradation (no_jre/no_jar states)
- [x] `scue/api/bridge.py` — `GET /api/bridge/status` endpoint
- [x] `tools/mock_bridge.py` — WebSocket replay tool for testing without Pioneer hardware
- [x] 4 JSON fixture files (device discovery, playback session, track metadata, transition)
- [x] 121 tests passing (messages, adapter, manager, fallback)
- [x] Java bridge JAR (`lib/beat-link-bridge.jar`) — v1.1.0 built and tested with XDJ-AZ (ADR-012: real-time data only, metadata finders stripped)
- [x] **[AUDIT]** Fallback parser wired into BridgeManager — triggers on `no_jre`/`no_jar` and after 3 consecutive crashes. Fixed 2026-03-17.
- [x] **[BUG-BRIDGE-CYCLE]** Crash-restart cycle on hardware disconnect/reconnect — 6 root causes identified and fixed (2026-03-18). QA verified with live XDJ-AZ hardware. Remaining FE display issues (stale devices/players, route mismatch persistence, console log clearing) logged as non-blockers in docs/bugs/frontend.md.
- [x] **[AUDIT]** Fallback parser test file added (`tests/test_bridge/test_fallback.py`) — 7 tests. Fixed 2026-03-17.
- [x] **[FIX]** Synthetic device creation from `player_status` — adapter now infers `DeviceInfo` when `device_found` was missed (e.g., Python connects after bridge init). Fixed 2026-03-17.

### ~~Milestone 2 — Live Cursor + Pioneer Enrichment (Layer 1B)~~ → COMPLETE (2026-03-16)
- [x] `scue/layer1/models.py` — Added TrackCursor, SectionInfo, BeatPosition, PlaybackState, TrackCursorFeatures, DivergenceRecord
- [x] `scue/layer1/cursor.py` — build_cursor(): maps playback position into TrackAnalysis sections/events
- [x] `scue/layer1/enrichment.py` — Pioneer enrichment pass: BPM/beatgrid/key swap, section rescaling, versioned storage
- [x] `scue/layer1/divergence.py` — DivergenceRecord logging and querying via SQLite
- [x] `scue/layer1/tracking.py` — PlaybackTracker: bridge adapter → TrackCursor, on-air-only cursor (ADR-006)
- [x] `scue/layer1/storage.py` — Added lookup_fingerprint, link_rekordbox_id, store_divergence, query_divergences
- [x] Bridge adapter → PlaybackTracker wired in main.py
- [x] `docs/bridge-java-spec.md` — Java bridge JAR handoff spec for tech-lead agent
- [x] 57 new tests (cursor: 16, enrichment: 12, tracking: 10, divergence: 6, helpers: 13), all passing
- [x] Full suite: 156 passed, 11 skipped

### ~~Milestone 0B — USB Scanner & rbox Metadata (ADR-012 Completion)~~ → COMPLETE (2026-03-16)
- [x] `rbox>=0.1.7` added as optional dependency (`[project.optional-dependencies.usb]`)
- [x] `scue/layer1/usb_scanner.py` — read_usb_library (via rbox OneLibrary), match_usb_tracks (path stem + title/artist + prefix matching), apply_scan_results
- [x] `scue/layer1/storage.py` — pioneer_metadata SQLite table with store/get/list methods
- [x] `scue/api/usb.py` — POST /api/usb/scan, GET /api/usb/status, GET /api/usb/pioneer-metadata
- [x] `scue/layer1/tracking.py` — enrichment now uses cached Pioneer metadata (key, beatgrid) from USB scan
- [x] `config/usb.yaml` — USB path configuration
- [x] Wired into main.py (usb_router + init_usb_api)
- [x] 21 new tests (scanner: 19, prefix matching, storage), all passing
- [x] Verified against real XDJ-AZ USB backup: 2022 tracks read, 4/4 analyses matched
- [x] Full suite: 277 passed, 11 skipped (as of 2026-03-17)
- [x] ANLZ beatgrid reading: rbox Rust parser panicked on XDJ-AZ files; replaced with two-tier pure-Python strategy (ADR-013: pyrekordbox primary + custom anlz_parser.py fallback). Fixed 2026-03-16.

### ~~Audit Backlog — 2026-03-17 findings~~ → COMPLETE (2026-03-18)
- [x] **[AUDIT-01]** Traffic detected but device never discovered — fixed 2026-03-17 (synthetic device creation from `player_status`)
- [x] **[AUDIT-02]** Fallback parser not wired into BridgeManager — fixed 2026-03-17
- [x] **[AUDIT-03]** API-level test coverage — `tests/test_api/` added (20 tests: batch jobs, scan dedup, WS broadcasting, bridge settings). Fixed 2026-03-18.
- [x] **[AUDIT-04]** YAML config consolidation — `scue/config/loader.py` + `config/server.yaml` + bridge/usb.yaml extensions. Pre-existing (confirmed complete 2026-03-18).
- [x] **[AUDIT-05]** Doc drift (React version, FE-BLT milestone, FE-2 status) — fixed 2026-03-17/18
- Full suite: 304 passed, 11 skipped (2026-03-18); 6 `test_analysis_edge_cases` skipped due to librosa not installed in test env — pre-existing, not a regression

### Milestone 3 — Cue Stream (Layer 2, section cues only)
### Milestone 4 — Basic Effect Engine (Layer 3A + 3B, minimal)
### Milestone 5 — DMX Output (Layer 4A + 4B)
### Milestone 6 — End-to-End Demo
### Milestone FE-2 — WebSocket + Console + Bridge Status
**Status:** PARTIALLY COMPLETE — WebSocket client + bridgeStore built as part of FE-BLT. Console log streaming remains.
- [x] WebSocket client with auto-reconnect (`api/ws.ts`)
- [x] `bridgeStore` — bridge status, devices, players, dotStatus, isStartingUp
- [x] `pioneer_status` message handling (is_receiving, lastMessageAgeMs)
- [ ] Console panel wired to real-time bridge log output (currently placeholder)

### ~~Milestone FE-BLT — Bridge Page~~ → COMPLETE (2026-03-17)
- [x] BridgeStatusPanel: StatusBanner, TrafficIndicator, DeviceList, PlayerList
- [x] HardwareSelectionPanel: RouteStatusBanner, ActionBar, InterfaceSelector
- [x] InterfaceRow with type/link-local badges and scoring
- [x] Route auto-fix on page load (at most once per mount)
- [x] Startup gating pattern: all queries gated with `enabled: !isStartingUp`
- [x] TopBar: StatusDot (bridge status only), TrafficDot (Pioneer liveness), StartupIndicator
- [x] 6 bugs found and fixed (see `docs/bugs/frontend.md`)
- [x] **[RESOLVED]** Pioneer traffic indicator flickers during active playback — presumed resolved by BLT→Bridge refactor 2026-03-18; see docs/bugs/frontend.md

### ~~Milestone FE-4 — Upload & Analyze Flow~~ → COMPLETE (2026-03-16)
- [x] Path-based scan → batch analyze → progress tracking flow
- [x] `POST /api/tracks/scan` — directory scanning with fingerprint-based dedup
- [x] `POST /api/tracks/analyze-batch` — sequential background analysis with in-memory job tracking
- [x] `GET /api/tracks/jobs/{job_id}` — job status polling (1s interval, auto-stops on completion)
- [x] `GET /api/filesystem/browse` — server-side filesystem browser (separate router)
- [x] AnalyzePanel: 3-phase UI (path input → scan results → progress bar)
- [x] FolderBrowser modal: breadcrumb navigation, directory/audio-file listing
- [x] Auto-dismiss on completion: resets to path input after 2s delay
- [x] Zustand store for analyze flow state (analyzeStore.ts)
- [x] Per-step progress reporting: shows current analysis step (1-10) with mini progress bar during single-file analysis (added during M7)
### Milestone FE-5 — Track Management + Projects
### Milestone FE-6 — Enrichment + Logs + Network Pages
### ~~Milestone 7 — Event Detection (Layer 1A, Tier 2)~~ → IN PROGRESS (2026-03-20)
**Status:** PARTIALLY COMPLETE — core framework, 5 detectors, pipeline integration, eval harness, API, and dev tuning page all implemented. Needs real-world tuning against ground truth.

#### Deliverables
- [x] `DetectorProtocol` — pluggable interface for swappable detection strategies
- [x] `DrumPattern` — compact percussion storage (16th-note slot arrays per bar, ~10KB vs ~300KB per track)
- [x] `DetectorConfig` — YAML-driven config with active strategies, params, section priors (`config/detectors.yaml`)
- [x] Heuristic percussion detector — beat-synchronous slot classification using sub-band energy, onset gating, spectral centroid
- [x] Random Forest percussion detector — 7-dim feature vectors per slot, heuristic fallback when model file missing
- [x] Riser detector — spectral centroid slope + R² threshold over sliding windows
- [x] Faller detector — falling centroid + RMS decay + spectral flatness discrimination
- [x] Stab detector — HPSS harmonic ratio at onset points + centroid + duration filter
- [x] HPSS (Harmonic-Percussive Source Separation) added to AudioFeatures extraction
- [x] Pipeline integration — event detection as step 9/10 in `run_analysis()`
- [x] Eval harness — `eval_detectors.py` with precision/recall/F1 scoring, A/B strategy comparison
- [x] `GET /api/tracks/{fingerprint}/events` — API endpoint for events + drum patterns
- [x] Detector Tuning Page — dev-facing UI at `/dev/detectors` with TrackPicker, EventTimeline (waveform + event overlay), EventControls (toggles, confidence slider), EventStats
- [x] Sidebar "Dev" section with Detectors link
- [x] Per-step progress reporting through full stack (backend → API → frontend)
- [ ] Ground truth JSON annotations for reference tracks
- [ ] RF model training from ground truth
- [ ] Real-world tuning pass (adjust thresholds, compare heuristic vs RF)

#### Key Files
- `scue/layer1/detectors/events.py` — framework: DrumPattern, DetectorResult, DetectorConfig, DetectorProtocol
- `scue/layer1/detectors/percussion_heuristic.py` — heuristic percussion detector
- `scue/layer1/detectors/percussion_rf.py` — RF percussion detector
- `scue/layer1/detectors/tonal.py` — riser, faller, stab detectors
- `scue/layer1/eval_detectors.py` — eval harness CLI
- `config/detectors.yaml` — detector configuration
- `frontend/src/pages/DetectorTuningPage.tsx` — dev tuning page
- `frontend/src/components/detectors/` — EventTimeline, EventControls, EventStats
- `frontend/src/types/events.ts` — frontend event types

#### Bug Fixes During M7
- **Event loop blocking:** `_run_analysis_task` was `async def`, blocking the event loop during CPU-bound analysis. Changed to `def` so FastAPI runs it in thread pool.
- **EventTimeline waveform rendering:** Drew three stacked color layers (ADR-018 anti-pattern). Rewrote to Pioneer-correct single blended bar approach.

### Test Audio Fixture Infrastructure (2026-03-20)
**Status:** COMPLETE — directory structure and manifest created. Assets not yet populated.

- [x] `tests/fixtures/audio/` directory with 7 subdirectories (full-tracks, loops, one-shots, stems, edge-cases, pioneer, formats)
- [x] Audio file extensions gitignored (wav, mp3, flac, aiff, ogg, m4a, aac)
- [x] `MANIFEST.md` — comprehensive inventory of needed test assets, categorized by content type, what each exercises in the pipeline, format/fidelity matrix, and population priority
- [ ] Populate assets (full-tracks, loops, one-shots, stems, edge-cases, pioneer exports, format variants)

### ~~Waveform Rendering Tuning Page~~ → COMPLETE (2026-03-24)
**Status:** COMPLETE — research, spec, and implementation all done.

Dev page at `/dev/waveforms` for real-time tuning of waveform rendering parameters: frequency weighting, amplitude compression, normalization strategy, and color mapping. Includes preset management (YAML storage, CRUD API) and Pioneer ANLZ reference comparison. Active preset applied app-wide to all waveform components.

- [x] Research: psychoacoustics, Pioneer waveform encoding, perceptual weighting (research/findings-waveform-frequency-color-rendering.md)
- [x] Skill doc: waveform rendering domain knowledge (skills/waveform-rendering.md)
- [x] Feature spec (specs/feat-waveform-tuning-page/spec.md)
- [x] Backend: preset CRUD API (6 endpoints) + YAML storage (`scue/api/waveform_presets.py`)
- [x] Frontend: WaveformTuningPage, ParameterControls (3 groups), PresetBar (save/save-as/load/activate/delete)
- [x] Frontend: modified WaveformCanvas accepting optional `WaveformRenderParams` with full rendering pipeline (per-band normalization, amplitude scaling, 3 color modes, gain/saturation/brightness)
- [x] Frontend: Pioneer reference waveform renderer (from ANLZ PWV5 data, scroll/zoom synced)
- [x] Frontend: waveformPresetStore (Zustand) with draftParams for tuning page, activePreset for app-wide use
- [x] Integration: AnalysisViewer + DeckWaveform read active preset from store
- [x] Seed presets: SCUE Default, Pioneer RGB Match, Pioneer 3-Band, High Detail (`config/waveform-presets.yaml`)
- [x] ADR-019: Frontend-time waveform rendering parameters (docs/DECISIONS.md)
- [x] TypeScript strict mode passes

#### Key Files
- `specs/feat-waveform-tuning-page/spec.md` — full specification
- `scue/api/waveform_presets.py` — backend preset CRUD API
- `config/waveform-presets.yaml` — preset storage (4 seed presets)
- `frontend/src/pages/WaveformTuningPage.tsx` — main page
- `frontend/src/components/waveformTuning/` — ParameterControls, PresetBar, PioneerReferenceWaveform
- `frontend/src/stores/waveformPresetStore.ts` — Zustand preset store
- `frontend/src/types/waveformPreset.ts` — WaveformRenderParams, WaveformPreset types
- `frontend/src/components/shared/WaveformCanvas.tsx` — modified renderer (accepts renderParams)

---

### Milestone 8 — Full Cue Vocabulary
### Milestone 9 — OSC Visual Output (Layer 4B)
### Milestone 10 — Real-Time User Override UI (Layer 4C)
### Milestone 11 — Polish & Tier 3 Features
