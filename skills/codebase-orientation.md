---
name: SCUE Codebase Orientation
description: File map, data flows, feature status, and key gotchas for the SCUE project. Load at session start for any SCUE work.
trigger: Any SCUE-related task
---

# SCUE Codebase Orientation

Automated lighting/laser/visual cue generation for live DJ sets. 5-layer architecture + React frontend.

**Project root:** `projects/DjTools/scue/`

## File-to-Responsibility Map

### Layer 0 — Beat-Link Bridge (Java subprocess + Python adapter)

#### Java Bridge (`bridge-java/src/main/java/com/scue/bridge/`)
| File | Responsibility |
|------|----------------|
| `BeatLinkBridge.java` | Main class: CLI args, network interface auto-detection with scoring, DeviceFinder/VirtualCdj/BeatFinder startup, Finder lifecycle (Timer/Metadata/BeatGrid/Waveform/AnalysisTag/Art), listener registration, DLP device detection |
| `MessageEmitter.java` | Constructs typed JSON message envelopes and broadcasts via WebSocket. Emits: bridge_status, device_found/lost, player_status, beat, track_metadata, beat_grid, waveform_detail, track_waveform, phrase_analysis, cue_points |
| `BridgeWebSocketServer.java` | java-websocket server on localhost, broadcasts JSON to all connected Python clients |

**Bridge JAR:** `lib/beat-link-bridge.jar` (pre-built artifact, v2.0.0). Uses beat-link 8.1.0-SNAPSHOT with native XDJ-AZ support.

#### Python Bridge Layer (`scue/bridge/`)
| File | Responsibility |
|------|----------------|
| `messages.py` | `BridgeMessage` dataclass + 11 typed payload dataclasses (DevicePayload, PlayerStatusPayload, BeatGridPayload, etc.). Message type constants. `parse_message()` / `parse_typed_payload()` |
| `adapter.py` | **Stateful adapter.** Accumulates per-player state (PlayerState) from message stream. Computes `playback_position_ms` from beat_number + beat_grid interpolation. Fires callbacks: `on_device_change`, `on_player_update`, `on_beat`, `on_track_loaded`. Synthesizes DeviceInfo from player_status when device_found was missed |
| `client.py` | WebSocket client (`BridgeWebSocket`). Connects to `ws://localhost:17400`, yields `BridgeMessage` via async generator |
| `manager.py` | **Subprocess lifecycle.** States: stopped/starting/running/crashed/no_jre/no_jar/fallback/waiting_for_hardware. Exponential backoff restart. Health check loop (bridge WS silence, NOT Pioneer silence). Route checking/auto-fixing. `to_status_dict()` for API/WS |
| `fallback.py` | Direct UDP Pro DJ Link parser (degraded mode). Parses keep-alive + status packets. Emits device_found, player_status, beat only (no metadata/waveforms). Used when JRE/JAR absent |
| `recorder.py` | `MessageRecorder` — captures live bridge messages to JSONL fixture files for replay |
| `__init__.py` | Re-exports `BridgeAdapter`, `BridgeManager` |

### Layer 1 — Track Analysis (1A: offline) + Live Tracking (1B: real-time)

