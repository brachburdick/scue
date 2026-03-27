# Section: frontend-core

## Purpose
Application shell, navigation, data management UI, bridge/network configuration, and track ingestion interface. CRUD-oriented, form-heavy, table-heavy components. The "plumbing" half of the frontend.

## Owned Paths
```
frontend/src/components/layout/       — Shell, TopBar, Sidebar, Console, ConsolePanel, ConsoleHeader, LogEntry
frontend/src/components/bridge/       — BridgeStatusPanel, DeviceList, PlayerList, HardwareSelection,
                                        InterfaceSelector, RouteStatusBanner, StatusBanner, DeviceCard,
                                        PlayerCard, InterfaceRow, ActionBar
frontend/src/components/ingestion/    — AnalyzePanel, HardwareTab, LibraryTab, AudioTab,
                                        ScanProgressPanel, UsbBrowser, TrackLibraryTable
frontend/src/components/tracks/       — TrackTable, TrackToolbar
frontend/src/components/shared/Button.tsx
frontend/src/components/shared/FolderBrowser.tsx
frontend/src/components/shared/PlaceholderPanel.tsx
frontend/src/stores/                  — all Zustand stores
frontend/src/api/                     — all API clients and query hooks
frontend/src/types/                   — all FE/BE boundary type definitions
frontend/src/utils/                   — formatters, consoleMapper, consoleExport
frontend/src/pages/TracksPage.tsx
frontend/src/pages/BridgePage.tsx
frontend/src/pages/IngestionPage.tsx
frontend/src/pages/LogsPage.tsx
frontend/src/pages/NetworkPage.tsx
frontend/src/pages/EnrichmentPage.tsx
frontend/src/App.tsx
frontend/src/main.tsx
frontend/                             — package.json, tsconfig.json, vite.config.ts, tailwind.config.js
```

## Incoming Inputs
- **REST API:** JSON responses from server section endpoints
- **WebSocket:** `bridge_status`, `pioneer_status`, `scan_progress` messages
- **User:** Mouse/keyboard interaction

## Outgoing Outputs
- **REST requests:** CRUD operations, scan triggers, network commands
- **Rendered UI:** Browser DOM (shell, tables, forms, status panels)
- **Shared infrastructure:** Stores, API clients, types, and utils consumed by frontend-viz

## Invariants
- No store imports another store. Each Zustand store is an independent state machine.
- All FE/BE boundary types are defined in `frontend/src/types/`. No inline type definitions for API data.
- TypeScript strict mode — no `any` types.
- WebSocket client handles reconnect with backoff. `resetMapperState()` called on WS reopen.
- `0` is never used as initial state for numeric ranges — use `null` and gate on `!== null`.

## Relationship to frontend-viz
Frontend-core owns the shared infrastructure (stores, api clients, types, utils) that frontend-viz consumes. Changes to types or stores may affect both sections. When a type change crosses the boundary, coordinate with frontend-viz.

## Allowed Dependencies
- React 19, TypeScript (strict), Vite 6, Tailwind 3
- Zustand for state, TanStack Query for server data, TanStack Table for data display
- `axios` for HTTP client
- No direct imports of Python code or backend modules

## How to Verify
```bash
cd frontend && npm run typecheck   # TypeScript validation
cd frontend && npm run build       # Production build
```

## Type Contract
Types in `frontend/src/types/` must match Python dataclasses in the backend.
When a backend type changes, the corresponding frontend type must be updated in the same session.

Key type files and what they mirror:
- `bridge.ts` → `scue/bridge/adapter.py` (DeviceInfo, PlayerState)
- `track.ts` → `scue/layer1/models.py` (TrackAnalysis, Section, RGBWaveform)
- `ws.ts` → `scue/api/ws_manager.py` broadcast shapes
- `ingestion.ts` → `scue/api/scanner.py` scan result shapes
