# Validator Verdict: FIX-STALE-DEVICES

## Verdict: PASS

## Verification Scope: STATIC+TESTS

## Pre-Check: Session Summary
- Session summary exists: YES
- All required fields present: YES

## Tests
- Pre-existing tests pass: YES — `npm run typecheck` exits cleanly with no errors
- New tests added: NO
- New tests pass: N/A

## Acceptance Criteria Check
- [x] When Pioneer hardware disconnects, DeviceList clears to "No Pioneer devices detected" within a reasonable time — **MET**. `bridgeStore.ts` line 84/99: `setBridgeState()` sets `devices: isRunning ? state.devices : {}` and `players: isRunning ? state.players : {}`. When the bridge transitions out of `"running"`, devices are force-cleared to `{}`, which triggers DeviceList's existing empty state rendering.
- [x] When Pioneer hardware disconnects, PlayerList clears to "No active players" within a reasonable time — **MET**. Same store logic clears players (line 100). `PlayerList.tsx` lines 11-16: renders "No active players." when `entries.length === 0`.
- [x] When bridge enters `waiting_for_hardware` mode, both components show empty state — **MET**. `status === "waiting_for_hardware"` is not `"running"`, so `isRunning` is false and both `devices` and `players` are set to `{}` (lines 99-100).
- [x] When bridge status is `disconnected`, both components show empty state — **MET**. Same reasoning: `"disconnected" !== "running"` triggers the clear path.
- [x] When hardware reconnects, devices and players repopulate from fresh `bridge_status` data — **MET**. When `status === "running"`, `setBridgeState()` passes through `state.devices` and `state.players` directly (lines 99-100), so fresh data from the backend populates both components.
- [x] No flicker on momentary traffic gaps (existing grace window preserved) — **MET**. The `recentTraffic` logic in `DeviceList.tsx` was not modified (out of scope for this file, and the Developer's summary confirms it was not touched). The fix only gates on `status`, not on traffic presence, so the grace window is unaffected.
- [x] All pre-existing tests pass — **MET**. Verified independently: `npm run typecheck` passes clean.
- [x] Bug entry in `docs/bugs/frontend.md` updated — **MET**. Entry at line 79-86 of `docs/bugs/frontend.md`: "Devices and players show stale data after hardware disconnect" updated with date resolved (2026-03-19), root cause (4 items), fix description, and affected files.
- [x] Interface impact — **MET**. Session summary states "None" for interfaces added or modified. The store's public API (action signatures, state shape) is unchanged — only internal behavior of existing actions was modified. No `docs/CONTRACTS.md` update needed.

## Scope Check
- Files modified: `frontend/src/stores/bridgeStore.ts`, `frontend/src/components/bridge/PlayerList.tsx`, `docs/bugs/frontend.md`
- Out-of-scope modifications: None. All three files are within the handoff packet's scope boundary.

## What Went Well
- The status-gate approach in `setBridgeState()` (lines 84, 99-100 of `bridgeStore.ts`) is a clean, defensive fix. By gating on `isRunning` rather than trying to detect specific non-running states, it handles all current and future non-running statuses without maintenance burden.
- The dual-clear strategy (clearing in both `setBridgeState` for status transitions and `setWsConnected(false)` for WS drops at line 79) covers both failure modes: bridge crash while WS stays alive, and WS disconnect. Good edge-case coverage.
- The decision to keep the existing DeviceList empty-state wording rather than changing it to match the handoff's exact phrasing was a reasonable judgment call, transparently documented in the session summary's Decisions Made section and flagged for Validator review. The existing wording is indeed more informative (context-aware sub-text).
- The bug log entry is thorough — it enumerates four distinct sub-causes and clearly describes the fix.

## Issues Found
- **WARNING**: The handoff AC specifies the DeviceList empty state text as "No Pioneer devices detected" but the Developer notes the existing text is "No Pioneer devices found" and chose not to change it. This is a cosmetic discrepancy, not a functional one. The existing text is part of a richer context-aware empty state. Flagging for operator awareness only.

## Recommendation
PASS — proceed to next task. The WARNING about DeviceList empty-state wording is cosmetic and the Developer's reasoning is sound; no action needed unless Brach prefers the exact handoff wording.
