# Tasks: FE-Analysis-Viewer

## Dependency Graph

```
TASK-001 (useTrackAnalysis hook + TrackPicker)
  |
  +---> TASK-002 (WaveformCanvas — shared component)
  |       |
  |       +---> TASK-003 (Section overlays + energy overlay)
  |       |       |
  |       |       +---> TASK-005 (Bidirectional section ↔ waveform interaction)
  |       |
  |       +---> TASK-004 (Zoom + scroll)
  |
  +---> TASK-006 (SectionList + filtering)
  |       |
  |       +---> TASK-005 (Bidirectional interaction — depends on both TASK-003 and TASK-006)
  |
  +---> TASK-007 (TrackMetadataPanel + PlaceholderPanels)

TASK-008 (Page assembly + routing + sidebar)
  depends on: TASK-001, TASK-005, TASK-007
```

**Parallel tracks after TASK-001:**
- Track A: TASK-002 → TASK-003 → TASK-005 (waveform rendering pipeline)
- Track A′: TASK-002 → TASK-004 (zoom/scroll, parallel with TASK-003)
- Track B: TASK-006 (section list, parallel with Track A)
- Track C: TASK-007 (metadata + placeholders, parallel with everything)
- TASK-008 is final assembly.

## Tasks

### TASK-001: useTrackAnalysis hook + TrackPicker component
- **Layer:** Frontend-State + Frontend-UI
- **Estimated effort:** 30 min
- **Depends on:** none
- **Scope:**
  - `frontend/src/api/tracks.ts` (modify — add `useTrackAnalysis` hook)
  - `frontend/src/components/analysis/TrackPicker.tsx` (create)
- **Inputs:**
  - Existing `useTracks` hook pattern
  - `TrackAnalysis` type from `types/track.ts`
  - `apiFetch` from `api/client.ts`
- **Outputs:**
  - `useTrackAnalysis(fingerprint: string | null)` — TanStack Query hook, calls `GET /api/tracks/:fingerprint`, enabled when fingerprint is non-null
  - `TrackPicker` component: compact sortable table (title, artist, BPM, key, duration, sections), search filter input, `onSelect(fingerprint)` callback, selected row highlighting, `max-h-48` with overflow scroll
- **Acceptance Criteria:**
  - [ ] `useTrackAnalysis` returns full `TrackAnalysis` object for a valid fingerprint
  - [ ] `useTrackAnalysis` with `null` fingerprint does not fire a request (`enabled: false`)
  - [ ] `TrackPicker` renders a sortable mini table with columns: title, artist, BPM, key, duration, sections
  - [ ] Search input filters rows by title and artist
  - [ ] Clicking a row calls `onSelect(fingerprint)` and highlights the row
  - [ ] Table is capped at `max-h-48` with vertical scroll
  - [ ] All pre-existing tests pass
- **Context files:**
  - `frontend/src/api/tracks.ts` — existing hooks pattern
  - `frontend/src/types/track.ts` — `TrackAnalysis`, `TrackSummary`
  - `frontend/src/api/client.ts` — `apiFetch`
  - `frontend/src/components/tracks/TrackTable.tsx` — reference for TanStack Table usage
- **Status:** [ ] Not started

### TASK-002: WaveformCanvas shared component — basic rendering
- **Layer:** Frontend-UI
- **Estimated effort:** 45 min
- **Depends on:** TASK-001 (needs `TrackAnalysis` data to test)
- **Scope:**
  - `frontend/src/components/shared/WaveformCanvas.tsx` (create)
- **Inputs:**
  - `RGBWaveform` type from `types/track.ts`
  - Props interface from spec (WaveformCanvas section)
  - Color mixing algorithm from spec
- **Outputs:**
  - `WaveformCanvas` component rendering a `<canvas>` element
  - Renders waveform as vertical bars, colored by 3-band frequency data (bass=blue `#0066FF`, mids=green `#00CC66`, highs=magenta `#FF3366`)
  - Bars extend from center (mirrored top/bottom, rekordbox style)
  - Downsamples when more samples than pixels (max-per-bucket)
  - Renders cursor line when `cursorPosition` is provided
  - Accepts `viewStart`/`viewEnd` for the visible time window
  - Responsive: fills parent width, fixed aspect ratio or height prop
