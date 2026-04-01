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

## Known Gaps / Follow-ups

- **Playlist track filtering:** Tree view selects playlists but cross-referencing track IDs with scan results needs `rekordbox_id` in the response for exact matching. Currently best-effort.
- **Pre-existing build errors:** `npm run build` has ~15 pre-existing TS errors in other files (ws.ts, AnnotationTimeline, ScanProgressPanel, etc.). `npm run typecheck` passes clean — no new errors from this work.
- **PlantUML diagrams are starter examples.** The two `.puml` files cover system overview and data flow. More diagrams (bridge lifecycle, strata pipeline, WS message flow) can be added as needed.

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
