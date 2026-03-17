# Architectural Decision Records (ADRs)

## ADR-001: Pioneer beatgrid as source of truth over librosa
Date: 2025-03
Context: librosa beat tracking drifts on tempo-variable tracks; Pioneer grids are hand-verified by the DJ in rekordbox and are more reliable.
Decision: The librosa-derived beatgrid from offline analysis serves as the working reference during analysis and as a fallback when Pioneer data is unavailable. When a track is first loaded on Pioneer hardware, the Pioneer enrichment pass replaces the librosa beatgrid with the Pioneer beatgrid. SCUE's original analysis is kept (versioned) — the Pioneer-enriched version is stored alongside it, not in place of it.
Consequences: Layer 1B must trigger the enrichment pass on first track load. TrackCursor reads from the enriched analysis if available, falling back to the raw offline analysis. All divergences between SCUE and Pioneer data must be logged via DivergenceRecord.

## ADR-002: Fixed-rate main loop (40Hz) with beat injection
Date: 2025-03
Context: Beat-synchronized ticks (variable rate depending on BPM) complicate timer logic and produce variable-rate output. Fixed-rate is simpler and gives smoother continuous effects.
Decision: The real-time processing loop ticks at 40Hz (every 25ms). Beat events from the TrackCursor are injected into the cue engine as discrete events when they occur. Effects that need beat sync reference the beat grid via the cursor, not the tick rate.
Consequences: Layer 2 cue generators receive both tick callbacks and beat event callbacks.

## ADR-003: YAML for all configuration; no hardcoded effect/fixture values
Date: 2025-03
Context: Effect definitions, fixture profiles, routing tables, and palettes need to be user-editable without code changes.
Decision: All configuration lives in `config/`. Effect definitions, fixture profiles, venue layouts, routing tables, and palettes are YAML files. Python code implements the runtime machinery; YAML files define the data. Adding a new effect type, fixture, or routing rule should not require touching Python.
Consequences: All config-loading code must handle missing or malformed YAML gracefully. Ship defaults for all config categories.

## ADR-004: JSON files as source of truth; SQLite as derived cache
Date: 2025-03
Context: Track analysis data needs to be portable, inspectable, and resilient. SQLite is convenient for queries but opaque and harder to debug.
Decision: Track analysis is stored as JSON files in the project's `tracks/` directory, keyed by audio fingerprint (SHA256). SQLite in `cache/` is a derived index rebuilt from JSON files. If the SQLite DB is deleted, nothing is lost — it's rebuilt on next project open.
Consequences: All writes go to JSON first, then update SQLite. Any query that needs full analysis detail reads from JSON. SQLite is only for table views, search, and filtering of flattened track metadata.

## ADR-005: beat-link as managed subprocess, not direct UDP or JPype
Date: 2025-03
Context: Direct Pro DJ Link UDP parsing (POC approach) only gets basic data: BPM, pitch, beat position, play state. Full protocol access (metadata, waveforms, cue points, phrase analysis) requires beat-link. Three options considered: JPype (fragile, crash isolation issues), porting beat-link to Python (years of work), managed subprocess + WebSocket (clean process boundary).
Decision: Embed the beat-link Java library as a managed subprocess. The bridge is a small Java app (single JAR) that connects to Pro DJ Link, translates events to typed JSON, and streams over a local WebSocket. Python adapter normalizes into Layer 1 types. Fallback to basic UDP parsing if bridge unavailable.
Consequences: Requires JRE on host. Bridge JAR is a pre-built artifact in `lib/`. Bridge crash doesn't take down SCUE — auto-restart with backoff. The POC's direct UDP parser is preserved as `bridge/fallback.py` for degraded mode.

## ADR-006: Multi-deck DeckMix with weighted cursors
Date: 2025-03
Context: During DJ transitions, two tracks play simultaneously. Layer 2 needs to blend cue streams from both decks proportionally.
Decision: Layer 1B tracks all active decks simultaneously and produces a `DeckMix` with per-deck `WeightedCursor` objects. Layer 2 generates cues per-deck and blends via a cue mixer using deck weights. Phase 1: master-only (weight 1.0 for master, 0.0 for others). Phase 2: crossfade blend based on on-air/crossfader state. Phase 3: manual weight assignment.
Consequences: TrackCursor infrastructure must support multiple simultaneous cursors from day one. Weight calculation strategy is configurable in project settings (`mix_mode`).

## ADR-007: Path-based analyze flow instead of file upload
Date: 2026-03
Context: SCUE runs locally and audio files are already on the local filesystem. A drag-and-drop upload would redundantly copy large audio files.
Decision: The analyze flow uses path-based input — user provides a directory path (typed or via server-side filesystem browser), backend scans it, then analyzes new files in place. No file copying or upload.
Consequences: Requires a server-side filesystem browse endpoint (`GET /api/filesystem/browse`) since browsers cannot expose absolute paths from native file pickers. Analysis reads files directly from their original location.

## ADR-012: Direct USB database reading via rbox for Device Library Plus hardware
Date: 2026-03-16
Context: The XDJ-AZ (and Opus Quad, OMNIS-DUO, CDJ-3000X) uses Device Library Plus (One Library) format exclusively. beat-link's MetadataFinder and CrateDigger cannot reliably retrieve metadata from these devices because they use a different ID namespace (DLP IDs vs DeviceSQL IDs). Confirmed known issue with beat-link v8.0.0.
Decision: For devices that use Device Library Plus, bypass beat-link's metadata system entirely. Use the `rbox` Python library to read track metadata, beatgrid, cue points, and phrase analysis directly from the USB's `exportLibrary.db` file. Use beat-link exclusively for real-time playback data (BPM, pitch, beat position, on-air status, beat events), which works correctly on all hardware. This creates two metadata paths:
- **DLP path (XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X):** rbox reads exportLibrary.db from USB → Python processes metadata directly. beat-link provides real-time playback data only.
- **Legacy path (CDJ-2000NXS2, CDJ-3000, XDJ-1000, etc.):** beat-link MetadataFinder + CrateDigger works normally for both metadata and real-time data.
The bridge reports which path is active per device so the Python side knows whether to expect metadata from the bridge or from rbox.
Consequences: New dependency: `rbox` (pip install rbox). The USB must be accessible to the SCUE computer (mounted directly or same USB accessible via hub). Track matching between rbox-imported metadata and beat-link's live playback uses the rekordbox ID from CdjStatus — it's the correct DLP ID and maps directly to records in `exportLibrary.db`. When beat-link adds DLP support in a future release, the bridge path can be used for all devices and rbox becomes a fallback.

## ADR-008: Sequential batch analysis with in-memory job tracking
Date: 2026-03
Context: `run_analysis()` is CPU-bound (~3-4s/track with librosa/MLX). Parallel analysis would thrash memory. SCUE is a local tool — no persistence needed for job state.
Decision: Batch analysis processes files sequentially via `asyncio.to_thread()` to keep the event loop responsive. Job state is tracked in-memory (`scue/api/jobs.py`). Frontend polls every 1s and auto-stops on completion.
Consequences: Job state is lost on server restart (acceptable for local tool). If persistence is needed later, jobs can be backed by SQLite.
