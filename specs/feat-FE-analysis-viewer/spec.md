# Spec: FE-Analysis-Viewer

## Summary

A standalone page for viewing TrackAnalysis results. Displays a Pioneer-style colored waveform (rendered from analysis RGB 3-band data) with section overlays, an energy curve overlay, a filterable/selectable section list with bidirectional highlighting, and minimal placeholders for future Tier 2 events and parameter tweaking. Read-only for v1 — no editing of analysis data. Intended for prep and debugging use.

Route: `/analysis`
Sidebar: Top-level entry "Analysis" (not nested under Data or System).

---

## User-Facing Behavior

The user arrives at `/analysis` and sees a mini track table at the top. They select a track, and the page loads the full `TrackAnalysis` (via `GET /api/tracks/:fingerprint`). Below the picker, a zoomable/scrollable waveform canvas renders with section overlays and an energy curve. A section list panel provides bidirectional interaction with the waveform. Minimal placeholder panels for Tier 2 events and parameter tweaking are present but collapsed.

---

## Page Layout

```
+----------------------------------------------------------+
| Track Picker (mini table — title, artist, BPM, key, dur) |
+----------------------------------------------------------+
| Waveform Canvas (scroll + zoom)                          |
| [section overlays + energy curve overlay]                 |
+----------------------------------------------------------+
| Section List          | Track Metadata     | Placeholders |
| (filterable,          | (BPM, key, mood,   | [Events M7]  |
|  selectable,          |  source, duration,  | [Params]     |
|  bidirectional)       |  fingerprint, etc.) |              |
+----------------------------------------------------------+
```

- **Top:** Mini track table for selection (compact, sortable, filterable).
- **Middle:** Full-width waveform canvas with horizontal scroll and zoom. Section boundaries overlaid as colored regions. Energy curve as semi-transparent overlay line.
- **Bottom:** Three-column grid (lg breakpoint).
  - Left: Section list with filter + selection.
  - Center: Track metadata panel.
  - Right: Placeholder panels (collapsed).

On narrower screens (<1024px), the bottom section stacks vertically.

---

## Component Hierarchy

```
AnalysisViewerPage
  TrackPicker (mini table)
  AnalysisViewer (shown when track selected)
    WaveformCanvas (shared component — Canvas 2D)
      SectionOverlay (colored regions per section)
      EnergyOverlay (semi-transparent line from features.energy_curve)
      PlaybackCursor (v1: static time marker on click; live in Deck Monitor)
    SectionList
      SectionFilterBar (filter by label type)
      SectionRow (repeated)
    TrackMetadataPanel
    PlaceholderPanel (x2: "Musical Events" + "Analysis Parameters")
```

### Component Responsibilities

| Component | Reusable? | Notes |
|-----------|-----------|-------|
| `AnalysisViewerPage` | No | Page shell. Manages selected fingerprint state. |
| `TrackPicker` | Yes | Mini track table. Accepts `onSelect(fingerprint)` callback. Reuses `useTracks` hook. |
| `AnalysisViewer` | No | Orchestrates waveform + section list + metadata. Fetches `TrackAnalysis` via new `useTrackAnalysis(fingerprint)` hook. |
| `WaveformCanvas` | **Yes** | Core shared component. Accepts `RGBWaveform`, optional section + energy data, zoom/scroll state. Used by both Analysis Viewer and Live Deck Monitor. Canvas 2D rendering. |
| `SectionOverlay` | Internal | Renders colored regions on the canvas for each section. Part of WaveformCanvas rendering logic. |
| `EnergyOverlay` | Internal | Renders energy curve line on the canvas. Part of WaveformCanvas rendering logic. |
| `SectionList` | Yes | Filterable, selectable section list. Accepts sections array + callbacks. |
| `SectionRow` | Yes | Single section row. Presentational. |
| `TrackMetadataPanel` | Yes | Displays track-level metadata. Props-driven. |
| `PlaceholderPanel` | Yes | Generic collapsed placeholder with title + subtitle. |

---

## Data Flow

### Track Selection

1. `TrackPicker` renders tracks from `useTracks({ limit: 1000 })` (existing hook).
2. User clicks a row → `onSelect(fingerprint)` fires.
3. `AnalysisViewerPage` sets `selectedFingerprint` state.
4. `AnalysisViewer` receives fingerprint, calls `useTrackAnalysis(fingerprint)`.

### New TanStack Query Hook

