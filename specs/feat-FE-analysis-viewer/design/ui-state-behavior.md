# UI State Behavior: Analysis Viewer Page

> Maps system states to expected component display for every component in the
> Analysis Viewer page. This is the source of truth for what each component should
> show in each state. Developers implement against it; Validators and QA Testers
> verify against it.

---

## States Reference

The Analysis Viewer is a **data-inspection page** with no real-time bridge dependency.
Its states are simpler than the Bridge page — they are driven by data-fetching lifecycle,
not bridge/hardware lifecycle.

| Dimension | Possible Values |
|---|---|
| Track list fetch | `loading`, `loaded`, `error`, `empty` (0 tracks) |
| Track selection | `none` (no track selected), `selected` (fingerprint set) |
| Analysis fetch | `idle` (no fingerprint), `loading`, `loaded`, `error` |
| Waveform data | `present` (waveform is non-null), `absent` (waveform is null) |
| Section data | `present` (sections.length > 0), `absent` (sections.length === 0) |
| Energy curve | `present` (features.energy_curve.length > 0), `absent` (empty or missing) |

### Derived Page States

These are the primary compound states the page can be in:

| # | State Key | Conditions |
|---|-----------|-----------|
| P1 | Track list loading | Track list query in flight |
| P2 | Track list error | Track list query failed |
| P3 | Track list empty | Track list returned 0 tracks |
| P4 | No track selected | Track list loaded, no fingerprint selected |
| P5 | Analysis loading | Fingerprint selected, analysis query in flight |
| P6 | Analysis error | Analysis query failed |
| P7 | Full data | Analysis loaded, waveform present, sections present |
| P8 | No waveform | Analysis loaded, waveform is null |
| P9 | No sections | Analysis loaded, sections.length === 0 |
| P10 | No energy curve | Analysis loaded, energy_curve empty or missing |

**P8, P9, P10 are independent and can combine** (e.g., analysis loaded with no waveform AND no sections).

---

## Component: TrackPicker

The mini table at the top of the page. Uses `useTracks` hook.

| System State | Expected Display | Notes |
|---|---|---|
| P1: Track list loading | Muted text centered in the table area: "Loading tracks..." with a pulsing opacity animation (`animate-pulse`). Table header row still renders (skeleton). | Pulsing text confirms the system is alive. |
| P2: Track list error | Red text below the search input: "Failed to load tracks: {error.message}". Retry is automatic via TanStack Query (background refetch). | Use `text-red-400 text-sm`. No manual retry button needed — TanStack handles it. |
| P3: Track list empty | Muted text centered in the table body: "No analyzed tracks found. Run analysis on some tracks first." | `text-gray-500 text-sm`. This is a valid state — the user may not have analyzed anything yet. |
| P4: No track selected | Table renders normally. No row highlighted. Search input active. | Default state on page load. |
| P5-P10: Track selected | Selected row has persistent highlight (`bg-blue-900/30 text-white`). Table remains interactive — user can select a different track. | Clicking another row changes selection, cancels any in-flight analysis fetch (TanStack handles via queryKey change). |

### Search/Filter Behavior

- Search input: `w-full px-3 py-1.5 text-sm bg-gray-900 border border-gray-700 rounded text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-500`
- Placeholder text: "Filter by title or artist..."
- Filters rows by case-insensitive substring match on `title` or `artist`.
- When filter produces 0 results: show "No tracks match filter" in the table body (`text-gray-500 text-sm`).
- Clearing the filter restores all rows.

### Table Styling

- Container: `rounded border border-gray-800 bg-gray-950 max-h-48 overflow-y-auto`
- Header row: `border-b border-gray-800 bg-gray-900 sticky top-0`
- Header cells: `text-xs font-medium text-gray-400 uppercase tracking-wider px-2 py-1.5`
- Body rows: `border-b border-gray-800/50 text-gray-300 hover:bg-gray-800/30 cursor-pointer transition-colors text-sm`
- Selected row: `bg-blue-900/30 text-white`
- Cell padding: `px-2 py-1.5 whitespace-nowrap`

---

## Component: AnalysisViewer (Orchestrator)

The main content area below the TrackPicker. Not rendered until a track is selected.

