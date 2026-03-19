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

## Known Gotchas

- [TODO: Fill from project experience]

## Anti-Patterns

- Importing one Zustand store from another
- Using `any` type — strict mode is enabled
- Putting FE/BE boundary types outside of `frontend/src/types/`
- Inline styles instead of Tailwind classes
- [TODO: Fill from project experience]
