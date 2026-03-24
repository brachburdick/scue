# Section: frontend

## Purpose
React/TypeScript single-page app for track management, analysis visualization, live deck monitoring, and bridge/network configuration.

## Owned Paths
```
frontend/src/components/  — UI components (bridge, tracks, layout, shared, live, annotations)
frontend/src/stores/      — Zustand state stores (bridge, analyze, folder, console, waveformPreset, ui)
frontend/src/api/         — API client, TanStack Query hooks, WebSocket client
frontend/src/types/       — FE/BE boundary type definitions
frontend/src/utils/       — formatters, helpers
frontend/src/App.tsx      — root component
frontend/src/main.tsx     — entry point
frontend/               — package.json, tsconfig.json, vite.config.ts, tailwind.config.js
```

## Incoming Inputs
- **REST API:** JSON responses from server section endpoints (`/api/tracks`, `/api/bridge`, etc.)
- **WebSocket:** `bridge_status`, `pioneer_status`, `playback_position` messages from server
- **User:** Mouse/keyboard interaction

## Outgoing Outputs
- **REST requests:** `POST /api/tracks/analyze`, `POST /api/network/route/fix`, etc.
- **Rendered UI:** Browser DOM

## Invariants
- No store imports another store. Each Zustand store is an independent state machine.
- All FE/BE boundary types are defined in `frontend/src/types/`. No inline type definitions for API data.
- TypeScript strict mode — no `any` types.
- WebSocket client handles reconnect with backoff. `resetMapperState()` called on WS reopen.
- Shared `WaveformCanvas` component used for ALL waveform rendering. No parallel canvas implementations.
- `0` is never used as initial state for numeric ranges — use `null` and gate on `!== null`.

## Allowed Dependencies
- React 19, TypeScript (strict), Vite 6, Tailwind 3
- Zustand for state, TanStack Query for server data, TanStack Table for data display
- `axios` for HTTP client
- No direct imports of Python code or backend modules

## How to Verify
```bash
cd frontend && npm run typecheck   # TypeScript validation
cd frontend && npm run build       # Production build (catches dead code, missing types)
cd frontend && npm run dev         # Dev server for manual verification
```

## Type Contract
Types in `frontend/src/types/` must match Python dataclasses documented in `docs/CONTRACTS.md`.
When a backend type changes, the corresponding frontend type must be updated in the same session.

Key type files and what they mirror:
- `bridge.ts` → `scue/bridge/adapter.py` (DeviceInfo, PlayerState)
- `track.ts` → `scue/layer1/models.py` (TrackAnalysis, Section, RGBWaveform)
- `ws.ts` → `scue/api/ws_manager.py` broadcast shapes
- `strata.ts` → `scue/layer1/strata/models.py` (StrataFormula)
- `events.ts` → `scue/layer1/models.py` (MusicalEvent, DrumPattern)

## Canvas Component Reference
When editing `WaveformCanvas`, `AnnotationTimeline`, or `DeckWaveform`, load `skills/component-api-reference.md` first.
