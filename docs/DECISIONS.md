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

## ADR-013: pyrekordbox for ANLZ parsing, rbox retained for database reading
Date: 2026-03-17
Context: rbox v0.1.7's Rust ANLZ parser panics (uncatchable process abort) on some XDJ-AZ Device Library Plus ANLZ files. The panic occurs when the parser encounters unknown section variants at certain offsets. Since Rust panics kill the Python process, this cannot be safely caught or isolated in-process.
Decision: Replace rbox's ANLZ parsing with a two-tier pure-Python strategy:
- **Tier 1: pyrekordbox** (v0.4.4+) — full ANLZ support via `AnlzFile.parse_file()`. Handles beat grid (PQTZ), cue points (PCOB), and phrase analysis (PSSI). Pure Python, raises normal exceptions on failure.
- **Tier 2: custom `anlz_parser.py`** — zero-dependency fallback. Reads PQTZ (beat grid) and PCOB (cue lists) only. Skips all other sections. Raises `AnlzParseError` on failure.
- If both fail, enrichment falls back to librosa-derived data (existing behavior).
rbox's `OneLibrary` is retained for `exportLibrary.db` reading — it works correctly and is the only Python library that supports the DLP/OneLibrary USB database format. pyrekordbox's `Rekordbox6Database` targets the desktop `master.db`, not the USB database.
Consequences: New dependency: `pyrekordbox>=0.4.4` (added to `[usb]` optional deps alongside rbox). ANLZ reading is now re-enabled in the USB scanner — no more Rust panic risk. All ANLZ parsing runs in pure Python with normal exception handling.

## ADR-014: USB ANLZ waveform reading as universal path via pyrekordbox
Date: 2026-03-20
Context: WaveformFinder is broken on ALL DLP hardware (XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X) due to a hard dependency on MetadataFinder + DLP ID namespace mismatch. Even on legacy hardware where WaveformFinder works, it adds startup complexity and network overhead. Research confirmed pyrekordbox v0.4.4 can read ALL 7 ANLZ waveform tags (PWAV, PWV2-7) from USB across all hardware variants.
Decision: Use pyrekordbox to read Pioneer ANLZ waveform data directly from USB as the universal waveform source for instant display. This eliminates the need for WaveformFinder entirely and provides a single code path for all hardware. Pioneer waveforms (PWV5/PWV7: ~45K entries at ~150/sec) provide sufficient resolution for visual display. SCUE's librosa-analyzed RGB waveform remains the primary source for cue generation (higher precision, frequency-aware). Two rendering paths in WaveformCanvas: SCUE RGB (primary) and Pioneer ANLZ (instant fallback when SCUE analysis hasn't run yet).
Consequences: Extend usb_scanner.py to read PWV3/PWV5/PWV7 tags during USB scan. Store Pioneer waveform data in pioneer_metadata cache. WaveformCanvas gains a Pioneer rendering mode. ADR-012's blanket disabling of WaveformFinder is confirmed correct — not collateral damage, but the right call.

## ADR-015: Composite primary key for track_ids table (multi-USB safety)
Date: 2026-03-20
Context: Research confirmed that DLP rekordbox_id values are per-USB auto-increment keys. Two USBs plugged into different decks will have colliding IDs (e.g., both have track ID 1 for completely different tracks). The current `track_ids` table uses `rekordbox_id INTEGER PRIMARY KEY` which silently overwrites in multi-USB setups. Additionally, IDs are volatile across USB re-exports — rekordbox reassigns IDs when the database is rebuilt.
Decision: Migrate `track_ids` table to composite primary key `(source_player, source_slot, rekordbox_id)`. Update `lookup_fingerprint()` and `link_rekordbox_id()` signatures to accept all three fields. Add `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}` REST endpoint for frontend track resolution. Migration strategy: drop and recreate (SQLite is derived cache per ADR-004). Tiered reconciliation (composite key → file path stem → title+artist) already implemented in usb_scanner.py, just needs composite key threading.
Consequences: All callers of lookup_fingerprint and link_rekordbox_id must be updated. Frontend must use composite key for track resolution (not bare rekordbox_id). This must ship before Live Deck Monitor to avoid silent data corruption.

