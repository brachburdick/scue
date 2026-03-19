# Session: FE-State — TypeScript Type Updates
**Date:** 2026-03-17
**Task Reference:** Handoff from Bridge L0 restart-logic session

## What Changed
| File | Change Type | Description |
|---|---|---|
| frontend/src/types/bridge.ts | Modified | Added `restart_attempt: number` and `next_retry_in_s: number \| null` to `BridgeState` |
| frontend/src/types/ws.ts | Modified | Added `bridge_connected: boolean` to `WSPioneerStatus` payload |
| frontend/src/stores/bridgeStore.ts | Modified | Added `restartAttempt`, `nextRetryInS`, `bridgeConnected` state fields with defaults; updated `setBridgeState` to map new fields; updated `setPioneerStatus` signature to accept and store `bridgeConnected` |
| frontend/src/api/ws.ts | Modified | Updated `pioneer_status` dispatch to pass `msg.payload.bridge_connected` to store setter |

## Interface Impact
- `BridgeState` type expanded with two new fields (additive, backward-compatible — `restart_count` preserved)
- `WSPioneerStatus` payload expanded with `bridge_connected` (additive)
- `setPioneerStatus` store action signature changed from `(boolean, number)` to `(boolean, number, boolean)` — internal to frontend, no cross-boundary impact

**[INTERFACE IMPACT]**: `BridgeState` and `WSPioneerStatus` types in `docs/CONTRACTS.md` should be updated to reflect the new fields (`restart_attempt`, `next_retry_in_s`, `bridge_connected`). These fields already exist in the Python backend payloads.

## Tests
| Test | Status |
|---|---|
| npm run typecheck | ✅ Pass |

## Decisions Made During Implementation
No judgment calls needed — the handoff spec was fully prescriptive.

## Questions for Brach
None.

## Remaining Work
- Components (BridgePage, TopBar) may want to use `bridgeConnected`, `restartAttempt`, and `nextRetryInS` for richer status display. This is FE-UI agent scope.
- `docs/CONTRACTS.md` needs updating to reflect the three new fields in the WebSocket message schemas (Architect scope).

## LEARNINGS.md Candidates
None — straightforward additive type sync with no surprises.