#### Core (`scue/layer1/`)
| File | Responsibility |
|------|----------------|
| `models.py` | All data models: `TrackAnalysis` (primary persisted object), `Section`, `MusicalEvent`, `TrackFeatures`, `RGBWaveform`, `TrackCursor` (Layer 1 -> Layer 2 contract), `SectionInfo`, `BeatPosition`, `PlaybackState`, `DivergenceRecord`. Serialization helpers |
| `analysis.py` | **Pipeline orchestrator.** 10-step pipeline: fingerprint -> features -> structure -> boundaries -> merge -> snap -> classify -> score -> events -> waveform. Coordinates detectors, does not contain detection logic |
| `storage.py` | `TrackStore` (JSON files, source of truth, keyed by SHA256 fingerprint) + `TrackCache` (SQLite derived index). Tables: tracks, track_ids (composite PK: source_player/source_slot/rekordbox_id), pioneer_metadata, divergence_log, analysis_jobs, settings. Schema migrations |
| `tracking.py` | **Layer 1B.** `PlaybackTracker`: bridge adapter PlayerState -> TrackCursor. Detects track changes via rekordbox_id, resolves fingerprint via composite key, triggers enrichment on first load. On-air-only cursor (ADR-006) |
| `cursor.py` | `build_cursor()`: maps playback position into TrackAnalysis sections/events, computes section progress, sliding window of upcoming events |
| `enrichment.py` | Pioneer enrichment pass: swaps beatgrid/BPM/key from Pioneer, re-aligns section boundaries, stores as new versioned entry (never overwrites original). Logs divergence |
| `divergence.py` | `log_divergence()`: persists SCUE vs Pioneer mismatches to SQLite for detector bias analysis |
| `fingerprint.py` | SHA256 of raw audio file bytes (not decoded samples). Primary key for all storage |
| `waveform.py` | RGB waveform: 3-band (low/mid/high) at 150 FPS, frequency crossovers matching Pioneer mixer EQ (20-200Hz / 200-2500Hz / 2500Hz+) |
| `usb_scanner.py` | Reads Pioneer exportLibrary.db via rbox + export.pdb for DeviceSQL. Dual-namespace scanning for mixed hardware. ANLZ parsing (pyrekordbox primary, custom parser fallback). Matches USB tracks to SCUE analyses by path/title/artist |
| `anlz_parser.py` | Zero-dep ANLZ binary file parser (PQTZ beat grid + PCOB cue list). Fallback when pyrekordbox fails |
| `__init__.py` | Public API: exports TrackAnalysis, TrackCursor, TrackStore, TrackCache, PlaybackTracker, etc. Layer 2 imports only from here |

#### Detectors (`scue/layer1/detectors/`)
| File | Responsibility |
|------|----------------|
| `events.py` | Framework: `DetectorProtocol`, `DetectorConfig`, `DetectorResult`, `DrumPattern` (compact 16th-note percussion storage). Config loading from `config/detectors.yaml` |
| `features.py` | `AudioFeatures` dataclass + `extract_all()` (librosa). HPSS, spectral, rhythmic features. `get_section_features()` / `get_track_stats()` |
| `sections.py` | `analyze_structure()` (allin1-mlx or fallback), `detect_boundaries()` (ruptures change-point), `merge_boundaries()` |
| `flow_model.py` | EDM flow model: relabels sections to intro/verse/build/drop/breakdown/fakeout/outro based on energy trajectory |
| `snap.py` | 8-bar grid snapping pass. Flags irregular phrases |
| `percussion_heuristic.py` | Beat-synchronous percussion detection: sub-band energy, onset gating, spectral centroid |
| `percussion_rf.py` | Random Forest percussion detector: 7-dim feature vectors per slot. Falls back to heuristic when model file missing |
| `tonal.py` | Riser (spectral centroid slope + R²), Faller (falling centroid + RMS decay), Stab (HPSS harmonic ratio at onsets) detectors |

#### Other Layer 1
| File | Responsibility |
|------|----------------|
| `eval_detectors.py` | CLI eval harness: precision/recall/F1 scoring, A/B strategy comparison |

### API Layer (`scue/api/`)
| File | Responsibility |
|------|----------------|
| `tracks.py` | REST: `GET /api/tracks` (list from SQLite), `GET /api/tracks/{fp}` (full JSON), `POST /api/tracks/analyze`, `POST /api/tracks/scan`, `POST /api/tracks/analyze-batch`, `GET /api/tracks/jobs/{id}`, `GET /api/tracks/{fp}/events` |
| `bridge.py` | REST: `GET /api/bridge/status`, `PUT /api/bridge/settings`, `POST /api/bridge/restart`, `POST /api/bridge/record/start|stop` |
| `network.py` | REST: `GET /api/network/interfaces` (scored), `GET /api/network/route`, `POST /api/network/route/fix`, `GET /api/network/route/setup-status` |
| `usb.py` | REST: `POST /api/usb/scan`, `GET /api/usb/status`, `GET /api/usb/pioneer-metadata` |
| `filesystem.py` | REST: `GET /api/filesystem/browse` (server-side directory listing for folder picker UI) |
| `ws.py` | WebSocket endpoint `/ws`. Sends `bridge_status` on every change + periodic `pioneer_status` every 2s. Dispatches `WSManager.broadcast()` |
| `ws_manager.py` | `WSManager`: manages WebSocket connections, broadcasts typed JSON to all connected frontend clients |
| `jobs.py` | In-memory `AnalysisJob` tracker for batch analysis. Persisted to SQLite for restart survival |

