# Spec: UX Redesign — Library + Analysis Pages

## Summary

Consolidate four existing pages (Ingestion, Tracks, Analysis Viewer, Strata) into two:

1. **Library** — import tracks from sources, browse your SCUE collection
2. **Analysis** — run strata tiers, view/edit/compare arrangement results

This eliminates the "analyze" ambiguity (ingestion-time vs strata), removes the dead-end Analysis Viewer page, and creates a clear two-step mental model: **get tracks in (Library) → understand them (Analysis)**.

Sidebar navigation: `Library | Analysis` (replacing Ingestion, Tracks, Analysis, Strata entries). All other pages (Bridge, Logs, Network, etc.) unchanged.

Route: `/library` (Library), `/analysis` (Analysis — replaces both `/analysis` and `/strata`)

---

## Supersedes

- `specs/feat-FE-analysis-viewer/` — Analysis Viewer page absorbed into Analysis page
- Current Ingestion page (`/ingestion`) → Library page
- Current Tracks page (`/data/db`) → Library page, SCUE Library tab
- Current Strata page (`/strata`) → Analysis page

---

## Library Page (`/library`)

### Layout

```
+----------------------------------------------------------+
| [Rekordbox] [Hardware] [Audio Files] [SCUE Library]  tabs |
+----------------------------------------------------------+
| Tab content area                                          |
|                                                           |
| ┌─ Import Settings Bar ────────────────────────────────┐ |
| │ Toggle: [Metadata only] ←→ [Metadata + Base Analysis]│ |
| └──────────────────────────────────────────────────────┘ |
|                                                           |
| Tab-specific content (see below)                          |
|                                                           |
+----------------------------------------------------------+
```

The Import Settings Bar appears on the Rekordbox, Hardware, and Audio tabs (not SCUE Library). It contains a toggle switch controlling whether import runs base analysis (waveform/BPM/key generation) or just pulls metadata.

### State Persistence

The Library page remembers across navigation:
- Active tab
- Filter state per tab (search text, column filters, Rekordbox playlist selection)
- Scroll position per tab
- Selected tracks (checkbox state)
- Expanded preview rows

Implementation: Zustand store with no persistence to localStorage (session-only is fine).

---

### Tab 1: Rekordbox

**Purpose:** Browse your Rekordbox library, pick tracks to import into SCUE.

**Two browse modes** (toggle in toolbar):
1. **Tree view** — Rekordbox playlist/folder hierarchy on the left, tracks in selected node on the right. Mirrors Rekordbox organization.
2. **Flat view** — All Rekordbox tracks in one searchable/filterable table.

**Flow:**
1. On tab mount, auto-detect Rekordbox master.db location (`GET /local-library/master-db/detect`)
2. If not found → show error with full file path attempted and troubleshooting detail
3. If found → auto-scan or show "Scan Rekordbox" button (TBD: auto vs manual)
4. Scan results populate the track table

**Track table columns:** Title, Artist, BPM, Key, Duration, Rekordbox Playlist(s), SCUE Status badge

**SCUE Status badge:**
- Green checkmark = already in SCUE
- Empty = not imported
- Default filter: show "Not in SCUE" only
- Toggle to show all (already-imported tracks shown with green badge, not grayed out — they may need re-import)

**Filtering:**
- Text search (title, artist)
- Rekordbox playlist/folder filter (tree view handles this naturally; flat view has a dropdown)
- Genre filter (if available from Rekordbox metadata)
- SCUE status filter (Not imported / Already imported / All)

**Selection + Import:**
- Checkbox multi-select on track rows
- "Select All (filtered)" button
- **Import button:** "Import to SCUE" — imports selected tracks per the toggle setting (metadata-only or metadata + base analysis)
- Import progress: inline spinner per track row during import. Row updates to show green checkmark when complete.

**Error states:**
- master.db not found: full path shown, suggestion to check Rekordbox installation
- master.db read error: error message + stack trace in expandable detail
- Individual track import failure: row shows red X with error message on hover/expand

---

### Tab 2: Hardware

**Purpose:** Browse tracks on connected Pioneer hardware (USB/SD), import into SCUE.

Largely same as current Hardware tab with these changes:
- Uses same track table patterns as Rekordbox tab (checkbox select, inline progress)
- Import follows the toggle setting (metadata-only vs metadata + base analysis)
- Device labeling is hardware-aware:
  - Standard CDJ: "CDJ-3000 (Player 1) — USB" / "CDJ-3000 (Player 1) — SD"
  - XDJ-AZ (all-in-one): "XDJ-AZ — USB" / "XDJ-AZ — SD" (not "Player 1 USB" / "Player 1 SD")
  - The system already deduplicates all-in-one units; labels should reflect the device name, not the DLP player number
