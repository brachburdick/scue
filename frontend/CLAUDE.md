# SCUE Frontend

React 18 + TypeScript (strict) + Vite + Tailwind CSS

## Key libraries
- Zustand for state management (independent stores per concern)
- TanStack Query for REST data fetching
- TanStack Table for track table (sortable, filterable, virtualized)
- React Router for page routing

## Architecture rules
- All FE/BE boundary types defined in src/types/. These mirror Python dataclasses from docs/CONTRACTS.md.
- Stores are independent silos. No store imports another store.
- Pages are thin (<100 lines). Compose feature components + connect to stores/hooks.
- Shared components (Modal, StatusBadge, etc.) are purely presentational — props in, callbacks out.
- WebSocket managed in api/ws.ts, dispatches to Zustand stores. Components never touch WS directly.
- No localStorage or sessionStorage. All state is in-memory via Zustand or fetched from backend.

## Commands
- `npm run dev` — dev server with HMR
- `npm run build` — production build
- `npm run typecheck` — tsc --noEmit
- `npm test` — run tests

## Communication with backend
- REST API: src/api/client.ts (base URL config), per-resource files in src/api/
- WebSocket: src/api/ws.ts → dispatches typed WSMessage to stores
- Types: src/types/ws.ts defines the WSMessage union type

## FE/BE contract
All types in src/types/ must match the Python dataclasses documented in docs/CONTRACTS.md.
If the backend changes a shape, update the corresponding TS type and fix all TypeScript errors.

## Startup gating pattern
The bridge WebSocket takes a moment to connect and the backend may still be initialising.
API calls fired before the backend is ready return HTTP 500.

**Pattern:** Gate TanStack Query hooks with `enabled: !isStartingUp`.

```typescript
const isStartingUp = useBridgeStore((s) => s.isStartingUp);
const { data } = useInterfaces({ enabled: !isStartingUp });
```

`isStartingUp` is a derived boolean in `bridgeStore`:
- `true`  while the WebSocket is not yet open, OR while `status === "starting"`
- `false` once the WS is open AND the bridge has reached a stable status

Show a placeholder/skeleton UI while `isStartingUp === true`. Never render error states
until startup is complete.

## bridgeStore patterns
`src/stores/bridgeStore.ts` is the source of truth for all bridge/network state.

Key state:
| Field | Type | Notes |
|---|---|---|
| `status` | `BridgeStatus` | Updated from `bridge_status` WS messages |
| `wsConnected` | `boolean` | `true` once WS `onOpen` fires |
| `isStartingUp` | `boolean` | Derived: `!wsConnected \|\| status === "starting"` |
| `isReceiving` | `boolean` | Updated from `pioneer_status` WS messages |
| `lastMessageAgeMs` | `number \| null` | ms since last Pioneer packet |
| `routeCorrect` | `boolean \| null` | From `bridge_status` WS message |
| `devices` | `Record<string, DeviceInfo>` | Discovered Pioneer devices |
| `players` | `Record<string, PlayerInfo>` | Per-player playback state |

`dotStatus` is a derived value (`"connected" | "degraded" | "disconnected"`) computed
from `status` only — not from `isReceiving`. The dot reflects bridge status, not traffic:
- `"connected"` — `status === "running"`
- `"degraded"` — `status === "fallback"`
- `"disconnected"` — all other statuses

`setWsConnected(bool)` updates both `wsConnected` and recomputes `isStartingUp`. It is
called from `api/ws.ts` `onOpen`/`onClose` handlers.

## Network query hooks
`src/api/network.ts` exports three query hooks, all accepting `{ enabled?: boolean }`:

```typescript
useInterfaces({ enabled })      // GET /api/network/interfaces
useRouteStatus({ enabled })     // GET /api/network/route
useRouteSetupStatus({ enabled }) // GET /api/network/route/setup-status
```

Always pass `enabled: !isStartingUp` from any component that uses these hooks.

`useRestartBridge` invalidates `["network", "route"]` on success so RouteStatusBanner
picks up the updated route state after a bridge restart.

## Auto-fix useEffect pattern
`RouteStatusBanner` auto-fixes a route mismatch once on startup if sudoers is installed.
Guard pattern using `useRef` to prevent repeated triggers:

```typescript
const hasAutoFixed = useRef(false);
useEffect(() => {
  if (!isStartingUp && route && !route.correct && canFix && !hasAutoFixed.current) {
    hasAutoFixed.current = true;
    fixMutation.mutateAsync(route.expected_interface!).then(() => refetchRoute());
  }
}, [isStartingUp, route, canFix]);
```

## TopBar components
`src/components/layout/TopBar.tsx` contains three status indicators:

- **StatusDot** — reflects `bridgeStore.dotStatus` (green/yellow/red). Driven by bridge
  status only, not Pioneer traffic — avoids false cycling when no hardware is connected.
- **TrafficDot** — cyan dot with `animate-ping` ripple when `isReceiving === true`.
  Only shown when `dotStatus !== "disconnected"`. Tooltip shows last message age.
- **StartupIndicator** — spinning pill shown while `isStartingUp === true`.
  Label: "Connecting…" (WS not open) or "Bridge starting…" (WS open, status=starting).
  Disappears once startup completes.

## Bridge page (src/pages/BridgePage.tsx)
Route: `/data/bridge` — sidebar label "Bridge".

Layout: two-column grid (lg breakpoint).
- Left: `BridgeStatusPanel` — StatusBanner, TrafficIndicator, DeviceList, PlayerList
- Right: `HardwareSelectionPanel` — RouteStatusBanner, ActionBar, InterfaceSelector

RouteStatusBanner and ActionBar are placed **above** InterfaceSelector so route fix
controls are immediately visible without scrolling.

## Detector Tuning Page (src/pages/DetectorTuningPage.tsx)
Route: `/dev/detectors` — sidebar label "Detectors" under "Dev" section header.

Dev-facing page for testing and tuning M7 event detection algorithms. Not user-facing.

Components:
- `TrackPicker` — reuses track table for selection (no fingerprint text input)
- `EventTimeline` — canvas with waveform + event marker overlay. Waveform uses Pioneer-correct
  single blended bar rendering (ADR-018). DrumPatterns are expanded client-side into MusicalEvents.
- `EventControls` — per-event-type color-coded toggles + confidence threshold slider
- `EventStats` — per-type counts, events/bar density, average confidence

Types: `src/types/events.ts` — `MusicalEvent`, `DrumPattern`, `TrackEventsResponse`, `EVENT_COLORS`

API: `GET /api/tracks/{fingerprint}/events` returns events + drum_patterns for a track.

## Bug tracking
When fixing any frontend bug, append an entry to `docs/bugs/frontend.md` with: symptom,
root cause, fix, and affected file(s). No fix is too small to record.