| System State | Expected Display | Notes |
|---|---|---|
| P4: No track selected | Centered muted text in the content area: "Select a track above to view analysis". Full height of the content area (fills available space below TrackPicker). | `text-gray-500 text-sm`. Center with flexbox: `flex items-center justify-center`. Min-height: `min-h-[300px]`. |
| P5: Analysis loading | Skeleton pulse in the waveform area (gray bar, `animate-pulse`, `bg-gray-800 rounded h-48`). Section list and metadata panels show individual loading states. | Skeleton matches approximate waveform area dimensions. |
| P6: Analysis error | Red error message below the TrackPicker: "Failed to load analysis for this track: {error.message}". Waveform area, section list, and metadata panel are NOT rendered. | `text-red-400 text-sm`. The error replaces the entire content area. |
| P7: Full data | All sub-components render with data. Waveform canvas + section overlays + energy curve. Section list populated. Metadata panel populated. Placeholders shown. | Normal happy path. |
| P8: No waveform | Waveform area shows centered text: "No waveform data -- re-analyze with waveform enabled". Section list and metadata panel still render normally. | `text-gray-500 text-sm` in a bordered box (`rounded border border-gray-800 bg-gray-950 h-48 flex items-center justify-center`). The rest of the page is functional. |
| P9: No sections | Waveform renders without section overlays. Section list shows its own empty state (see SectionList below). | Energy curve and waveform still render. |
| P10: No energy curve | Waveform renders without energy curve overlay. Everything else normal. | Graceful degradation — no error message needed. |

### State Management

`AnalysisViewer` holds:
- `highlightedSectionIndex: number | null` — hover (transient). Set on mouseenter, cleared on mouseleave.
- `selectedSectionIndex: number | null` — click (persistent). Set on click, cleared only by clicking another section.

These are passed to both `WaveformCanvas` and `SectionList` for bidirectional interaction.

### Layout

```
[WaveformCanvas — full width]
[Bottom grid: 3 columns on lg, stacked on smaller]
  [Left: SectionList]
  [Center: TrackMetadataPanel]
  [Right: PlaceholderPanels (stacked)]
```

Bottom grid: `grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4`

---

## Component: WaveformCanvas (Shared)

Core shared component. Used by both Analysis Viewer (zoom/scroll, click-to-select) and
Live Deck Monitor (auto-scroll, cursor, no user interaction).

### State Behavior in Analysis Viewer Context

| System State | Expected Display | Notes |
|---|---|---|
| P5: Analysis loading | Not rendered. Parent shows skeleton. | WaveformCanvas is only mounted when analysis data is available. |
| P7: Full data | Canvas renders colored vertical bars (bass=blue, mids=green, highs=magenta). Section overlays behind bars. Energy curve as white semi-transparent line on top. | Full rendering pipeline active. |
| P8: No waveform | Not rendered. Parent shows "No waveform data" message. | WaveformCanvas requires `waveform` prop. |
| P9: No sections | Canvas renders waveform bars only. No section overlays. No section boundary lines. No section labels. | `sections` prop is optional — empty array or undefined skips overlay rendering. |
| P10: No energy curve | Canvas renders waveform bars + section overlays. No energy line. | `energyCurve` prop is optional — empty array or undefined skips energy rendering. |
| Section highlighted (hover) | Highlighted section overlay doubles alpha and gets a solid 1px border. All other sections remain at base alpha. | Transition should feel immediate (no animation delay). |
| Section selected (click) | Same visual as highlighted, but persistent. If a different section is hovered while one is selected, both show enhanced styling. | Selected takes priority if both selected and highlighted are the same index. |
| Zoomed in | Only samples within `[viewStart, viewEnd]` rendered. Bars get wider as fewer samples fit. Section overlays clip to visible range. Energy curve clips to visible range. | Canvas re-renders on every view change via `requestAnimationFrame`. |
| Zoomed out (default) | Entire track visible. Downsamples by max-per-pixel-bucket. All sections visible. | Default: `viewStart=0, viewEnd=duration`. |

### Shared Props Interface (Analysis Viewer + Live Deck Monitor)

```typescript
interface WaveformCanvasProps {
  // Required
  waveform: RGBWaveform;
  duration: number;
  viewStart: number;
  viewEnd: number;

  // Optional data overlays
  sections?: Section[];
  energyCurve?: number[];

  // Optional interaction (Analysis Viewer uses these)
  highlightedSection?: number | null;
  onSectionHover?: (index: number | null) => void;
  onSectionClick?: (index: number) => void;
  onTimeClick?: (seconds: number) => void;
  onViewChange?: (start: number, end: number) => void;

  // Optional cursor (Live Deck Monitor uses this)
  cursorPosition?: number | null;
}
```