- Real-time scan progress via WebSocket (existing `scan_progress` events)
- No scan history on this tab — filter SCUE Library by source=hardware instead

---

### Tab 3: Audio Files

**Purpose:** Import local audio files directly (not from Rekordbox or hardware).

Same as current Audio tab. Uses the import toggle setting.

---

### Tab 4: SCUE Library

**Purpose:** Browse all tracks imported into SCUE. Starting point for analysis.

**Track table columns:**
| Column | Description |
|--------|-------------|
| Title | Track title |
| Artist | Artist name |
| BPM | Beats per minute |
| Key | Musical key |
| Duration | Track length |
| Source | Badge: Rekordbox / Hardware / Audio |
| Imported | Date imported |
| Q | Quick tier badge (green dot if exists) |
| S | Standard tier badge |
| D | Deep tier badge |
| L | Live tier badge |
| L-O | Live Offline tier badge |

Tier badges: green dot = complete, gray dot = not run. Tooltip on each badge explaining what the tier means (per existing `project_column_definitions` memory — these are not common knowledge).

**Filtering:**
- Text search (title, artist)
- Source filter (Rekordbox / Hardware / Audio / All)
- Tier filter (e.g., "has Quick but no Standard" — useful for finding tracks needing deeper analysis)
- Date range filter on import date
- Hardware scan date filter (for source=hardware tracks)

**Selection + Bulk Actions:**
- Checkbox multi-select
- **"Run Quick Analysis"** button — kicks off strata quick tier for all selected tracks
  - Inline progress: each row shows small spinner in Q column while analyzing
  - On complete, spinner → green dot
  - Uses existing batch strata endpoint (`POST /api/strata/analyze-batch`)
- **"Open in Analysis"** button — navigates to Analysis page with selected track (single select only)

**Inline Preview (expandable row):**
Clicking a track row expands it to show:
- Full metadata: BPM, key, duration, source, import date, fingerprint
- Mini waveform (if base analysis has been run) — small, non-interactive, just for visual ID
- Tier status summary (which tiers exist, which sources: analysis/pioneer_enriched/etc.)
- **"Open in Analysis →"** link

Clicking elsewhere or another row collapses the preview.

---

## Analysis Page (`/analysis`)

### Purpose

Single workspace for all track analysis: run strata tiers, view arrangement results, edit, compare. Replaces both the old Analysis Viewer and Strata pages.

### Layout

```
+----------------------------------------------------------+
| Track Picker (mini table — title, artist, BPM, key, dur) |
+----------------------------------------------------------+
| Waveform Panel (collapsible)                              |
| [waveform canvas + section overlays + energy curve]       |
| [track metadata sidebar]                                  |
+----------------------------------------------------------+
| Arrangement Panel                                         |
| ┌─ Tier Selector ──────────────────────────────────────┐ |
| │ [Quick ●] [Standard ○] [Deep ○] [Live ○] [L-O ○]   │ |
| │ Source: [analysis ▾]  [Analyze] [Compare]            │ |
| └──────────────────────────────────────────────────────┘ |
|                                                           |
| ArrangementMap (stems, patterns, transitions, beat grid)  |
|                                                           |
| Section details / Pattern details (context panel)         |
+----------------------------------------------------------+
```

### Stacked Panels

**Panel 1: Track Picker** (top, always visible)
- Mini track table (compact). Same data as SCUE Library but optimized for quick selection.
- Sortable, searchable. Remembers last selection.
- If navigated from Library with a track pre-selected, that track is highlighted.

**Panel 2: Waveform + Metadata** (collapsible)
- Full-width waveform canvas from the old Analysis Viewer
- Section overlays as colored regions
- Energy curve overlay
- Beat grid / downbeat markers
- Track metadata sidebar (BPM, key, duration, source, fingerprint)
- Section list with bidirectional highlighting (click section → waveform scrolls, click waveform region → section highlights)
- **Collapsible:** user can minimize this panel to focus on the arrangement. Collapse state persisted.

