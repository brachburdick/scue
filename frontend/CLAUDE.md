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

## Bug tracking
When fixing any frontend bug, append an entry to `docs/bugs/frontend.md` with: symptom, root cause, fix, and affected file(s). No fix is too small to record.
