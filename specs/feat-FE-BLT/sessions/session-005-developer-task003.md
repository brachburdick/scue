# Session Summary: TASK-003

## Role
Developer

## Objective
When the bridge reconnects (status transitions to "running" from any non-running state), TanStack route/interface queries must auto-invalidate so stale warnings clear. On WS reconnect, the console mapper's diff-detection state must reset so console entries correctly reflect the new session.

## Status
COMPLETE

## Work Performed
- Ran baseline `npm run typecheck` — passed (0 errors)
- Created `frontend/src/api/queryClient.ts` — extracted `QueryClient` instantiation from `main.tsx` into a shared module so non-React code (`ws.ts`) can import it
- Updated `frontend/src/main.tsx` — imports `queryClient` from the shared module instead of creating it inline
- Added module-level `prevBridgeStatus` variable in `ws.ts` for tracking bridge status transitions
- Added query invalidation logic in `ws.ts` `dispatch()`: when `bridge_status.status` transitions to `"running"` from any non-running state (including `null` initial), invalidates `["network", "route"]` and `["network", "interfaces"]` queries
- Added `resetMapperState()` call in `ws.ts` `onOpen()` before the "Connected to backend" console entry, plus reset of `prevBridgeStatus` to `null`
- Updated bug entry in `docs/bugs/frontend.md`: changed "[OPEN] Route mismatch warning does not auto-clear on reconnect" to [FIXED] with root cause and fix details
- Ran final `npm run typecheck` — passed (0 errors)

## Files Changed
- `frontend/src/api/queryClient.ts` — NEW: shared QueryClient instance extracted from main.tsx
- `frontend/src/main.tsx` — imports QueryClient from shared module instead of creating inline
- `frontend/src/api/ws.ts` — added BridgeStatus type import, resetMapperState import, queryClient import, module-level prevBridgeStatus tracking, query invalidation on "running" transition in dispatch(), and resetMapperState()+prevBridgeStatus reset in onOpen()
- `docs/bugs/frontend.md` — updated route mismatch bug entry from [OPEN] to [FIXED]

## Interfaces Added or Modified
None. No new public interfaces, types, or API endpoints were added. The `queryClient` export from `api/queryClient.ts` is an internal frontend module — not a FE/BE boundary type.

## Decisions Made
- **Extract QueryClient to `api/queryClient.ts` rather than exporting from `main.tsx`**: Placing it in the `api/` directory groups it with other API-related modules (`ws.ts`, `network.ts`, `client.ts`). Exporting from `main.tsx` would work but `main.tsx` is the React render entry point and shouldn't be imported by non-React modules. Alternative: create at `utils/queryClient.ts` — rejected because it's API infrastructure, not a utility.
- **Reset `prevBridgeStatus` to `null` in `onOpen()`**: This ensures that after a WS reconnect, the first `bridge_status` message with `status === "running"` triggers query invalidation (since `null !== "running"`). Without this reset, a reconnect where the bridge was already running would not re-invalidate. Alternative: leave `prevBridgeStatus` unchanged across reconnects — rejected because it would miss the reconnect-to-running transition.
- **Update `prevBridgeStatus` before `setBridgeState()` call**: The status tracking update and query invalidation happen before the store update. This is safe because `invalidateQueries` is async and doesn't block — the store update follows immediately. Alternative: update after store — equivalent behavior, chose before for clarity of the "detect then act then update store" sequence.

## Scope Violations
None

## Remaining Work
None — all acceptance criteria met.

## Blocked On
None

## Missteps
None — baseline typecheck passed, all edits applied cleanly, final typecheck passed.

## Learnings
None — the implementation followed the established patterns (module-level state tracking as in consoleMapper.ts, query invalidation as in network.ts mutation hooks). No surprises encountered.