**Panel 3: Arrangement** (main workspace)
- **Tier selector bar:** buttons for each tier (Quick/Standard/Deep/Live/Live-Offline). Active tier highlighted. Dot indicator: green=exists, gray=not run, disabled=not available.
- **Source selector:** dropdown for analysis source (analysis, pioneer_enriched, pioneer_reanalyzed, pioneer_live) when multiple sources exist for a tier.
- **"Analyze" button:** runs the selected tier. Quick runs synchronously. Standard/Deep show inline progress (step name, progress bar, ETA).
- **"Compare" button:** opens side-by-side comparison mode (pick two tier/source combos).
- **ArrangementMap canvas:** stem lanes, activity spans, pattern blocks, transition markers, beat grid. Interactive — click patterns/transitions for detail.
- **Context panel below map:** shows detail for selected pattern or transition. Pattern template, variation instances, confidence scores. Editable in edit mode.
- **Edit mode toggle:** allows manual adjustment of transitions, patterns, section labels. Save button writes back via `PUT /tracks/{fp}/strata/{tier}`.
- **Batch mode:** select multiple tracks from picker, run analysis on all. Progress shown per-track inline.

### Analysis Progress UX

**Quick tier (synchronous):**
- Button shows spinner for 3-7 seconds
- On complete, arrangement map renders immediately

**Standard/Deep tier (async):**
- Progress bar appears below tier selector
- Shows: step name ("Running stem separation..."), step N/M, estimated time remaining
- Polls `GET /api/strata/jobs/{job_id}` every 1s
- On complete, progress bar disappears, arrangement map renders

**Live tier:**
- Active only when a track is loaded on a CDJ
- Real-time playback cursor on arrangement map
- Formula updates via WebSocket (`strata_live` events)

---

## Navigation

### Sidebar

```
── Library        → /library
── Analysis       → /analysis
── Bridge         → /data/bridge
── Logs           → /console
── Network        → /data/network
```

(Other existing pages remain in their current positions.)

### Cross-Page Navigation

- Library → Analysis: "Open in Analysis" link in track preview, or "Open in Analysis" button with selected track. Navigates to `/analysis?track={fingerprint}`.
- Analysis → Library: breadcrumb or back link. "← Library" in top-left of track picker.
- Deep link support: `/analysis?track={fingerprint}&tier=standard&source=pioneer_enriched` pre-selects track + tier + source.

### Redirects

- `/ingestion` → redirect to `/library` (Rekordbox tab)
- `/data/db` → redirect to `/library` (SCUE Library tab)
- `/strata` → redirect to `/analysis`
- `/analysis` (old route) → works directly (same route, new page)

---

## Error Handling

All error states show developer-level detail:
- Actual error message and stack trace where available
- File paths, endpoint URLs, HTTP status codes
- Expandable by default (not hidden behind "show details")
- Red background / border to make errors unmissable

Examples:
- Rekordbox DB not found: "master.db not found at `/Users/brach/Library/Pioneer/rekordbox/master.db`. Check that Rekordbox is installed and has been opened at least once."
- Scan failure: full error with traceback
- Analysis job failure: step that failed, error message, full job state dump

---

## Migration Notes

### Pages to Remove
- `IngestionPage.tsx` — replaced by Library page
- `TracksPage.tsx` — replaced by Library page (SCUE Library tab)
- `AnalysisViewerPage.tsx` — replaced by Analysis page

### Components to Reuse
- `TrackPicker` — reuse in Analysis page (already shared between Analysis Viewer and Strata)
- `ArrangementMap` — reuse as-is in Analysis page arrangement panel
- `WaveformCanvas` — reuse in Analysis page waveform panel
- `SectionList` — reuse in Analysis page waveform panel
- `AnalysisViewer` — extract waveform + metadata portions, discard page wrapper
- `RekordboxTab` — refactor for new patterns (tree+flat view, checkbox select, inline progress)
- `HardwareTab` — refactor for new patterns (device labeling, import toggle)
- `ScanProgressPanel` — keep for hardware real-time progress

### New Components Needed
- `LibraryPage` — new page with tab management + state persistence
- `ScueLibraryTab` — track table with tier badges, bulk actions, inline preview
- `TrackPreviewRow` — expandable inline preview (metadata + mini waveform + tier status)
- `ImportSettingsBar` — toggle for metadata-only vs metadata + base analysis
- `RekordboxTreeView` — playlist/folder hierarchy browser
- `AnalysisPage` — new page replacing both AnalysisViewer and Strata
- `WaveformPanel` — collapsible wrapper around WaveformCanvas + SectionList + metadata
- `TierSelectorBar` — tier buttons + source dropdown + analyze/compare actions

### Backend Changes
- Rekordbox scan endpoint may need playlist/folder hierarchy data (currently returns flat list?)
- No new strata endpoints needed — existing ones cover all analysis flows
- Redirect middleware for old routes (or handle in frontend router)

---

## Out of Scope

- Deep tier implementation (Phase 6 — not yet built)
- Musical Events viewer (future milestone)
- Analysis parameter tuning UI (future)
- Ground truth annotation system (partially done, separate effort)
- Simplifying tier selection for end users (future — developer control needed now)