- **Acceptance Criteria:**
  - [ ] Canvas renders colored vertical bars from `RGBWaveform` data
  - [ ] Color mixing matches spec: bass=blue, mids=green, highs=magenta, hot=white
  - [ ] Bars are mirrored (top/bottom from center line)
  - [ ] Downsampling works: 18K samples displayed at 1200px width without performance issues
  - [ ] `viewStart`/`viewEnd` props control the visible window
  - [ ] Cursor line renders at `cursorPosition` when provided (white, 2px, full height)
  - [ ] Component re-renders on prop changes via `requestAnimationFrame`
  - [ ] Canvas resizes with parent container (observe with ResizeObserver)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — WaveformCanvas section
  - `frontend/src/types/track.ts` — `RGBWaveform`
- **Status:** [ ] Not started

### TASK-003: Section overlays + energy curve overlay
- **Layer:** Frontend-UI
- **Estimated effort:** 30 min
- **Depends on:** TASK-002
- **Scope:**
  - `frontend/src/components/shared/WaveformCanvas.tsx` (modify — add overlay rendering)
- **Inputs:**
  - `Section[]` and `number[]` (energy curve) props on `WaveformCanvas`
  - Section color map from spec
  - Energy overlay rendering approach from spec
- **Outputs:**
  - Section overlays rendered as semi-transparent colored regions behind waveform bars
  - Section boundary lines (thin vertical)
  - Section labels at top-left of each region (10px font)
  - `highlightedSection` prop brightens the highlighted section (2x alpha, solid border)
  - Energy curve rendered as semi-transparent white line overlaid on waveform
  - Low-confidence sections (< 0.3) rendered with dashed border and faint overlay
- **Acceptance Criteria:**
  - [ ] Each section type renders with the correct color from the spec's color table
  - [ ] Section boundaries drawn as thin vertical lines
  - [ ] Section labels rendered at top-left of each section region
  - [ ] `highlightedSection` prop causes the target section to brighten
  - [ ] Energy curve renders as a smooth line over the waveform
  - [ ] Energy curve interpolates linearly between its coarser data points
  - [ ] Missing or empty energy curve gracefully skips overlay (no error)
  - [ ] Missing or empty sections gracefully skips overlays
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — Section overlay colors, energy overlay
  - `frontend/src/types/track.ts` — `Section`
- **Status:** [ ] Not started

### TASK-004: Zoom and scroll interaction
- **Layer:** Frontend-UI
- **Estimated effort:** 30 min
- **Depends on:** TASK-002
- **Scope:**
  - `frontend/src/components/shared/WaveformCanvas.tsx` (modify — add zoom/scroll event handlers)
  - `frontend/src/hooks/useWaveformView.ts` (create — zoom/scroll state management)
- **Inputs:**
  - Zoom/scroll spec from WaveformCanvas section
  - `duration` prop for calculating bounds