### Application Entry (`scue/`)
| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI app. Startup: loads config, inits TrackStore/TrackCache, creates BridgeManager, wires adapter callbacks to PlaybackTracker, creates WSManager, starts bridge, resumes incomplete jobs |
| `config/loader.py` | Typed YAML config: `ScueConfig` with `ServerConfig`, `BridgeConfig` (port, network_interface, route, watchdog, health, restart), `UsbConfig`. Defaults on missing files |

### Network (`scue/network/`)
| File | Responsibility |
|------|----------------|
| `route.py` | macOS broadcast route: `check_route()`, `fix_route()`, `enumerate_interfaces()` with scoring (link-local +10, ethernet +5). `netstat -rn` primary (not `route get` which is unreliable). Sudoers/launchd checks |
| `models.py` | Dataclasses: `NetworkInterfaceInfo`, `RouteCheckResult`, `RouteFixResult`, `RouteStatus` |

### Frontend (`frontend/src/`)

#### Pages
| File | Route | Status |
|------|-------|--------|
| `pages/TracksPage.tsx` | `/data/db` | COMPLETE. TanStack Table, search, analyze panel |
| `pages/BridgePage.tsx` | `/data/bridge` | COMPLETE. Status, devices, players, interface selector, route fix |
| `pages/AnalysisViewerPage.tsx` | `/analysis` | READY (spec). Waveform + section overlay + metadata |
| `pages/LiveDeckMonitorPage.tsx` | `/live` | READY (spec). 2-deck real-time waveform + cursor |
| `pages/DetectorTuningPage.tsx` | `/dev/detectors` | COMPLETE. Event timeline, controls, stats |
| `pages/EnrichmentPage.tsx` | `/data/enrichment` | Placeholder |
| `pages/LogsPage.tsx` | `/logs` | Placeholder |
| `pages/NetworkPage.tsx` | `/network` | Placeholder |

#### Stores (Zustand, independent silos)
| File | Responsibility |
|------|----------------|
| `stores/bridgeStore.ts` | Bridge status, devices, players, dotStatus, isStartingUp, isRecovering, countdown. Updated by WS messages |
| `stores/consoleStore.ts` | Console log entries from WS messages |
| `stores/analyzeStore.ts` | Batch analysis flow state (3-phase: path input -> scan -> progress) |
| `stores/folderStore.ts` | Folder browser state for track organization |
| `stores/uiStore.ts` | UI state (sidebar collapse, console toggle) |

#### API / WebSocket
| File | Responsibility |
|------|----------------|
| `api/ws.ts` | WebSocket client with auto-reconnect + exponential backoff. Dispatches typed messages to stores. Components never touch WS directly |
| `api/client.ts` | Axios base URL config |
| `api/tracks.ts` | TanStack Query hooks for track CRUD |
| `api/analyze.ts` | Analysis job API calls |
| `api/network.ts` | `useInterfaces()`, `useRouteStatus()`, `useRouteSetupStatus()` hooks. All accept `{ enabled }` for startup gating |
| `api/queryClient.ts` | TanStack QueryClient singleton |

#### Components
| Directory | Key Components |
|-----------|---------------|
| `components/layout/` | `Shell` (sidebar + topbar + outlet + console), `Sidebar`, `TopBar` (StatusDot, TrafficDot, StartupIndicator), `Console`, `ConsolePanel`, `LogEntry` |
| `components/bridge/` | `BridgeStatusPanel`, `HardwareSelectionPanel`, `DeviceList`/`DeviceCard`, `PlayerList`/`PlayerCard`, `InterfaceSelector`/`InterfaceRow`, `StatusBanner`, `RouteStatusBanner`, `ActionBar` |
| `components/analysis/` | `AnalysisViewer`, `TrackPicker`, `SectionList`, `TrackMetadataPanel` |
| `components/live/` | `DeckPanel`, `DeckWaveform`, `DeckMetadata`, `DeckEmptyState` |
| `components/detectors/` | `EventTimeline` (waveform + event overlay), `EventControls` (toggles + threshold), `EventStats` |
| `components/shared/` | `Button`, `WaveformCanvas`, `FolderBrowser`, `PlaceholderPanel`, `SectionIndicator` |
| `components/tracks/` | `TrackTable` (TanStack Table), `TrackToolbar`, `AnalyzePanel` (3-phase batch UI) |

