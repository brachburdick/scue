# Section: frontend-viz

## Purpose
Visualization-heavy, real-time, canvas-oriented components: waveform rendering, analysis viewers, live deck monitoring, strata arrangement maps, detector event timelines, annotation overlays, and waveform tuning. The "display" half of the frontend.

## Owned Paths
```
frontend/src/components/analysis/       — AnalysisViewer, TrackPicker, SectionList, TrackMetadataPanel
frontend/src/components/annotations/    — AnnotationTimeline, AnnotationList, AnnotationToolbar, ScorePanel
frontend/src/components/detectors/      — EventTimeline, EventControls, EventStats
frontend/src/components/live/           — DeckPanel, DeckWaveform, DeckMetadata, DeckEmptyState
frontend/src/components/strata/         — ArrangementMap, ComparisonView, DiffSummary,
                                          PatternDetailPanel, TierAnalysisStatus
frontend/src/components/waveformTuning/ — ParameterControls, PresetBar, PioneerReferenceWaveform
frontend/src/components/shared/WaveformCanvas.tsx
frontend/src/components/shared/drawBeatgridLines.ts
frontend/src/components/shared/SectionIndicator.tsx
frontend/src/components/shared/LiveEventDisplay.tsx
frontend/src/components/shared/EventTypeToggles.tsx
frontend/src/hooks/useWaveformView.ts
frontend/src/hooks/useActiveEvents.ts
frontend/src/pages/AnalysisViewerPage.tsx
frontend/src/pages/LiveDeckMonitorPage.tsx
frontend/src/pages/StrataPage.tsx
frontend/src/pages/DetectorTuningPage.tsx
frontend/src/pages/WaveformTuningPage.tsx
frontend/src/pages/AnnotationPage.tsx
```

## Incoming Inputs
- **From frontend-core:** Stores (bridgeStore, analyzeStore, strataLiveStore, waveformPresetStore), API clients, types, utils
- **REST API:** Track analysis data, strata formulas, waveform preset configs
- **WebSocket:** `playback_position`, `strata_live`, `active_events` real-time messages
- **User:** Canvas interactions (zoom, pan, scrub, hover)

## Outgoing Outputs
- **Rendered UI:** Canvas-drawn waveforms, SVG timelines, arrangement maps
- **User interactions:** Zoom/pan state, annotation edits, preset selections

## Invariants
- Shared `WaveformCanvas` component used for ALL waveform rendering. No parallel canvas implementations.
- Canvas components must handle `devicePixelRatio` for retina displays.
- All time-domain rendering uses seconds (not samples or beats) as the x-axis unit.
- Waveform draw pipeline: clear → background → waveform bars → beatgrid → sections → cursor → overlays.
- `useWaveformView` hook is the single source of truth for zoom/pan state across all waveform views.
- Live deck components must handle missing/stale data gracefully (empty state, not crashes).

## Relationship to frontend-core
Frontend-viz consumes stores, API clients, and types owned by frontend-core. It does not define new stores or API clients — those belong in frontend-core. If a viz component needs new server data, the API client and type go in frontend-core; the component that uses them goes here.

## Allowed Dependencies
- React 19, TypeScript (strict), Tailwind 3
- Canvas 2D API (no WebGL currently)
- All frontend-core shared infrastructure (stores, api, types, utils)
- No direct imports of Python code or backend modules

## How to Verify
```bash
cd frontend && npm run typecheck   # TypeScript validation
cd frontend && npm run build       # Production build
cd frontend && npm run dev         # Dev server for visual verification
```

## Canvas Component Reference
When editing `WaveformCanvas`, `AnnotationTimeline`, or `DeckWaveform`, load `skills/component-api-reference.md` first. These components have complex draw pipelines and interaction handlers.

## Key Skill
Load `skills/waveform-rendering.md` for psychoacoustic color mapping, Pioneer parity rules, and the preset system.