**Analysis Viewer usage:**
- Passes: `waveform`, `duration`, `viewStart`, `viewEnd`, `sections`, `energyCurve`, `highlightedSection`, `onSectionHover`, `onSectionClick`, `onViewChange`
- Does NOT pass: `cursorPosition` (no live playback)
- Zoom/scroll enabled via `onViewChange`

**Live Deck Monitor usage:**
- Passes: `waveform`, `duration`, `viewStart`, `viewEnd`, `sections`, `cursorPosition`, `highlightedSection`
- Does NOT pass: `onSectionHover`, `onSectionClick`, `onViewChange`, `energyCurve` (auto-scroll, no user interaction)
- Zoom/scroll controlled externally (auto-follow cursor)

### Canvas Container Styling

- Wrapper: `w-full bg-gray-950 rounded border border-gray-800`
- Canvas element fills parent width via `ResizeObserver`.
- Fixed height: `h-48` (192px) in Analysis Viewer. Live Deck Monitor may vary (50% viewport share).
- No padding inside the canvas area — waveform renders edge-to-edge within the border.

### Rendering Details

**Waveform bars:**
- Extend from center (mirrored top/bottom).
- Color per spec: `r = high * 255`, `g = mid * 180`, `b = low * 255`.
- Bar height = `max(low, mid, high)` normalized to half canvas height.
- At full zoom-out: downsample via max-per-pixel-bucket.
- At full zoom-in (~2s visible): ~10px per bar, no downsampling.

**Section overlays (rendered BEHIND waveform bars):**

| Label | Fill Color | Border |
|---|---|---|
| intro | `rgba(100, 100, 100, 0.15)` | `rgba(100, 100, 100, 0.4)` solid 1px |
| verse | `rgba(59, 130, 246, 0.15)` | `rgba(59, 130, 246, 0.4)` solid 1px |
| build | `rgba(234, 179, 8, 0.15)` | `rgba(234, 179, 8, 0.4)` solid 1px |
| drop | `rgba(239, 68, 68, 0.2)` | `rgba(239, 68, 68, 0.5)` solid 1px |
| breakdown | `rgba(168, 85, 247, 0.15)` | `rgba(168, 85, 247, 0.4)` solid 1px |
| fakeout | `rgba(239, 68, 68, 0.1)` | `rgba(239, 68, 68, 0.3)` dashed 1px |
| outro | `rgba(100, 100, 100, 0.15)` | `rgba(100, 100, 100, 0.4)` solid 1px |

**Highlighted section:** Fill alpha doubled (e.g., 0.15 -> 0.30). Border becomes solid 2px (even for fakeout).

**Low-confidence sections (confidence < 0.3):** Border style forced to dashed. Fill alpha halved (e.g., 0.15 -> 0.075). Visually distinct from confident sections.

**Section labels:** Rendered at top-left of each section region. Font: 10px, `rgba(255, 255, 255, 0.6)`. Only rendered when the section is wide enough (>40px on screen) to avoid label overlap at full zoom-out.

**Energy curve:** White semi-transparent line (`rgba(255, 255, 255, 0.4)`) drawn OVER waveform bars. Linearly interpolated between coarse data points (~2 samples/sec). Y-axis: 0.0 at bottom, 1.0 at top of canvas.

**Cursor line (Live Deck Monitor only):** White 2px vertical line, full canvas height. `rgba(255, 255, 255, 0.9)` main line with `rgba(255, 255, 255, 0.3)` 2px glow on each side.

---

## Component: SectionList

Filterable, selectable section list in the bottom-left column.