#### Types (`frontend/src/types/`)
| File | Defines |
|------|---------|
| `bridge.ts` | `BridgeStatus`, `BridgeState`, `DeviceInfo`, `PlayerInfo` |
| `track.ts` | `Track`, `TrackAnalysis` (mirrors Python) |
| `events.ts` | `MusicalEvent`, `DrumPattern`, `TrackEventsResponse`, `EVENT_COLORS` |
| `ws.ts` | `WSMessage` union type (bridge_status, pioneer_status) |
| `analyze.ts` | Analyze flow types |
| `console.ts` | Console entry types |
| `index.ts` | Re-exports |

### Configuration (`config/`)
| File | Contents |
|------|----------|
| `server.yaml` | CORS origins, audio extensions, tracks_dir, cache_path |
| `bridge.yaml` | `network_interface`, port, route auto_fix, watchdog thresholds, health check interval, restart backoff |
| `usb.yaml` | USB relative paths (exportLibrary.db, export.pdb, USBANLZ) |
| `detectors.yaml` | Active strategies (percussion: heuristic/rf, riser, faller, stab), per-detector params, section priors |

### Tools (`tools/`)
| File | Purpose |
|------|---------|
| `mock_bridge.py` | WebSocket replay server: plays JSONL fixture files for testing without hardware |
| `analyze_track.py` | CLI: `python tools/analyze_track.py <path>` |
| `pdb_lookup.py` | Utility for querying Pioneer PDB files |
| `recorder.html` | Browser dev tool for bridge message recording |
| `fix-djlink-route.sh` | macOS route fix script (sudoers-whitelisted) |
| `install-route-fix.sh` | Installs sudoers entry + launchd agent for auto route fix |

### Layers 2-4 (Stubs)
| Package | Status |
|---------|--------|
| `scue/layer2/generators/` | Empty `__init__.py`. Awaiting M3 (Cue Stream) |
| `scue/layer3/effects/` | Empty `__init__.py`. Awaiting M4 (Effect Engine) |
| `scue/layer4/adapters/` | Empty `__init__.py`. Awaiting M5 (DMX Output) |

---

## Data Flow Chains

### 1. Bridge -> Frontend (real-time playback)
```
Pioneer Hardware (Pro DJ Link UDP)
  -> Java BeatLinkBridge (beat-link library)
    -> BridgeWebSocketServer (localhost:17400, JSON)
      -> Python BridgeWebSocket (client.py)
        -> BridgeManager._listen_loop() (manager.py)
          -> BridgeAdapter.handle_message() (adapter.py)
            -> Accumulates PlayerState per player
            -> Fires on_player_update, on_track_loaded, on_beat callbacks
              -> PlaybackTracker.on_player_update() (tracking.py)
                -> Resolves fingerprint via composite key
                -> Triggers enrichment on first load
                -> Returns TrackCursor (-> Layer 2, future)
          -> BridgeManager._notify_state_change()
            -> WSManager.broadcast() (ws_manager.py)
              -> FastAPI WebSocket /ws
                -> Frontend api/ws.ts dispatch()
                  -> bridgeStore.setBridgeState() (bridge_status messages)
                  -> bridgeStore.setPioneerStatus() (pioneer_status messages)
                  -> consoleStore (all messages logged)
                    -> UI components re-render via Zustand selectors
```

### 2. Offline Analysis Pipeline
```
Audio File (.mp3/.wav/.flac/.aiff)
  -> POST /api/tracks/analyze (or analyze-batch)
    -> run_analysis() (analysis.py)
      1. compute_fingerprint() -> SHA256 (primary key)
      2. extract_all() -> AudioFeatures (librosa)
      3. analyze_structure() -> allin1-mlx or fallback
      4. detect_boundaries() -> ruptures change-points
      5. merge_boundaries() -> combined sections
      6. snap_to_8bar_grid() -> grid-aligned, irregular flagged
      7. classify_sections() -> EDM flow model labels
      8. _score_confidence() -> weighted by source agreement
      9. _run_event_detection() -> percussion, riser, faller, stab
      10. compute_rgb_waveform() -> 3-band at 150fps
    -> TrackStore.save() -> tracks/{fingerprint}.json (source of truth)
    -> TrackCache.index_analysis() -> SQLite (derived index)
```