```typescript
// frontend/src/api/tracks.ts — new hook
export function useTrackAnalysis(fingerprint: string | null) {
  return useQuery<TrackAnalysis>({
    queryKey: ["track-analysis", fingerprint],
    queryFn: () => apiFetch<TrackAnalysis>(`/tracks/${fingerprint}`),
    enabled: fingerprint !== null,
  });
}
```

No new backend endpoints needed. `GET /api/tracks/:fingerprint` already exists and returns the full `TrackAnalysis` with waveform data.

---

## WaveformCanvas — Shared Component

### Props

```typescript
interface WaveformCanvasProps {
  waveform: RGBWaveform;                // 3-band data at 60fps
  sections?: Section[];                  // section overlays
  energyCurve?: number[];                // Tier 3 energy overlay
  duration: number;                      // track duration in seconds

  // Interaction
  highlightedSection?: number | null;    // index of section to highlight
  onSectionHover?: (index: number | null) => void;
  onSectionClick?: (index: number) => void;
  onTimeClick?: (seconds: number) => void;

  // Cursor (for Live Deck Monitor)
  cursorPosition?: number | null;        // seconds — renders a vertical line

  // Zoom/scroll (controlled externally)
  viewStart: number;                     // visible window start (seconds)
  viewEnd: number;                       // visible window end (seconds)
  onViewChange?: (start: number, end: number) => void;
}
```

### Rendering

**Canvas 2D.** The waveform is rendered as vertical bars, one per sample in the visible range. Each bar is colored by mixing the three frequency bands:

- **Bass (low):** Blue `#0066FF`
- **Mids (mid):** Green `#00CC66`
- **Highs (high):** Red/Magenta `#FF3366`

Each sample's color is computed by mixing these three channels based on their relative amplitudes. When all three are high, the result trends toward white — matching rekordbox's Pioneer-style rendering.

**Color mixing algorithm:**
```
r = high * 255         // highs drive red channel
g = mid * 180          // mids drive green channel
b = low * 255          // bass drives blue channel
// Clamp to 0-255, apply as rgb()
```

Bar height is the max of the three band values at that sample, normalized to the canvas height. Bars extend from center (mirrored top/bottom like rekordbox).

**Section overlays:** Semi-transparent colored regions behind the waveform bars. Each section type gets a distinct color:

| Label | Color | Tailwind Reference |
|-------|-------|--------------------|
| intro | `rgba(100, 100, 100, 0.15)` | gray |
| verse | `rgba(59, 130, 246, 0.15)` | blue |
| build | `rgba(234, 179, 8, 0.15)` | yellow |
| drop | `rgba(239, 68, 68, 0.2)` | red (slightly more opaque) |
| breakdown | `rgba(168, 85, 247, 0.15)` | purple |
| fakeout | `rgba(239, 68, 68, 0.1)` | red (faint, dashed border) |
| outro | `rgba(100, 100, 100, 0.15)` | gray |

Section boundaries are drawn as thin vertical lines. The section label is rendered at the top-left of each region (small, `10px` font).

**Energy curve overlay:** A semi-transparent white line (`rgba(255, 255, 255, 0.4)`) drawn over the waveform, mapping `energy_curve` values (0.0-1.0) to the canvas height. The energy curve has ~2 samples/sec (one per ~0.5s), so it's much coarser than the waveform — interpolate linearly between points.

**Highlighted section:** When `highlightedSection` is set, the corresponding section overlay brightens (double the alpha) and gets a solid border.

### Zoom & Scroll

- **Default view:** Entire track visible (`viewStart=0`, `viewEnd=duration`).
- **Zoom:** Mousewheel (or pinch) zooms in/out centered on the cursor position. Zoom range: full track down to ~2 seconds visible.
- **Scroll:** Click-drag horizontally to pan. When zoomed, scrollbar or drag to move through the track.
- **Zoom state** is managed by the parent component (`AnalysisViewer`), not internal to `WaveformCanvas`. This allows the Live Deck Monitor to control the view (auto-scroll to cursor position).

### Performance

- At full zoom-out on a 5-minute track: ~18,000 samples. At typical canvas width (~1200px), this is ~15 samples per pixel. Downsample by taking the max of each pixel-bucket — standard waveform rendering technique.
- At full zoom-in (~2 seconds visible): ~120 samples for ~1200px = ~10px per bar. No downsampling needed.
- Re-render on: view change (zoom/scroll), section highlight change, cursor position change. Use `requestAnimationFrame` for smooth zoom/scroll.
- **WebGL stretch goal:** If Canvas 2D proves too slow during rapid zoom/scroll on large tracks, migrate to WebGL. The rendering logic (vertical bars, color mixing) maps directly to a vertex shader.