| System State | Expected Display | Notes |
|---|---|---|
| P5: Analysis loading | Skeleton: 3 pulsing rows (`animate-pulse bg-gray-800 rounded h-6 mb-2`). Filter bar not shown during loading. | Matches approximate row height. |
| P7: Full data | Filter bar + scrollable list of section rows. All sections shown by default (All filter active). | Normal happy path. |
| P9: No sections | Filter bar hidden. Centered muted text: "No sections detected". | `text-gray-500 text-sm` in the list area. No filter needed when there's nothing to filter. |
| Filter active, 0 matches | Filter bar shown with active filters. List body: "No sections match filter". | `text-gray-500 text-sm`. User can click "All" to reset. |
| Section highlighted (hover) | Row gets lighter background: `bg-gray-800/50`. Transient — clears on mouseleave. | Must be visually distinct from selected. |
| Section selected (click) | Row gets persistent highlight: `bg-blue-900/30 text-white`. List auto-scrolls to keep selected row visible. | If another row is hovered while this one is selected, both have distinct highlights. |

### Container Styling

- Outer: `rounded border border-gray-800 bg-gray-950`
- Header: `text-xs font-semibold uppercase tracking-wider text-gray-500 px-3 py-2` — "Sections ({count})"
- List area: `max-h-64 overflow-y-auto` (256px max, scrollable)
- Empty state: centered in list area, `min-h-[100px]`

### SectionFilterBar

- Container: `flex flex-wrap gap-1.5 px-3 py-2 border-b border-gray-800`
- Each chip: `px-2 py-0.5 rounded text-xs cursor-pointer transition-colors`
- Active chip: color-coded to match section overlay color (e.g., drop chip is `bg-red-900/50 text-red-300`)
- Inactive chip: `bg-gray-800 text-gray-500 hover:text-gray-300`
- "All" chip: `bg-gray-700 text-gray-300` when active (all showing), `bg-gray-800 text-gray-500` when filters are active
- Clicking a chip toggles that section type's visibility. Multiple types can be active simultaneously.
- Clicking "All" resets to all types visible.

### SectionRow

Each row displays:

```
| #  | Label      | Start   | End     | Bars   | Confidence | Source     |
```

- Row: `flex items-center gap-2 px-3 py-1.5 text-sm border-b border-gray-800/50 cursor-pointer transition-colors`
- Index (`#`): `text-gray-500 w-6 text-right` — 1-based
- Label: Color-coded badge matching section overlay colors.

| Label | Badge Style |
|---|---|
| intro | `bg-gray-700/50 text-gray-300` |
| verse | `bg-blue-900/50 text-blue-300` |
| build | `bg-amber-900/50 text-amber-300` |
| drop | `bg-red-900/50 text-red-300` |
| breakdown | `bg-purple-900/50 text-purple-300` |
| fakeout | `bg-red-900/30 text-red-400 border border-dashed border-red-700` |
| outro | `bg-gray-700/50 text-gray-300` |

- Start / End: `text-gray-300 font-mono text-xs` — formatted as `M:SS.s`
- Bars: `text-gray-300 text-xs` — formatted as `bar_count/expected_bar_count`. If `irregular_phrase === true`: `text-amber-400 font-semibold` (amber highlight draws attention to irregular phrasing).
- Confidence: `text-xs font-mono` with color gradient:
  - `< 0.5`: `text-red-400`
  - `0.5 - 0.7`: `text-amber-400`
  - `> 0.7`: `text-green-400`
- Source: small badge `px-1.5 py-0.5 rounded text-[10px]`
  - `"analysis"`: `bg-gray-800 text-gray-400`
  - `"pioneer_enriched"`: `bg-green-900/50 text-green-300`

---

## Component: TrackMetadataPanel

Center column of the bottom grid. Displays track-level metadata.

| System State | Expected Display | Notes |
|---|---|---|
| P5: Analysis loading | Skeleton: 6 pulsing rows (`animate-pulse bg-gray-800 rounded h-4 mb-3`). | Approximate number of metadata fields visible. |
| P7: Full data | All metadata fields rendered in a vertical list. Pioneer enrichment fields shown when present. | Normal happy path. |
| P8: No waveform | All metadata fields render normally. Waveform absence doesn't affect metadata. | Metadata is independent of waveform data. |

### Container Styling

- Outer: `rounded border border-gray-800 bg-gray-950 px-4 py-3`
- Header: `text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3` — "Track Metadata"

### Field Rendering

Each field rendered as a row:
- Label: `text-xs text-gray-500` (left)
- Value: `text-sm text-gray-300` (right)
- Layout: `flex justify-between items-baseline py-1 border-b border-gray-800/30`