### 3. Track Resolution (composite key)
```
Player loads track on Pioneer hardware
  -> player_status message with rekordbox_id, source_player, source_slot
    -> PlaybackTracker._load_track_for_player()
      -> TrackCache.lookup_fingerprint(rekordbox_id, source_player, source_slot)
        -> Falls back to "dlp" and "devicesql" namespaces
          -> Returns fingerprint (SHA256)
            -> TrackStore.load_latest(fingerprint)
              -> Returns TrackAnalysis

Pre-set: USB scan populates the mapping
  POST /api/usb/scan
    -> usb_scanner.read_usb_library() (rbox OneLibrary)
      -> match_usb_tracks() (path stem + title/artist matching)
        -> TrackCache.link_rekordbox_id() (composite key: source_player/source_slot/rekordbox_id -> fingerprint)
        -> TrackCache.store_pioneer_metadata() (beatgrid, cues, waveforms)
```

### 4. Pioneer Enrichment
```
Track first loaded on deck (tracking.py)
  -> Looks up cached Pioneer metadata from USB scan
  -> run_enrichment_pass() (enrichment.py)
    -> Swaps BPM, beatgrid, key from Pioneer
    -> Re-aligns section boundaries to Pioneer grid
    -> Logs DivergenceRecord for each differing field
    -> TrackStore.save() as version N+1 (source="pioneer_enriched")
    -> NEVER overwrites original analysis
```

---

## Feature Completion Status

### COMPLETE
| Milestone | What |
|-----------|------|
| M0 | Beat-Link Bridge (Python side): messages, adapter, client, manager, fallback, recorder |
| M0 (Java) | Bridge JAR v2.0.0: all Finders enabled, XDJ-AZ native support, DLP detection |
| M0B | USB Scanner: rbox, dual-namespace (DLP+DeviceSQL), ANLZ parsing, track matching |
| M1 | Analysis Pipeline: sections, 8-bar snap, flow model, fingerprint storage, RGB waveform |
| M2 | Live Cursor + Pioneer Enrichment: TrackCursor, enrichment pass, divergence logging |
| M7 | Event Detection (core): 5 detectors, pipeline integration, eval harness, API, tuning page |
| FE-1 | Shell + Routing |
| FE-3 | Track Table (TanStack Table, search, sort) |
| FE-4 | Upload & Analyze Flow (scan, batch, progress) |
| FE-BLT | Bridge Page (status, devices, players, interface selector, route fix) |
| FE-2 | WebSocket + bridgeStore (partially: console log streaming still placeholder) |
| Audit | Fallback wiring, synthetic device creation, API tests, config consolidation |
| Research | Waveform sources, DLP track IDs, bridge data strategy (11 findings) |

### IN PROGRESS / READY
| Item | Status | Notes |
|------|--------|-------|
| M7 tuning | Needs ground truth JSON annotations, RF model training, real-world threshold tuning |
| FE-Analysis-Viewer | READY (spec complete, 8 tasks). Waveform + section overlay. Blocked: needs building |
| FE-Live-Deck-Monitor | READY (spec complete, 7 tasks). 2-deck real-time waveform. Depends on Analysis Viewer for shared WaveformCanvas |

### BLOCKED / FUTURE
| Item | Status |
|------|--------|
| M3 (Cue Stream, Layer 2) | BLOCKED on Analysis Viewer + Live Deck Monitor to validate data pipeline |
| M4 (Effect Engine, Layer 3) | Future |
| M5 (DMX Output, Layer 4) | Future |
| M6 (End-to-End Demo) | Future |
| FE-2 Console | Console panel wired to real-time bridge log output (currently placeholder) |
| FE-5 (Track Management) | Future |
| FE-6 (Enrichment + Logs + Network pages) | Placeholder pages exist |

---

## Cross-Layer Pipeline Skeleton

When adding a new message type that flows from hardware to UI, these files change in order:

