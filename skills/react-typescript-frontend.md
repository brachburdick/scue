# Skill: React / TypeScript / Frontend

> **When to use:** Any task involving the frontend (components, stores, types, styling, API client).

---

## Stack & Environment

- React 19 with TypeScript (strict mode)
- Vite for build/dev server
- Tailwind CSS v3 for styling
- Zustand for state management
- TanStack Query for server data fetching
- TanStack Table for data display
- WebSocket for real-time updates from backend

## Project Structure

```
frontend/
├── src/
│   ├── App.tsx              # Root component
│   ├── main.tsx             # Entry point
│   ├── types/               # FE/BE boundary types (shared contract)
│   │   ├── index.ts
│   │   ├── ws.ts            # WebSocket message types
│   │   ├── track.ts         # Track models
│   │   ├── bridge.ts        # Bridge status models
│   │   └── analyze.ts       # Analysis job models
│   ├── stores/              # Zustand state management
│   │   ├── bridgeStore.ts
│   │   ├── analyzeStore.ts
│   │   ├── waveformPresetStore.ts
│   │   └── uiStore.ts
│   ├── components/          # UI components
│   │   ├── bridge/          # Bridge status & config
│   │   ├── tracks/          # Track table & analysis
│   │   └── layout/          # Shell, sidebar, console
│   ├── api/                 # API client functions
│   └── utils/               # Formatters, helpers
```

## Common Patterns

### State Management
- Zustand stores are **independent** — no store imports another store
- WebSocket data flows through stores, not direct component updates
- Server data fetched via TanStack Query, local UI state via Zustand

### Types
- All FE/BE boundary types defined in `frontend/src/types/`
- These must match the Python backend's API response shapes
- TypeScript strict mode is enabled — no `any` types

### Commands
- `cd frontend && npm run dev` — dev server
- `cd frontend && npm run build` — production build
- `cd frontend && npm run typecheck` — TypeScript validation

## Canvas Component API Reference

When editing `WaveformCanvas`, `AnnotationTimeline`, or `DeckWaveform`, load `skills/component-api-reference.md` first. It has props tables, draw pipeline order, and interaction modes — saves re-reading the source files.

## Known Gotchas

- **"Not yet loaded" sentinel values:** Never use `0` as initial state for numeric ranges (e.g., `viewEnd`, `duration`). `0` is indistinguishable from "no data." Use `null` and gate rendering on `value !== null`. This caused a waveform rendering bug where `viewEnd: 0` was treated as a valid zero-duration range.
- **Waveform rendering:** Always use the shared `WaveformCanvas` component for waveform display. Do NOT create new canvas rendering logic — ADR-018 documents a stacked-layer anti-pattern that was independently re-introduced in `EventTimeline.tsx` after being fixed in `WaveformCanvas.tsx`. If `WaveformCanvas` doesn't support your use case, extend it rather than building a parallel implementation.
- **WebSocket reconnect backoff:** The `ws.ts` client accumulates backoff across browser sleep cycles without resetting on `visibilitychange`. Be aware of this when debugging connection issues after laptop sleep.

## waveformPresetStore Pattern

`waveformPresetStore` manages waveform rendering presets (ADR-019). Key concepts:

- **`activePreset`** — The app-wide active preset. Fetched on app startup via `fetchPresets()` in `App.tsx`. All waveform components (AnalysisViewer, DeckWaveform) read `activePreset.params` and pass as `renderParams` to `WaveformCanvas`.
- **`draftParams`** — Tuning page only. Holds unsaved edits that override `activePreset` locally. Other pages never see draft changes.
- **`isDirty`** — True when `draftParams` differs from the loaded preset.
- **`getRenderParams()`** — Returns `draftParams ?? activePreset?.params ?? DEFAULT_RENDER_PARAMS`. Used by the tuning page.

Preset lifecycle: load → edit (draftParams) → save (PUT API) → activate (POST API) → store refetch.

The store is independent (no imports from other stores). Backend sync uses `apiFetch` directly, not TanStack Query — the store owns its own data. TanStack Query hooks in `api/waveformPresets.ts` are used by the tuning page for mutations with cache invalidation.

## Anti-Patterns

- Importing one Zustand store from another
- Using `any` type — strict mode is enabled
- Putting FE/BE boundary types outside of `frontend/src/types/`
- Inline styles instead of Tailwind classes
- Using `0` as initial value for numeric state that represents "not loaded"
- Creating new waveform canvas rendering instead of extending `WaveformCanvas`