| Field | Format | Special Styling |
|---|---|---|
| Title | Plain text, truncated with `truncate` class | `text-white font-medium` (emphasized) |
| Artist | Plain text, truncated | `text-gray-300` |
| BPM | `128.00` (2 decimal places) | `font-mono text-sm` |
| Key | e.g., "Cm" | `text-gray-300` |
| Key Confidence | `0.85` | Color-coded same as section confidence (red/amber/green) |
| Mood | Badge | Uses existing `MOOD_COLORS` pattern: `px-2 py-0.5 rounded text-xs` |
| Danceability | `0.75` | `font-mono text-sm` |
| Duration | `M:SS` | `font-mono text-sm` |
| Sections | Count (e.g., "12") | `text-gray-300` |
| Source | Badge | Same badge style as SectionRow source |
| Version | Number | `text-gray-400 text-xs` |
| Beatgrid Source | Badge | Same badge style as source |
| Fingerprint | First 12 chars + "..." | `font-mono text-xs text-gray-400 cursor-pointer hover:text-gray-200`. Click copies full value to clipboard. Show brief "Copied!" tooltip on click. |
| Created | Date string (ISO) | `text-gray-400 text-xs` |

### Pioneer Enrichment Section

When `pioneer_bpm` or `pioneer_key` is non-null, render an additional section:

- Divider: `border-t border-gray-700 mt-3 pt-3`
- Sub-header: `text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2` — "Pioneer Enrichment"
- Pioneer BPM: shown alongside analysis BPM for comparison. If different: `text-amber-400` to draw attention.
- Pioneer Key: shown alongside analysis key.
- rekordbox_id: shown when non-null. `font-mono text-xs text-gray-400`.

---

## Component: PlaceholderPanel (x2)

Right column of the bottom grid. Two stacked instances.

| System State | Expected Display | Notes |
|---|---|---|
| All states (P4-P10) | Static bordered box with header and muted subtitle. Always rendered when AnalysisViewer is shown. Not affected by data states. | These are coming-soon placeholders — no data dependency. |

### Instances

1. **Musical Events**
   - Header: "Musical Events"
   - Subtitle: "Event detection coming in Milestone 7"
   - If `analysis.events.length > 0` (future): show count badge on header: `ml-2 px-1.5 py-0.5 rounded-full text-[10px] bg-blue-900/50 text-blue-300`

2. **Analysis Parameters**
   - Header: "Analysis Parameters"
   - Subtitle: "Parameter tweaking coming soon"

### Styling

- Container: `rounded border border-gray-800 bg-gray-950 px-4 py-3`
- Header: `text-xs font-semibold uppercase tracking-wider text-gray-500`
- Subtitle: `mt-1 text-xs text-gray-600`
- Two instances stacked with `flex flex-col gap-4` in the right column.

---

## Component: Zoom/Scroll Controls (via useWaveformView hook)

Not a visible component — interaction behavior on the WaveformCanvas.

| Interaction | Expected Behavior | Notes |
|---|---|---|
| Mousewheel up (on canvas) | Zoom in centered on cursor X position. View window narrows. Minimum visible: ~2 seconds. | `onViewChange(newStart, newEnd)` fires. |
| Mousewheel down (on canvas) | Zoom out centered on cursor X position. View window widens. Maximum visible: full track duration. | Returns to `viewStart=0, viewEnd=duration` at max zoom-out. |
| Click-drag horizontally (on canvas) | Pan the view when zoomed in. Cursor changes to `cursor-grab` on mousedown, `cursor-grabbing` during drag. | View cannot scroll past 0 or past duration. |
| Double-click (on canvas) | Reset to full track view (`viewStart=0, viewEnd=duration`). | Quick escape from any zoom level. |
| Click (on canvas, not drag) | `onTimeClick(seconds)` fires with the clicked time position. | Used for future cursor placement. Not wired to anything in v1 Analysis Viewer, but the event is available. |

### Zoom Behavior in Live Deck Monitor

In Live Deck Monitor context, `onViewChange` is NOT passed. The `useWaveformView` hook is not used. Instead, `DeckWaveform` computes `viewStart`/`viewEnd` to keep `cursorPosition` centered in a ~10-15 second window. No user interaction with zoom/scroll.

---

## Component: SectionIndicator (Shared)

A thin horizontal bar showing current section label + progress. Defined here for both contexts.

### Analysis Viewer Usage