## ADR-016: DLP fix strategy — SCUE translation layer (Strategy D)
Date: 2026-03-20
Context: beat-link has a critical DLP bug: CdjStatus constructor only flags `isFromOpusQuad`. XDJ-AZ and CDJ-3000X take the else branch, passing DLP-namespace IDs through unchanged. All Finders (Metadata, BeatGrid, Waveform, AnalysisTag, CrateDigger) build DataReference with the wrong ID, returning wrong track data. Upstream fix timeline uncertain — @brunchboy stated "XDJ-AZ is not supposed to be supported" (Jan 2025). Four strategies evaluated: (A) patch beat-link (3-5 weeks, HIGH risk), (B) SCUE translation layer (1-2 days, LOW risk), (C) DlpProvider (2-3 weeks), (D) hybrid of existing architecture + B.
Decision: Strategy D — fix composite key (ADR-015), add `uses_dlp` flag per device to route metadata queries to the correct namespace, implement dual-database USB scanning to build DLP↔DeviceSQL ID mapping via shared file paths. SCUE handles the translation internally rather than waiting for upstream beat-link fixes. Medium-term opportunity: contribute DlpProvider as clean upstream extension.
Consequences: USB scanner must read both export.pdb and exportLibrary.db when both are present. Device classification needs `uses_dlp` flag (Opus Quad, XDJ-AZ, CDJ-3000X, OMNIS-DUO). All metadata resolution paths must be namespace-aware. Estimated effort: 2-4 days.

## ADR-017: Enable beat-link Finders via 8.1.0-SNAPSHOT upgrade
Date: 2026-03-20
Status: SUPERSEDES ADR-012
Context: Research confirmed beat-link 8.1.0-SNAPSHOT (used by BLT) has native XDJ-AZ support. The XDJ-AZ has a working dbserver (unlike Opus Quad). CrateDigger downloads exportLibrary.db via NFS, providing ID translation. All Finders work correctly. ADR-012's blanket disabling was correct for 8.0.0 but is no longer needed.
Decision: Upgrade bridge from beat-link 8.0.0 to 8.1.0-SNAPSHOT. Enable MetadataFinder, WaveformFinder, BeatGridFinder, AnalysisTagFinder, CrateDigger, TimeFinder, and ArtFinder. Add --database-key CLI argument for DLP database decryption (required for exportLibrary.db). Retain rbox/pyrekordbox USB scanning as supplementary source (offline analysis, pre-scan before hardware is connected). Bridge version bumped to 2.0.0.
Consequences: Bridge now emits track_metadata, beat_grid, waveform_detail, phrase_analysis, and cue_points messages. Python adapter already handles these. Database key must be configured for DLP hardware via SCUE_DLP_DATABASE_KEY env var. Opus Quad still requires metadata archives (no dbserver).

## ADR-018: Pioneer-accurate RGB waveform rendering
Date: 2026-03-20
Context: SCUE's RGB waveform rendering looked visually wrong compared to Pioneer CDJs. Side-by-side comparison revealed three root causes: (1) the renderer drew three separate colored layers (red/green/blue stacked on top of each other) instead of blending into a single color per column, (2) the color channel mapping was inverted (R=highs, B=lows — opposite of Pioneer's R=lows, B=highs), (3) each frequency band was normalized independently to 0.0–1.0, destroying the actual frequency balance (a bass-heavy track appeared to have equal bass and treble).

Decision: Rewrite waveform computation and rendering to match Pioneer's approach:

**Backend (`layer1/waveform.py`):**
- Frequency crossovers aligned to Pioneer mixer EQ points: LOW 20–200 Hz, MID 200–2500 Hz, HIGH 2500 Hz+ (was 0–250, 250–4000, 4000–11025)
- Output resolution bumped from 60 fps to 150 entries/sec (matches Pioneer PWV5/PWV7 detail resolution)
- Global normalization: all three bands share the same max value, preserving relative frequency balance across the track

**Frontend (`WaveformCanvas.tsx`):**
- Single blended bar per column instead of three stacked layers. Height = amplitude (`max(low, mid, high)`), color = frequency ratio (each channel divided by amplitude)
- Color mapping corrected: R = low/bass, G = mid, B = high/treble (matches Pioneer PWV5)
- Result: kick = red, hi-hat = blue, vocal = green/cyan, kick+hat = magenta, full spectrum = white/pink

Consequences: All existing cached waveform data must be re-analyzed to pick up the new crossover points, global normalization, and 150fps resolution. Existing waveforms will still render (the frontend handles any sample_rate) but will show the old frequency balance until re-analyzed. The `RGBWaveform` type contract (low/mid/high float arrays + sample_rate + duration) is unchanged — this is a rendering and computation fix, not a schema change.

## ADR-008: Sequential batch analysis with in-memory job tracking
Date: 2026-03
Context: `run_analysis()` is CPU-bound (~3-4s/track with librosa/MLX). Parallel analysis would thrash memory. SCUE is a local tool — no persistence needed for job state.
Decision: Batch analysis processes files sequentially via `asyncio.to_thread()` to keep the event loop responsive. Job state is tracked in-memory (`scue/api/jobs.py`). Frontend polls every 1s and auto-stops on completion.
Consequences: Job state is lost on server restart (acceptable for local tool). If persistence is needed later, jobs can be backed by SQLite.
