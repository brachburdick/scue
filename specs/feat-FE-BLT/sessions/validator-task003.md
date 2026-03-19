# Validator Verdict: TASK-003

## Verdict: PASS

## Verification Scope: STATIC

## Pre-Check: Session Summary
- Session summary exists: YES
- All required fields present: YES

## Tests
- Pre-existing tests pass: YES — Developer reports `npm run typecheck` passed at baseline and final. No pre-existing unit tests for `ws.ts` or `main.tsx` to regress.
- New tests added: NO — handoff packet did not require new tests. The task is WS dispatch wiring (untestable without integration harness) and query invalidation (TanStack internal). No new public functions were introduced.
- New tests pass: N/A

## Acceptance Criteria Check
- [x] `ws.ts` tracks the previous bridge status in a module-level variable — **MET**. `ws.ts` line 22: `let prevBridgeStatus: BridgeStatus | null = null;`. Typed as `BridgeStatus | null`, initialized to `null`.
- [x] When `bridge_status.status` transitions to `"running"` from any non-running state (including `null` initial → `"running"`), both network queries are invalidated — **MET**. `ws.ts` lines 39-42: `if (newStatus === "running" && prevBridgeStatus !== "running")` gates the two `queryClient.invalidateQueries()` calls. `null !== "running"` is true, so initial state triggers correctly. `prevBridgeStatus` is updated on line 43, after the invalidation check.
- [x] `QueryClient` is importable from a shared module (not created inline in `ws.ts`) — **MET**. `frontend/src/api/queryClient.ts` exports `queryClient`. `ws.ts` line 12 imports it: `import { queryClient } from "./queryClient";`. `main.tsx` line 5 imports the same instance.
- [x] `onOpen()` calls `resetMapperState()` before the "Connected to backend" entry — **MET**. `ws.ts` lines 65-66: `resetMapperState()` and `prevBridgeStatus = null` are called before the `addEntry` call on line 68.
- [x] After bridge auto-reconnect, network queries refetch and route mismatch warning clears — **MET** (by design). The `invalidateQueries` calls trigger TanStack refetch. When the refetched route data shows correct state, `RouteStatusBanner` re-renders without the warning. This is a behavioral criterion; the code path is verified statically.
- [x] Console entries from before disconnect are preserved in the store (ring buffer not flushed) — **MET**. `onOpen()` calls `resetMapperState()` (which resets the mapper's diff-detection variables in `consoleMapper.ts`) but does NOT call `useConsoleStore.getState().clearEntries()`. The console store's `entries` array is untouched on reconnect.
- [x] After WS reconnect, the first `bridge_status` generates appropriate console entries — **MET**. `resetMapperState()` sets `prevBridgeStatus = null` inside the mapper module. The mapper's `mapBridgeStatus` function (line 85-87) handles `prevBridgeStatus === null` with a non-default status by emitting a "Bridge status: {status}" entry. Additionally, `prevBridgeStatus = null` in `ws.ts` ensures the query invalidation also fires on the first "running" message.
- [x] `npm run typecheck` passes — **MET**. Session summary reports typecheck passed at both baseline and final run.
- [x] Bug entry updated in `docs/bugs/frontend.md` — **MET**. The "[OPEN] Route mismatch warning does not auto-clear on reconnect" entry is now "[FIXED]" with date, root cause, and fix description (lines 63-70).
- [x] If interfaces added/modified, update `docs/CONTRACTS.md` or flag `[INTERFACE IMPACT]` — **MET**. Session summary correctly states "None" — the `queryClient` export is internal frontend infrastructure, not a FE/BE boundary type.

## Scope Check
- Files modified:
  - `frontend/src/api/queryClient.ts` (NEW) — within scope (handoff explicitly allows creating this)
  - `frontend/src/main.tsx` — within scope
  - `frontend/src/api/ws.ts` — within scope
  - `docs/bugs/frontend.md` — within scope
- Out-of-scope modifications: none
- Files that must NOT be touched (verified untouched):
  - `frontend/src/stores/bridgeStore.ts` — not modified
  - `frontend/src/stores/consoleStore.ts` — not modified
  - `scue/` — not modified
  - `docs/CONTRACTS.md` — not modified

## What Went Well
- **Clean separation of concerns.** The `QueryClient` extraction into `api/queryClient.ts` with a clear docblock (lines 1-6) follows the project's existing pattern of per-concern modules in `api/`. The Developer correctly rejected placing it in `main.tsx` or `utils/` with documented rationale.
- **Correct ordering in `onOpen()`.** `resetMapperState()` is called before the "Connected to backend" entry and before any bridge status messages can arrive, exactly as the handoff specified. The `prevBridgeStatus = null` reset in `ws.ts` is placed alongside it, ensuring both the mapper and the query-invalidation tracker start fresh.
- **Dual `prevBridgeStatus` variables are intentional and correct.** The mapper in `consoleMapper.ts` has its own `prevBridgeStatus` for diff-based console entry generation, while `ws.ts` has a separate one for query invalidation triggers. These serve different purposes and are reset independently through their respective mechanisms (`resetMapperState()` vs. direct assignment in `onOpen()`). No confusion between them.
- **`staleTime: 30_000` preserved.** The `QueryClient` extraction maintained the existing default options, ensuring no behavioral change to other queries in the application.

## Issues Found
No issues found.

## Recommendation
Proceed to next task.
