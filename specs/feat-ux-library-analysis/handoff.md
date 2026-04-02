# Handoff: Library + Analysis UX Redesign + PlantUML

**Date:** 2026-04-01
**Spec:** `specs/feat-ux-library-analysis/spec.md`
**Plan:** `~/.claude/plans/binary-foraging-cascade.md`
**Status:** All 4 implementation phases complete. Old pages deleted. PlantUML added. Typecheck passes. Needs QA.

---

## What Was Built

Consolidated 4 pages (Ingestion, Tracks, AnalysisViewer, Strata) into 2 (Library + Analysis).

### New Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/src/pages/LibraryPage.tsx` | 90 | 4-tab page shell (Rekordbox, Hardware, Audio, SCUE Library) |
| `frontend/src/pages/AnalysisPage.tsx` | 483 | TrackPicker + WaveformPanel + TierSelectorBar + FormulaView; all modes |
| `frontend/src/components/library/ScueLibraryTab.tsx` | 396 | TanStack Table: tier badges, multi-select, bulk Quick Analysis, expandable preview |
| `frontend/src/components/library/TrackPreviewRow.tsx` | 102 | Expandable row: metadata, mini waveform, tier status, "Open in Analysis" |
| `frontend/src/components/library/ImportSettingsBar.tsx` | 37 | Toggle: metadata-only vs metadata + base analysis |
| `frontend/src/components/library/RekordboxTreeView.tsx` | 94 | Recursive playlist/folder tree browser |
| `frontend/src/components/analysis/FormulaView.tsx` | 493 | Extracted from StrataPage: waveform + arrangement + patterns + transitions + edit mode |
| `frontend/src/components/analysis/TierSelectorBar.tsx` | 217 | Extracted: tier buttons, source selector, analyze/reanalyze actions |
| `frontend/src/components/analysis/BatchAnalysisPanel.tsx` | 80 | Extracted: batch tier checkboxes, analyze button, progress |
| `frontend/src/components/analysis/WaveformPanel.tsx` | 117 | Collapsible wrapper: WaveformCanvas + SectionList + metadata sidebar |
| `frontend/src/stores/libraryStore.ts` | 55 | Zustand store: active tab, import mode, per-tab selections/search |
| `frontend/src/types/library.ts` | 17 | LibraryTab, ImportMode, LibraryFilterState types |

### Modified Files

| File | Change |
|------|--------|
| `scue/layer1/masterdb_scanner.py` | Added `PlaylistNode`, `scan_playlists()`, `_playlist_tree_to_dict()` |
| `scue/api/local_library.py` | Added `GET /api/local-library/master-db/playlists` endpoint |
| `frontend/src/api/ingestion.ts` | Added `useMasterDbPlaylists()` hook |
| `frontend/src/types/ingestion.ts` | Added `PlaylistNode`, `PlaylistTreeResponse` types |
| `frontend/src/components/ingestion/RekordboxTab.tsx` | Rewritten: flat/tree toggle, multi-select, SCUE status badges, import mode |
| `frontend/src/components/ingestion/HardwareTab.tsx` | XDJ-AZ labeling: "XDJ-AZ — USB" instead of "Player 1" |
| `frontend/src/App.tsx` | Routes: `/library`, `/analysis`, redirects for old routes, old imports removed |
| `frontend/src/components/layout/Sidebar.tsx` | Final nav: Library, Analysis, Live Monitor, Data, System, Archive |

### Deleted Files

| File | Replaced By |
|------|-------------|
| `frontend/src/pages/IngestionPage.tsx` | LibraryPage (Rekordbox/Hardware/Audio tabs) |
| `frontend/src/pages/TracksPage.tsx` | LibraryPage (SCUE Library tab) |
| `frontend/src/pages/AnalysisViewerPage.tsx` | AnalysisPage (WaveformPanel) |
| `frontend/src/pages/StrataPage.tsx` | AnalysisPage (TierSelectorBar + FormulaView) |

### PlantUML Integration (added same session)

| File | Purpose |
|------|---------|
| `frontend/src/components/shared/PlantUmlDiagram.tsx` | React component: encodes source via `plantuml-encoder`, renders `<img>` from PlantUML server |
| `docs/diagrams/system-overview.puml` | 5-layer architecture diagram (dark theme) |
| `docs/diagrams/data-flow.puml` | Track data flow: import → analysis tiers → output |
| `scripts/render-diagrams.sh` | CLI: renders all `.puml` → `.svg` via PlantUML server |
| `frontend/package.json` | Added `plantuml-encoder` + `@types/plantuml-encoder` |
| `.gitignore` | Added `docs/diagrams/*.svg` (generated artifacts) |

PlantUML server is configurable via `VITE_PLANTUML_SERVER` env var (default: `https://www.plantuml.com/plantuml`). For offline use: `docker run -d -p 8080:8080 plantuml/plantuml-server:jetty`.

