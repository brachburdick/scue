# Handoff Packet: TASK-003 — Frontend reconnect-aware query invalidation and console mapper reset

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
When the bridge reconnects (status transitions to "running" from any non-running state), TanStack route/interface queries must auto-invalidate so stale warnings clear. On WS reconnect, the console mapper's diff-detection state must reset so console entries correctly reflect the new session.

## Role
Developer

## Scope Boundary
- Files this agent MAY read/modify:
  - `frontend/src/api/ws.ts` — add query invalidation logic in dispatch; call `resetMapperState()` in `onOpen()`
  - `frontend/src/utils/consoleMapper.ts` — read-only (function already exists at line 23, just needs to be called)
  - `frontend/src/api/network.ts` — read-only context (query keys)
  - `frontend/src/main.tsx` or wherever `QueryClient` is instantiated — may need to export it for use in `ws.ts`
  - `docs/bugs/frontend.md` — update route mismatch bug entry
- Files this agent must NOT touch:
  - `frontend/src/stores/bridgeStore.ts` — store must stay pure (no TanStack imports)
  - `frontend/src/stores/consoleStore.ts` — no changes needed
  - `scue/` — all backend files
  - `docs/CONTRACTS.md`

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `frontend/src/api/ws.ts` — full file. Key: `dispatch()` (line 27), `onOpen()` (line 45), `onClose()` (line 65). Understand the message flow.
- `frontend/src/utils/consoleMapper.ts` — full file. Key: `resetMapperState()` (line 23), module-level `prev*` variables (lines 13-19). These persist across WS reconnects.
- `frontend/src/api/network.ts` — query keys: `["network", "route"]` (line 27), `["network", "interfaces"]` (line 17)
- `frontend/src/stores/bridgeStore.ts` — read-only context. The `BridgeStatus` type and store shape. Note: stores are independent silos — do NOT import TanStack into stores.
- `frontend/CLAUDE.md` — architecture rules, especially "Stores are independent silos. No store imports another store."
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-4 and TR-6 (full requirements)
- `docs/bugs/frontend.md` — "[OPEN] Route mismatch warning does not auto-clear on reconnect" entry

## State Behavior
`[INLINE — simple]` — query invalidation is invisible to the user (queries refetch silently, UI updates from fresh data). Console mapper reset produces correct entries — no new visual states.

## Constraints
- Do NOT import TanStack `queryClient` into any Zustand store. The invalidation logic belongs in `ws.ts` (the WS dispatch layer), not in stores.
- To track status transitions in `dispatch()`, use a module-level variable (e.g., `let prevBridgeStatus: string | null = null`) similar to how `consoleMapper.ts` tracks prev state. Update it after each `bridge_status` dispatch.
- The `QueryClient` instance must be accessible from `ws.ts`. Check where it's currently instantiated (likely `frontend/src/main.tsx` or a dedicated module). If it's not exported, create a shared export (e.g., `frontend/src/api/queryClient.ts`).
- Call `resetMapperState()` in `onOpen()` BEFORE the "Connected to backend" console entry is added — this ensures the mapper is fresh for the first messages of the new session.
- All pre-existing tests and typecheck must continue to pass.

## Acceptance Criteria
- [ ] `ws.ts` tracks the previous bridge status in a module-level variable
- [ ] When `bridge_status.status` transitions to `"running"` from any non-running state (including `null` initial state → `"running"`), `queryClient.invalidateQueries({ queryKey: ["network", "route"] })` and `queryClient.invalidateQueries({ queryKey: ["network", "interfaces"] })` are called
- [ ] `QueryClient` is importable from a shared module (not created inline in `ws.ts`)
- [ ] `onOpen()` calls `resetMapperState()` from `consoleMapper.ts` before the "Connected to backend" entry
- [ ] After bridge auto-reconnect, `["network", "route"]` and `["network", "interfaces"]` queries refetch — route mismatch warning clears if route is now correct
- [ ] Console entries from before disconnect are preserved in the store (ring buffer not flushed)
- [ ] After WS reconnect, the first `bridge_status` generates appropriate console entries (e.g., "Bridge status: running")
- [ ] `npm run typecheck` passes
- [ ] Bug entry "[OPEN] Route mismatch warning does not auto-clear on reconnect" updated in `docs/bugs/frontend.md`
- [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.

## Dependencies
- Requires completion of: none (can run in parallel with TASK-001)
- Blocks: TASK-005 (console mapper reset may partially fix console log disappearance)

## Open Questions
None — all decisions resolved by operator in Architect session.