---

## Section List

### Layout

A panel below the waveform (left column in the 3-column grid). Contains:

1. **Filter bar:** Row of toggleable chips, one per section type (intro, verse, build, drop, breakdown, fakeout, outro). Clicking a chip toggles visibility. "All" chip resets filter.
2. **Section rows:** Scrollable list of sections matching the active filter.

### Section Row

```
| # | Label    | Start   | End     | Bars  | Confidence | Source  |
|---|----------|---------|---------|-------|------------|---------|
| 1 | drop     | 1:32.0  | 2:28.5  | 16/16 | 0.85       | analysis|
| 2 | breakdown| 2:28.5  | 3:24.0  | 16/16 | 0.72       | analysis|
```

- `#` = section index (1-based).
- `Label` = section type, color-coded to match waveform overlay colors.
- `Start` / `End` = formatted as `M:SS.s` (minutes, seconds, tenths).
- `Bars` = `bar_count/expected_bar_count`. Highlighted if `irregular_phrase === true`.
- `Confidence` = 0.00-1.00, color gradient (red < 0.5, yellow 0.5-0.7, green > 0.7).
- `Source` = "analysis" or "pioneer_enriched", as a small badge.

### Bidirectional Highlight

- **Click section row → waveform scrolls/zooms** to show that section. The view adjusts so the section fills ~80% of the visible canvas width (with some padding on both sides). The section overlay brightens.
- **Hover waveform section → section row highlights** in the list. The hovered section gets a brighter background in the list.
- **Click waveform section → section row scrolls into view** and gets selected (persistent highlight until another click).

State management: `AnalysisViewer` holds `highlightedSectionIndex: number | null` and `selectedSectionIndex: number | null`. Highlighted = hover (transient). Selected = click (persistent). Both are passed to `WaveformCanvas` and `SectionList`.

---

## Track Metadata Panel

Displays in the center column of the bottom grid:

| Field | Source | Format |
|-------|--------|--------|
| Title | `analysis.title` | Plain text |
| Artist | `analysis.artist` | Plain text |
| BPM | `analysis.bpm` | `128.00` |
| Key | `analysis.features.key` | e.g., "Cm" |
| Key Confidence | `analysis.features.key_confidence` | `0.85` with color |
| Mood | `analysis.features.mood` | Badge (dark/euphoric/etc.) |
| Danceability | `analysis.features.danceability` | `0.75` |
| Duration | `analysis.duration` | `M:SS` |
| Sections | `analysis.sections.length` | Count |
| Source | `analysis.source` | Badge |
| Version | `analysis.version` | Number |
| Beatgrid Source | `analysis.beatgrid_source` | Badge |
| Fingerprint | `analysis.fingerprint` | Truncated, copy-on-click |
| Created | `analysis.created_at` | Date string |

If Pioneer enrichment exists (`pioneer_bpm`, `pioneer_key`):
- Show Pioneer values alongside analysis values for comparison.
- If `rekordbox_id` is set, display it.

---

## Placeholder Panels

Two minimal collapsed panels in the right column:

1. **Musical Events (Tier 2)**
   - Header: "Musical Events"
   - Body: Gray text "Event detection coming in Milestone 7"
   - If `analysis.events.length > 0` (future), show event count badge on header.

2. **Analysis Parameters**
   - Header: "Analysis Parameters"
   - Body: Gray text "Parameter tweaking coming soon"

Both use a shared `PlaceholderPanel` component: a bordered box with a header and muted body text. Not collapsible/expandable — just static content.

---

## Track Picker (Mini Table)

A compact version of the TracksPage table, positioned at the top of the page. Shows:

| Column | Width | Sortable |
|--------|-------|----------|
| Title | flexible | Yes |
| Artist | flexible | Yes |
| BPM | 60px | Yes |
| Key | 50px | Yes |
| Duration | 70px | Yes |
| Sections | 60px | Yes |

- Height: capped at `max-h-48` (192px) with overflow scroll when many tracks.
- Includes a search/filter input above the table.
- Clicking a row selects the track (highlighted) and triggers analysis fetch.
- Selected row stays highlighted.
- Uses `useTracks` existing hook for data.

---

## Navigation & Routing

**Sidebar change:**