---

## Architecture Decisions

1. **Rekordbox tree view:** Backend endpoint via pyrekordbox `get_playlist()`/`get_playlist_contents()`. Recursive `PlaylistNode` tree. Brach's library is flat (no folders), but hierarchy is supported.

2. **StrataPage decomposition:** FormulaView, TierSelectorBar, BatchAnalysisPanel extracted as standalone. AnalysisPage recomposes with same useState pattern (no new store — page state doesn't persist across navigation).

3. **Pan/zoom sync:** WaveformPanel and ArrangementMap share viewStart/viewEnd via `useWaveformView` hook, same as original StrataPage pattern.

4. **Import mode:** `libraryStore.importMode` maps to `skip_waveform` on ingest endpoint. "Metadata only" = skip_waveform=true.

---

## QA Checklist

### Library Page (`/library`)
- [ ] SCUE Library tab: tracks load with tier dot badges + tooltips
- [ ] Bulk select + "Run Quick Analysis" triggers batch strata endpoint
- [ ] "Open in Analysis" navigates to `/analysis?track={fp}`
- [ ] Expandable preview: metadata + mini waveform + tier status
- [ ] Import Settings toggle persists across tab switches
- [ ] Rekordbox tab: scan → SCUE status badges (checkmark vs empty)
- [ ] Rekordbox tab: flat/tree toggle loads playlists
- [ ] Rekordbox tab: "Show imported" filter
- [ ] Hardware tab: XDJ-AZ shows device name, not player number
- [ ] Audio tab: unchanged behavior

### Analysis Page (`/analysis`)
- [ ] TrackPicker → WaveformPanel + ArrangementMap render
- [ ] WaveformPanel collapsible
- [ ] Tier selector with availability dots
- [ ] Analyze: quick sync, standard/deep async with progress
- [ ] Source selector when multiple sources exist
- [ ] Compare mode, batch mode, edit mode all work
- [ ] Live tier with WS + playback cursor
- [ ] Deep link: `/analysis?track={fp}&tier=standard&source=pioneer_enriched`

### Navigation
- [ ] `/ingestion` → `/library`, `/data/db` → `/library`, `/strata` → `/analysis`
- [ ] Default route → `/library`
- [ ] Sidebar matches spec

---

## Bug Fixes (same session)

### [FIXED] Strata progress bar jumps to 40% then stalls
Progress was `current_step / total_steps` — equal weight per step. Demucs (step 2/5) takes 60s of ~75s total but only showed as 20% bar width. Fixed with `durationWeightedPercent()` that weights by estimated wall time. Also fixed pre-existing `TIER_LABELS` build error (missing `live`/`live_offline`).
File: `frontend/src/components/strata/TierAnalysisStatus.tsx`

## Open Bugs (for next session)

### [FIXED 2026-04-01] App goes dormant when laptop screen sleeps
**Priority:** MEDIUM
**Fix:** Added OS sleep/wake detection in `_health_check_loop()`. If `asyncio.sleep(N)` slept > 3×N, macOS suspended us. On detection: reset stale timestamps, grant 30s grace period before resuming health checks. See `docs/bugs/layer0-bridge.md` for full details.

### [FIXED 2026-04-01] Bridge crash-restart loop (recurring)
**Priority:** HIGH
**Fix:** Four root causes found and fixed (see `docs/bugs/layer0-bridge.md` entry dated 2026-04-01):
1. **Interface pre-check** (THE critical fix) — `start()` now checks `socket.if_nametoindex()` before launching subprocess. If en16 doesn't exist, skips directly to `waiting_for_hardware` with zero crash loops. Previously the Java bridge launched as a zombie and took ~7 minutes to reach waiting_for_hardware.
2. **Crash-window mechanism** — `_consecutive_failures` no longer resets when crashes happen within 120s of each other, even if individual runs exceed 30s.
3. **Listen loop restart on clean WS close** — `_listen_loop()` now triggers restart when the WS closes cleanly (ConnectionClosed), not just on exceptions.
4. **Sleep/wake grace period** — health check detects OS sleep and grants 30s grace before resuming checks.
All 69 bridge tests pass. **Needs live hardware QA** — see mandatory test criteria in `docs/bugs/layer0-bridge.md`.

## Known Gaps / Follow-ups

- **Playlist track filtering:** Tree view selects playlists but cross-referencing track IDs with scan results needs `rekordbox_id` in the response for exact matching. Currently best-effort.
- **Pre-existing build errors:** `npm run build` has ~14 pre-existing TS errors in other files (ws.ts, AnnotationTimeline, ScanProgressPanel, etc.). `npm run typecheck` passes clean — no new errors from this work. (One pre-existing error fixed: `TierAnalysisStatus.tsx` TIER_LABELS.)
- **PlantUML diagrams are starter examples.** The two `.puml` files cover system overview and data flow. More diagrams (bridge lifecycle, strata pipeline, WS message flow) can be added as needed.

## Assessment: Parallel Song Analysis

### Current state
All analysis is **strictly sequential**. Both single-track and batch paths run in a single `BackgroundTasks` thread:
- Single: `_run_strata_analysis()` — one track, one thread, blocks until done.
- Batch: `_run_strata_batch()` — iterates a `for` loop over tracks, calling `_run_strata_analysis()` per track. No concurrency.

### Resource profile per track (standard tier)

| Stage | Time | CPU | RAM | GPU/MPS | I/O |
|-------|------|-----|-----|---------|-----|
| 1. Load analysis | ~1s | low | ~50 MB | none | disk read |
| 2. Stem separation (demucs htdemucs) | ~60s | **high** (all cores) | **~2-4 GB** (model + audio tensors) | MPS if available, else CPU | writes 4 stem WAVs (~200 MB total) |
| 3. Per-stem analysis | ~10s | medium | ~200 MB per stem | none | reads stem WAVs |
| 4. Cross-stem transitions | ~3s | low | ~100 MB | none | none |
| 5. Assembly | ~1s | low | ~50 MB | none | writes formula JSON |

**Demucs is the bottleneck.** It uses PyTorch and will attempt MPS (Apple Silicon GPU) if available, otherwise saturates all CPU cores. Memory footprint is ~2-4 GB for the model + full-track audio tensor.

### Parallelism viability

| Scenario | Tracks | Feasible? | Notes |
|----------|--------|-----------|-------|
| Quick tier only | 10-50+ | **Yes** | No demucs, ~3-7s per track, CPU-light. Could run 4-8 in parallel easily. |
| Standard tier, M-series Mac (16 GB) | **2** | **Yes, carefully** | Each demucs instance needs ~2-4 GB RAM. Two instances = 4-8 GB. Leaves room for the app + bridge. |
| Standard tier, M-series Mac (16 GB) | **3+** | **Risky** | 3 × 4 GB = 12 GB just for demucs. Likely triggers memory pressure / swap thrashing. |
| Standard tier, 32+ GB Mac | **3-4** | **Yes** | Comfortable RAM headroom. GPU contention (MPS is single-queue) becomes the bottleneck instead. |
| Standard tier, any machine | **5+** | **No** | Diminishing returns: MPS is serialized, CPU-fallback demucs pins all cores, disk I/O for stem WAVs becomes a factor. |

### Recommendations

**Quick tier parallelism (low-hanging fruit):**
- Quick analysis is CPU-light and takes 3-7s. Running 4-8 tracks in parallel via `concurrent.futures.ThreadPoolExecutor` or `ProcessPoolExecutor` would batch-analyze a library of 100 tracks in ~2-3 minutes instead of ~10 minutes.
- This is the highest-value change: bulk Quick analysis is the primary batch use case (Library page "Run Quick Analysis" button).
- Implementation: Replace the `for` loop in `_run_strata_batch()` with a pool, gated by tier. Quick → parallel, standard/deep → sequential.

**Standard tier parallelism (more complex):**
- Limited to 2 concurrent tracks on 16 GB machines. Demucs caches stems on disk, so re-runs skip separation — only the first analysis per track is expensive.
- Would need a configurable `max_workers` setting (in `config/server.yaml`) so the user can tune based on their hardware.
- Demucs itself already uses internal parallelism (multi-threaded tensor ops). Running 2 demucs instances won't be 2x faster — more like 1.4-1.6x due to shared CPU/GPU.
- MPS (Apple GPU) is single-queue, so two PyTorch processes sharing MPS actually serialize at the GPU level. True GPU parallelism isn't possible on current Apple Silicon.

**Suggested implementation order:**
1. Quick tier parallel batch (ThreadPoolExecutor, `max_workers=min(8, os.cpu_count())`)
2. Add `VITE_BATCH_MAX_PARALLEL` / `batch.max_parallel` config
3. Standard tier parallel with `max_workers=2` default, configurable up to 4
4. Per-track progress needs rework for parallel (currently assumes one active job)

## Session Verification Summary

| Check | Result |
|-------|--------|
| `npm run typecheck` | Clean (0 errors) |
| `npm run build` | No new errors (pre-existing only) |
| `/` default route → `/library` | Confirmed |
| `/strata` redirect → `/analysis` | Confirmed |
| `/ingestion` redirect → `/library` | Confirmed |
| `/data/db` redirect → `/library` | Confirmed |
| Analysis page renders with TrackPicker + mode toggles | Confirmed |
| Sidebar final layout matches spec | Confirmed |
| PlantUML `<img>` renders from public server | Confirmed |
| `scripts/render-diagrams.sh` produces valid SVGs | Confirmed (2 diagrams) |
| Zero console errors in browser | Confirmed |