- **Outputs:**
  - `useWaveformView(duration: number)` hook managing `viewStart`/`viewEnd` state
  - Mousewheel zoom: zooms in/out centered on cursor position. Range: full track to ~2 seconds.
  - Click-drag pan: horizontal drag to scroll when zoomed.
  - `onViewChange` callback fires on zoom/scroll
  - Double-click to reset to full track view
  - Zoom respects bounds (can't scroll past track start/end)
- **Acceptance Criteria:**
  - [ ] Mousewheel up zooms in, centered on cursor X position
  - [ ] Mousewheel down zooms out, centered on cursor X position
  - [ ] Zoom stops at minimum ~2 seconds visible
  - [ ] Zoom stops at maximum = full track duration
  - [ ] Click-drag pans the view horizontally when zoomed
  - [ ] View cannot scroll past track start (0) or end (duration)
  - [ ] Double-click resets to full track view
  - [ ] `onViewChange` callback fires with updated `viewStart`/`viewEnd`
  - [ ] Zoom/scroll is smooth (uses requestAnimationFrame)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — Zoom & Scroll section
- **Status:** [ ] Not started

### TASK-005: Bidirectional section ↔ waveform interaction
- **Layer:** Frontend-UI
- **Estimated effort:** 25 min
- **Depends on:** TASK-003, TASK-006
- **Scope:**
  - `frontend/src/components/shared/WaveformCanvas.tsx` (modify — add section hover/click detection)
  - `frontend/src/components/analysis/AnalysisViewer.tsx` (create — orchestration component)
- **Inputs:**
  - `onSectionHover`, `onSectionClick` callbacks on `WaveformCanvas`
  - `SectionList` selection/highlight callbacks
- **Outputs:**
  - `AnalysisViewer` component orchestrating state between `WaveformCanvas` and `SectionList`:
    - `highlightedSectionIndex` (hover, transient)
    - `selectedSectionIndex` (click, persistent)
  - **Hover waveform section → highlights section row** in list
  - **Click waveform section → selects section row** and scrolls it into view
  - **Click section row → waveform scrolls/zooms** to show that section (~80% width)
  - **Hover section row → highlights section** on waveform
  - Hit detection on canvas: map mouse X position to time, find which section contains that time
- **Acceptance Criteria:**
  - [ ] Hovering over a section region on the canvas highlights the corresponding row in SectionList
  - [ ] Clicking a section region on the canvas selects the corresponding row and scrolls it into view
  - [ ] Hovering a row in SectionList highlights the corresponding section on the canvas
  - [ ] Clicking a row in SectionList scrolls/zooms the waveform to show that section
  - [ ] The waveform view adjusts so the clicked section fills ~80% of the canvas width
  - [ ] Highlight clears when mouse leaves a section (both directions)
  - [ ] Selection persists until another section is clicked
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — Bidirectional Highlight section
- **Status:** [ ] Not started

### TASK-006: SectionList component with filtering
- **Layer:** Frontend-UI
- **Estimated effort:** 25 min
- **Depends on:** TASK-001 (needs `TrackAnalysis` data)
- **Scope:**
  - `frontend/src/components/analysis/SectionList.tsx` (create)
  - `frontend/src/components/analysis/SectionFilterBar.tsx` (create)
  - `frontend/src/components/analysis/SectionRow.tsx` (create)
- **Inputs:**
  - `Section[]` from `TrackAnalysis`
  - Section row format from spec
  - Filter chip UI from spec
- **Outputs:**
  - `SectionList` component: scrollable list of sections with filter bar
  - `SectionFilterBar`: toggleable chips per section type + "All" reset chip
  - `SectionRow`: single row showing index, label (color-coded), start/end (M:SS.s), bars (bar_count/expected, highlighted if irregular), confidence (color-coded), source badge
  - Props: `sections`, `highlightedIndex`, `selectedIndex`, `onHover(index)`, `onSelect(index)`
  - Selected row has persistent highlight, hovered row has transient highlight
  - List scrolls to keep selected row visible
- **Acceptance Criteria:**
  - [ ] SectionList renders all sections as rows
  - [ ] Each row shows: index, label (colored), start time, end time, bars, confidence, source
  - [ ] Time formatted as `M:SS.s` (minutes:seconds.tenths)
  - [ ] Irregular phrases (bar_count != expected_bar_count) have bars field highlighted
  - [ ] Confidence color: red < 0.5, yellow 0.5-0.7, green > 0.7
  - [ ] Source shown as small badge ("analysis" / "pioneer_enriched")
  - [ ] Filter chips toggle section types; "All" resets filter
  - [ ] `highlightedIndex` prop highlights a row (transient, lighter)
  - [ ] `selectedIndex` prop highlights a row (persistent, stronger)
  - [ ] List auto-scrolls to keep selected row visible
  - [ ] `onHover` fires on row mouseenter/leave, `onSelect` fires on row click
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — Section List section
  - `frontend/src/types/track.ts` — `Section`, `SectionLabel`
- **Status:** [ ] Not started

### TASK-007: TrackMetadataPanel + PlaceholderPanel components
- **Layer:** Frontend-UI
- **Estimated effort:** 20 min
- **Depends on:** TASK-001 (needs `TrackAnalysis` data)
- **Scope:**
  - `frontend/src/components/analysis/TrackMetadataPanel.tsx` (create)
  - `frontend/src/components/shared/PlaceholderPanel.tsx` (create)
- **Inputs:**
  - Metadata fields from spec (Track Metadata Panel section)
  - Placeholder panel design from spec
- **Outputs:**
  - `TrackMetadataPanel`: props-driven panel showing all fields from spec (title, artist, BPM, key, mood, duration, sections count, source, version, fingerprint, etc.). Shows Pioneer values alongside analysis values when enrichment exists. Fingerprint truncated with copy-on-click.
  - `PlaceholderPanel`: generic bordered box with header text and muted body text. Used for "Musical Events (Tier 2)" and "Analysis Parameters" placeholders.
- **Acceptance Criteria:**
  - [ ] `TrackMetadataPanel` displays all fields from the spec's metadata table
  - [ ] Pioneer enrichment values (pioneer_bpm, pioneer_key) shown alongside analysis values when present
  - [ ] Fingerprint displayed truncated, full value copied to clipboard on click
  - [ ] rekordbox_id shown when present
  - [ ] Mood displayed as a badge
  - [ ] Key confidence color-coded
  - [ ] `PlaceholderPanel` renders a bordered box with header and muted subtitle
  - [ ] Two placeholder instances: "Musical Events — coming in Milestone 7" and "Analysis Parameters — coming soon"
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — Track Metadata Panel, Placeholder Panels
  - `frontend/src/types/track.ts` — `TrackAnalysis`, `TrackFeatures`
- **Status:** [ ] Not started

### TASK-008: Page assembly + routing + sidebar
- **Layer:** Frontend-UI
- **Estimated effort:** 20 min
- **Depends on:** TASK-005, TASK-007
- **Scope:**
  - `frontend/src/pages/AnalysisViewerPage.tsx` (create)
  - `frontend/src/App.tsx` (modify — add route)
  - `frontend/src/components/layout/Sidebar.tsx` (modify — add nav entries)
- **Inputs:**
  - All components from TASK-001 through TASK-007
  - Routing/sidebar spec
- **Outputs:**
  - `AnalysisViewerPage`: page shell composing `TrackPicker` + `AnalysisViewer` + `TrackMetadataPanel` + `PlaceholderPanel`s. Manages `selectedFingerprint` state.
  - Route `<Route path="analysis" element={<AnalysisViewerPage />} />` added to `App.tsx`
  - Sidebar updated with top-level "Analysis" and "Live Monitor" entries (both added now even though Live Monitor page comes later)
  - Loading/empty/error states as specified
- **Acceptance Criteria:**
  - [ ] `/analysis` route renders `AnalysisViewerPage`
  - [ ] Sidebar shows "Analysis" and "Live Monitor" as top-level entries above the "Data" group
  - [ ] No track selected: shows "Select a track above to view analysis" in waveform area
  - [ ] Track selected: TrackPicker row highlighted, AnalysisViewer renders with full data
  - [ ] Loading state: skeleton/pulse in waveform area while fetching
  - [ ] Error state: red message below track picker
  - [ ] No waveform data: appropriate message in waveform area, section list + metadata still render
  - [ ] Bottom grid: section list (left), metadata (center), placeholders (right) at lg breakpoint; stacks on narrow screens
  - [ ] Page is thin (<100 lines per project convention)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-analysis-viewer/spec.md` — Page Layout, Navigation, Loading/Empty/Error States
  - `frontend/src/App.tsx` — routing pattern
  - `frontend/src/components/layout/Sidebar.tsx` — nav items
  - `frontend/src/pages/TracksPage.tsx` — reference for thin page pattern
- **Status:** [ ] Not started