Not used in v1 Analysis Viewer. The SectionList provides section inspection. Reserved for
future use or optional addition.

### Live Deck Monitor Usage

Rendered below each deck's metadata row.

| System State | Expected Display | Notes |
|---|---|---|
| No track loaded | Not rendered. | DeckEmptyState shown instead. |
| Track loaded, no sections | Muted text: "No sections" | `text-gray-500 text-xs` |
| Track loaded, cursor in a section | Current section label (left, color-coded badge), progress bar (colored, 0-100%), next section label (right, muted). | Progress = `(cursor - section.start) / (section.end - section.start)` |
| Track loaded, cursor between sections | "Between sections" (muted label), no progress bar. Next section label (right, muted). | Edge case if there are gaps in section coverage. |

### Props Interface

```typescript
interface SectionIndicatorProps {
  sections: Section[];
  currentPositionSec: number;    // cursor position in seconds
  className?: string;
}
```

### Styling

- Container: `flex items-center gap-2 h-6`
- Current section label: color-coded badge (same as SectionRow label badges)
- Progress bar: `h-1 rounded-full` with section-colored fill on `bg-gray-800` track
- Next section label: `text-[10px] text-gray-500`

---

## Compound States

### P8 + P9: No waveform AND no sections

The waveform area shows "No waveform data -- re-analyze with waveform enabled."
The section list shows "No sections detected."
The metadata panel still renders normally (it depends only on `TrackAnalysis` root fields).
The page is functional but minimal — user needs to re-analyze the track with richer options.

### P7 + partial sections (some low confidence)

All sections render. Low-confidence sections (< 0.3) have dashed borders and faint overlays
on the waveform. The SectionList shows them with red confidence values. No sections are
hidden by default — the user can filter them out via the filter bar if desired.

### Track switch during loading (P5 -> P5)

User selects track A (P5: loading). Before it loads, user selects track B.
TanStack Query cancels the track A fetch automatically (queryKey change from
`["track-analysis", fingerprintA]` to `["track-analysis", fingerprintB]`).
The skeleton loading state continues seamlessly — no flash of track A data.

### Track switch from loaded to new track (P7 -> P5)

User is viewing track A (P7: full data). Selects track B.
Analysis content area transitions to P5 (loading skeleton). Previous track's
waveform/sections/metadata are unmounted and replaced by skeleton immediately.
No cross-fade or stale-data display — clean cut to loading state.

`[DECISION OPPORTUNITY]` An alternative is to keep the previous track visible with a
loading overlay until the new track loads (reduces perceived latency). Recommendation:
clean cut is simpler to implement and avoids confusion about which track's data is displayed.
The analysis fetch is fast (local JSON read) so the loading state is brief.

---

## Transition Narrative: Typical User Flow

1. User navigates to `/analysis`. Page renders with TrackPicker (P1 -> P4).
2. Track list loads. User sees sortable mini table with all analyzed tracks.
3. User types in search to filter. Table filters in real time.
4. User clicks a track row. Row highlights. Content area transitions to P5 (loading).
5. Analysis loads (~100ms for local JSON). Content area transitions to P7 (full data).
6. User sees waveform with section overlays and energy curve. Section list populates.
7. User hovers over a section in the list -> corresponding section brightens on waveform.
8. User clicks a section row -> waveform zooms/scrolls to show that section at ~80% width.
9. User hovers over a section on the waveform -> corresponding row highlights in the list.
10. User clicks a section on the waveform -> section row scrolls into view, gets selected.
11. User uses mousewheel to zoom in/out. Click-drags to pan.
12. User double-clicks waveform to reset to full track view.
13. User clicks a different track in TrackPicker -> cycle repeats from step 4.

---

## Follow-Up Items (Out of Scope)

1. **SectionIndicator in Analysis Viewer:** Could be added below the waveform as a compact
   "current section" readout when a section is selected. Low priority — SectionList already
   provides this information. Revisit if user feedback requests it.

2. **Keyboard navigation:** Arrow keys to move between sections, Enter to select, Escape
   to deselect. Not in v1 scope but would improve power-user workflow.

3. **Waveform minimap:** A tiny full-track waveform below the main canvas showing the
   current viewport as a highlighted region. Useful when zoomed in deeply. Defer to v2
   if zoom/scroll interaction proves disorienting.
