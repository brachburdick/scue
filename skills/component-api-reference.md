# SCUE Frontend Component API Reference

> Load this before editing any SCUE frontend canvas component.
> Saves ~1500 tokens per session by eliminating re-reads of source files.
> Source: review cycle 2026-03-24, Lens C finding #1 (6 sessions affected).

---

## WaveformCanvas

**Path:** `frontend/src/components/shared/WaveformCanvas.tsx`
**Role:** Core reusable waveform renderer. Full interaction (pan, zoom, click, section hover).

### Props

| Prop | Type | Required | Notes |
|------|------|----------|-------|
| waveform | RGBWaveform | yes | `low[]`, `mid[]`, `high[]`, `sample_rate` |
| duration | number | yes | Track duration in seconds |
| viewStart / viewEnd | number | yes | Viewport bounds (seconds) |
| onViewChange | (start, end) => void | no | Callback when viewport changes |
| sections | Section[] | no | Background section bands |
| highlightedSection / selectedSection | number \| null | no | Section highlight state |
| onSectionHover / onSectionClick | callbacks | no | Section interaction |
| energyCurve | number[] | no | White overlay curve (0-1 normalized) |
| beats / downbeats | number[] | no | Beatgrid overlay lines |
| cursorPosition | number \| null | no | Playback cursor (seconds) |
| onTimeClick | (seconds) => void | no | Seek callback |
| height | number | no | Default: 160 |
| renderParams | WaveformRenderParams | no | Gain, scaling, color mode |

### Draw Pipeline (back to front)

1. Clear canvas (`#0f172a`)
2. Section overlays (semi-transparent colored bands)
3. Waveform bars (RGB frequency-color blend, downsampled by zoom)
4. Beatgrid lines (gray/white at beat/downbeat timestamps)
5. Energy curve (white semi-transparent line graph)
6. Cursor line (glowing white vertical, outer glow + inner line)

### Mouse Interactions

- **Drag:** Pan timeline (3px threshold to distinguish from click)
- **Wheel:** Zoom anchored at cursor position
- **Click:** `onTimeClick` (seek) or `onSectionClick`
- **Double-click:** Reset to full duration
- **Hover over section:** `onSectionHover`

### Internal State (refs, not React state)

`canvasRef`, `containerRef`, `widthRef` (ResizeObserver), `rafRef` (requestAnimationFrame), `isDragging`, `dragStartX/ViewStart/ViewEnd`.

---

## AnnotationTimeline

**Path:** `frontend/src/components/annotations/AnnotationTimeline.tsx`
**Role:** Ground truth labeling editor. Place point/region events with snap-to-grid.

### Props

| Prop | Type | Required | Notes |
|------|------|----------|-------|
| sections | Section[] | yes | Background section bands |
| waveform | Waveform \| null | yes | RGB waveform for background |
| duration | number | yes | Track duration |
| annotations | GroundTruthEvent[] | yes | Events being edited |
| selectedIndex | number \| null | yes | Currently selected annotation |
| detectorEvents | MusicalEvent[] | no | Detector overlay (faded, alpha=0.25) |
| showDetectorOverlay | boolean | yes | Toggle detector display |
| cursorPosition | number \| null | yes | Playback position (seconds) |
| activeType | EventType | yes | Event type for placement |
| placementMode | PlacementMode | yes | "point" or "region" |
| snapResolution | SnapResolution | yes | "16th", "32nd", "64th", "off" |
| beats / downbeats | number[] | yes | For snap alignment |
| visibleTypes | Set\<EventType\> | yes | Filter which event types show |
| viewStart / viewEnd | number | yes | Viewport bounds |
| onViewChange | callback | yes | Viewport change |
| onPlaceEvent | (event) => void | yes | Create annotation |
| onSelectEvent | (index \| null) => void | yes | Select/deselect |
| onTimeClick | (seconds) => void | yes | Seek |

### Draw Pipeline (back to front)

1. Clear canvas (`#0f172a`)
2. Section bands (muted background)
3. Waveform bars (simplified RGB)
4. Beatgrid snap lines
5. Detector overlay (alpha=0.25): diagonal lines for risers/fallers, bars for stabs
6. Ground truth annotations (opaque): rectangles for regions, vertical lines for points
7. Cursor line

### Interaction Modes

- **Point mode:** Click places event at snapped time
- **Region mode:** Drag creates region; click deselects and seeks
- **Pan:** Middle-click or alt+left-click
- **Hit detection:** 6px tolerance for click-near-annotation

### Canvas height: 192px fixed.

---

## DeckWaveform

**Path:** `frontend/src/components/live/DeckWaveform.tsx`
**Role:** Read-only live playback view. Thin wrapper around WaveformCanvas.

### Props

| Prop | Type | Required | Notes |
|------|------|----------|-------|
| waveform | RGBWaveform | yes | RGB waveform data |
| sections | Section[] | yes | Section context |
| duration | number | yes | Track duration |
| positionMs | number \| null | yes | Playback position (milliseconds) |
| beats / downbeats | number[] | no | Beatgrid overlay |

### Viewport: Auto-managed

- **Window:** Fixed 12-second viewport (±6s around cursor)
- **When stopped:** Shows 0 to min(12, duration)
- **When playing:** Smooth scroll following playback, clamped to track boundaries

### State

- Converts `positionMs` → seconds internally
- Fetches render preset from `useWaveformPresetStore` (Zustand)
- Computes `currentSectionIndex` from cursor position
- **No interaction handlers** — display only

---

## Shared Types

```typescript
// RGBWaveform: { low: number[], mid: number[], high: number[], sample_rate: number }
// Section: { label: string, start: number, end: number, confidence?: number }
// GroundTruthEvent: { type: EventType, timestamp: number, duration?: number, source?: string }
// MusicalEvent: { type: EventType, timestamp: number, duration: number|null, intensity: number }
// WaveformRenderParams: { lowGain, midGain, highGain, normalization, amplitudeScale,
//   gamma, logStrength, noiseFloor, colorMode, saturation, brightness, ... }
// EventType: "kick" | "snare" | "hihat" | "clap" | "riser" | "faller" | "stab"
// PlacementMode: "point" | "region"
// SnapResolution: "16th" | "32nd" | "64th" | "off"
```

## Quick Summary

| Component | Interactive? | State Mgmt | Key Pattern |
|-----------|-------------|------------|-------------|
| WaveformCanvas | Full (pan/zoom/click) | Props + drag refs | ResizeObserver + RAF |
| AnnotationTimeline | Full (place/pan/snap) | Props + drag refs | Snap-to-grid + hit detect |
| DeckWaveform | None (read-only) | Props + Zustand store | 12s sliding window |