| Step | Layer | File | What to add |
|------|-------|------|-------------|
| 1 | Java bridge | `BeatLinkBridge.java` | Listener registration for the new data |
| 2 | Java bridge | `MessageEmitter.java` | New `emit*()` method with JSON envelope |
| 3 | Python bridge | `messages.py` | New payload dataclass + message type constant |
| 4 | Python bridge | `adapter.py` | Handler in `_handle_message()` + state update + callback |
| 5 | Python API | `scue/api/{domain}.py` | New REST endpoint or WS message type |
| 6 | Frontend types | `frontend/src/types/{domain}.ts` | TypeScript interface matching Python dataclass |
| 7 | Frontend store | `frontend/src/stores/{domain}Store.ts` | WS message handler + state slice |
| 8 | Frontend component | `frontend/src/components/{domain}/` | UI component consuming the store |

This pattern has been repeated for: `player_status`, `beat_grid`, `waveform_detail`, `track_waveform`, `phrase_analysis`, `cue_points`. Follow an existing example (e.g., `waveform_detail`) as a template.

---

## Key Gotchas

### Bridge / Pro DJ Link
1. **XDJ-AZ reports 658.63 BPM when no track loaded.** `getEffectiveTempo()` returns garbage for `NO_TRACK` state. Guard with `rekordbox_id == 0` or `playback_state == "NO_TRACK"`.

2. **TimeFinder is unreliable over DLP/NFS.** Compute position from `beat_number + beatgrid` Python-side instead. The adapter's `_compute_position_ms()` interpolates from the ANLZ beat grid.

3. **beat-link Finder start order matters.** Correct order: `DeviceFinder` -> `VirtualCdj` -> `BeatFinder` -> then all Finders (TimeFinder, MetadataFinder, BeatGridFinder, WaveformFinder, AnalysisTagFinder, ArtFinder).

4. **`bridge.yaml` `network_interface` is hardcoded, not auto-detected.** If the USB-Ethernet adapter changes, the config file must be updated. The Java bridge auto-detects with scoring, but the Python side passes the configured value.

5. **macOS link-local broadcast routing requires manual fix.** `sudo route add -host 169.254.255.255 -interface en16` (or use `tools/install-route-fix.sh` for persistent sudoers entry). Without this, beat-link never discovers devices. The bridge manager auto-fixes on startup if `route.auto_fix: true` in config and sudoers is installed.

6. **BLUE-style waveforms on XDJ-AZ, not THREE_BAND.** WaveformFinder returns BLUE-style data (3 bytes per sample: low/mid/high, range 0-31). The adapter decodes this in `_handle_track_waveform()`.

7. **Bridge Java stderr is invisible.** Stdout/stderr are piped but not drained by the Python side. Use `/tmp` file write for Java-side debugging.

8. **Synthetic device creation.** If Python connects to the bridge WS after device discovery already happened, `device_found` events are missed. The adapter synthesizes `DeviceInfo` from `player_status` messages to keep the device list accurate.

9. **`netstat -rn` is the reliable route check, not `route get`.** `route get 169.254.255.255` returns stale/wrong results on macOS for link-local broadcast. The network module uses `netstat -rn` as primary source.

### Analysis / Layer 1
10. **`async def` vs `def` for CPU-bound FastAPI endpoints.** Use `def` (not `async def`) for analysis endpoints so FastAPI runs them in a thread pool. `async def` blocks the event loop during CPU-bound work. Alternatively use `asyncio.to_thread()`.

11. **Track IDs are volatile across USB re-exports.** rekordbox_id values change when a USB is re-exported. Composite key `(source_player, source_slot, rekordbox_id)` is REQUIRED. Never use rekordbox_id alone.

12. **JSON files are source of truth, SQLite is derived.** If the SQLite DB is deleted, rebuild from JSON via `TrackCache.rebuild_from_store()`. Never modify SQLite without updating JSON first.

13. **Enrichment never overwrites.** Pioneer enrichment creates a new versioned entry (v2, v3...) alongside the original. `TrackStore.load_latest()` returns the highest version.

14. **allin1-mlx is optional.** Falls back to librosa-only with ruptures change-point detection. Confidence is scaled by 0.7 in fallback mode. allin1-mlx is MLX (Apple Silicon only) — will need PyTorch/ONNX for Windows.