```typescript
// Sidebar.tsx — add top-level entry
const navItems = [
  { to: "/analysis", label: "Analysis" },     // NEW — top-level
  { to: "/live", label: "Live Monitor" },      // NEW — top-level
  { label: "Data", header: true },
  { to: "/data/db", label: "Tracks" },
  { to: "/data/bridge", label: "Bridge" },
  { to: "/data/enrichment", label: "Enrichment" },
  { label: "System", header: true },
  { to: "/logs", label: "Logs" },
  { to: "/network", label: "Network" },
];
```

**Route:** Add `<Route path="analysis" element={<AnalysisViewerPage />} />` to `App.tsx`.

---

## Loading / Empty / Error States

| State | Display |
|-------|---------|
| **No track selected** | Waveform area shows centered muted text: "Select a track above to view analysis" |
| **Loading analysis** | Waveform area shows skeleton pulse animation (gray bar) |
| **Analysis loaded, no waveform** | Waveform area shows "No waveform data — re-analyze with waveform enabled" |
| **Analysis loaded, no sections** | Section list shows "No sections detected" |
| **Fetch error** | Red error message below track picker |
| **Track list loading** | Track picker shows "Loading tracks..." |

---

## v1 Scope Constraints

### In Scope
- `AnalysisViewerPage` with track picker, waveform canvas, section list, metadata panel
- `WaveformCanvas` shared component (Canvas 2D, zoom/scroll, section overlays, energy overlay)
- `useTrackAnalysis` TanStack Query hook
- Bidirectional section list ↔ waveform interaction
- Section filter by label type
- Sidebar + routing changes (Analysis + Live Monitor entries)
- Placeholder panels for Tier 2 events and parameter tweaking

### Out of Scope
- Editing analysis data (sections, labels, boundaries)
- Audio playback
- Waveform data generation (that's Layer 1 analysis)
- Tier 2 event display (M7)
- Parameter tweaking UI
- WebGL rendering (stretch goal only)
- Mobile/touch optimization

---

## Design Decisions Summary

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|---------------------|
| 1 | Standalone page with mini track table | Analysis inspection is a distinct workflow from track management. Self-contained page avoids coupling to TracksPage routing. | Drill-down from TracksPage (couples navigation) |
| 2 | Canvas 2D (WebGL stretch) | 18K points is well within Canvas 2D capability. WebGL adds complexity without proven need. | SVG (too many DOM nodes), WebGL-first (premature optimization) |
| 3 | Zoom/scroll with controlled view state | Parent controls view state so Live Deck Monitor can auto-scroll. Keeps WaveformCanvas stateless re: navigation. | Internal zoom state (can't control from outside) |
| 4 | Shared WaveformCanvas component | Both screens render the same data shape. Sharing avoids duplicate rendering logic. Fork if needs diverge. | Separate implementations (duplicated code) |
| 5 | Pioneer-style color mixing (R=high, G=mid, B=low) | Matches industry standard. DJs immediately recognize the visual language. | Custom color scheme (unfamiliar), raw amplitude (no frequency info) |
| 6 | Energy curve as overlay | Shows energy contour in spatial context with the waveform. Separate strip wastes vertical space for a coarse signal. | Separate chart strip, skip entirely |
| 7 | Mini track table (not dropdown) | Sortable/filterable for libraries of any size. Combobox breaks at >100 tracks. | Combobox (doesn't scale), full TracksPage embed (too heavy) |
| 8 | Bidirectional highlight with scroll-on-click | Most polished interaction for section inspection workflow. Low additional wiring cost over highlight-only. | Highlight only (less useful), one-directional (inconsistent) |

---

## Edge Cases

| Edge Case | Expected Behavior |
|-----------|------------------|
| Track with no waveform data | Show message "No waveform data". Section list and metadata still render. |
| Track with 0 sections | Section list shows empty state. Waveform renders without overlays. |
| Very short track (<10s) | Zoom minimum still works. Full track visible at default zoom. |
| Very long track (>30 min, DJ mix) | Waveform downsamples aggressively at full zoom. Scroll/zoom still functional. |
| Energy curve length doesn't match duration | Interpolate to fit. If empty, skip overlay. |
| Track selected while previous is loading | Cancel previous query (TanStack Query handles this via queryKey change). |
| Waveform bands have different lengths | Use the shortest length. Log warning. |
| Section with confidence < 0.3 | Render with dashed border and faint overlay to indicate low confidence. |
| Pioneer-enriched sections mixed with analysis | Show source badge per section. Both render the same way on the waveform. |