### Frontend
15. **Startup gating.** All TanStack Query hooks that hit the backend must gate with `enabled: !isStartingUp`. `isStartingUp` is true while WS is not open OR bridge status is "starting".

16. **Stores are independent silos.** No Zustand store imports another store. Cross-store coordination happens in `api/ws.ts` dispatch or in components.

17. **`dotStatus` reflects bridge status, not Pioneer traffic.** Green = "running", yellow = "fallback"/"waiting_for_hardware", red = everything else. Do not confuse with `isReceiving` (separate TrafficDot indicator).

---

## Test Landscape

### Backend Tests (`tests/`)
```
tests/
  conftest.py               # Shared fixtures
  test_bridge/              # 7 test files, ~120 tests
    test_messages.py         # Message parsing, typed payloads
    test_adapter.py          # PlayerState accumulation, callbacks, position computation
    test_manager.py          # Subprocess lifecycle, state transitions, health check
    test_fallback.py         # UDP parser, packet parsing
    test_integration.py      # End-to-end bridge message flow
    test_reconnection.py     # Reconnect/backoff behavior
    test_network_interface.py # Interface scoring, route mocking
  test_layer1/              # 13 test files, ~160 tests
    test_analysis.py         # Full pipeline run
    test_analysis_edge_cases.py # Edge cases (6 skipped: librosa not in test env)
    test_models.py           # Serialization round-trip
    test_storage.py          # JSON + SQLite CRUD, composite keys
    test_fingerprint.py      # SHA256 consistency
    test_cursor.py           # Section lookup, progress computation
    test_enrichment.py       # Pioneer enrichment pass, divergence logging
    test_tracking.py         # PlaybackTracker, track change detection
    test_divergence.py       # DivergenceRecord persistence
    test_snap.py             # 8-bar grid snapping
    test_flow_model.py       # EDM flow model classification
    test_usb_scanner.py      # USB scanning, track matching
    test_anlz_parser.py      # ANLZ binary parsing
  test_api/                 # 2 test files, ~20 tests
    test_bridge_api.py       # Bridge REST endpoints
    test_tracks_api.py       # Tracks REST endpoints
  test_config/
    test_loader.py           # YAML config loading
  test_layer2/              # Empty (Layer 2 not implemented)
  test_layer3/              # Empty
  test_layer4/              # Empty
```

**Run commands:**
- All tests: `python -m pytest tests/`
- Bridge only: `python -m pytest tests/test_bridge/ -v`
- Layer 1 only: `python -m pytest tests/test_layer1/ -v`
- Last known count: 304 passed, 11 skipped

**Test fixtures:** `tests/fixtures/bridge/` (JSONL bridge message recordings). Audio fixtures in `tests/fixtures/audio/` (gitignored, see `MANIFEST.md` for inventory).

### Frontend Tests
- `frontend/src/stores/__tests__/bridgeStore.test.ts` — bridgeStore state transitions
- Run: `cd frontend && npm test`
- Coverage: minimal (bridgeStore only)

### Known Test Gaps
- No integration tests for the full bridge -> adapter -> tracker -> enrichment flow with real fixture data
- No frontend component tests beyond bridgeStore
- Event detector tests depend on audio fixtures not yet populated
- Layer 2/3/4 test directories exist but are empty (layers not implemented)

---

## Quick Reference

### Commands
```bash
# Backend
uvicorn scue.main:app --reload              # Dev server (port 8000)
python -m pytest tests/ -v                  # All tests
python tools/mock_bridge.py                 # Replay bridge fixtures
python tools/analyze_track.py <path>        # CLI analysis

# Frontend
cd frontend && npm run dev                  # Dev server (port 5173)
cd frontend && npm run build                # Production build
cd frontend && npm run typecheck            # TypeScript checking
```

### Key Config Files
- `config/bridge.yaml` -> network_interface, port, route settings
- `config/server.yaml` -> tracks_dir, cache_path, CORS
- `config/detectors.yaml` -> active detection strategies and params

### Important Paths
- Track analyses (JSON): `tracks/{fingerprint}.json`
- SQLite cache: `cache/scue.db`
- Bridge JAR: `lib/beat-link-bridge.jar`
- Feature specs: `specs/feat-*/`
- Architecture docs: `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/DECISIONS.md`
