# Session Summary: FIX-STALE-DEVICES

## Role
QA Tester

## Objective
Execute live test scenarios to verify that the FIX-STALE-DEVICES fix (Developer session-001, Validator session-002) correctly resolves the bug: when Pioneer hardware disconnects or bridge enters a non-running state, DeviceList and PlayerList must show empty state instead of stale last-known values.

## Status
COMPLETE — verdict: FAIL

## Work Performed
- Read all required preamble files, handoff packet, Validator verdict, and Developer session summary
- Read changed files: `frontend/src/stores/bridgeStore.ts`, `frontend/src/components/bridge/PlayerList.tsx`
- Read the bridge manager and adapter to understand the full data flow
- Started backend (uvicorn), frontend (vite), confirmed both reached baseline state
- Ran frontend typecheck — clean (no regressions)
- Wrote and executed store logic unit tests (22 assertions covering all 8 scenario branches) — all PASS
- Wrote and executed stale data injection tests (10 assertions simulating the exact bug scenario with stale backend payloads) — all PASS
- Ran live WebSocket integration tests (10 assertions against running backend) — all PASS
- Observed live bridge restart cycle via WebSocket: confirmed status transitions running→starting→running, confirmed empty devices/players in non-running bridge_status messages
- Issued UI-01 checkpoint — operator verified browser UI
- Received operator visual verification results with live board disconnect test
- Identified failure mode: stale data reappears when bridge returns to running after crash-restart
- Wrote QA verdict to `specs/feat-FE-BLT/sessions/session-003-qa-tester.md`
- Appended SC-015 and SC-016 to `docs/test-scenarios/bridge-lifecycle.md`

## Files Changed
- `specs/feat-FE-BLT/sessions/session-003-qa-tester.md` — QA verdict (this session's primary artifact)
- `docs/test-scenarios/bridge-lifecycle.md` — appended SC-015 and SC-016 (new FAIL scenarios discovered during testing)

## Interfaces Added or Modified
None

## Decisions Made
- **Used Python mirror of store logic for unit testing rather than browser automation**: The store's `setBridgeState()` and `setWsConnected()` logic is pure function-equivalent (no side effects beyond state), so mirroring it in Python gives exact behavioral coverage without needing a browser automation tool. Alternative considered: Playwright E2E test — rejected because it would require a full test harness setup and is not available in the current environment. The Python mirror is not a replacement for browser tests but is sufficient to verify the conditional logic.
- **Operator checkpoint used for UI rendering verification**: The PlayerList empty state rendering (the component returning a styled div vs. null) requires a browser to verify. Issued checkpoint UI-01 to operator rather than marking as CANNOT_TEST, per preamble guidance (prefer checkpoint over REQUIRES_OPERATOR when operator can perform the action).
- **Classified verdict as FAIL rather than PARTIAL PASS**: The acceptance criterion "When Pioneer hardware disconnects, DeviceList clears to empty state" is not fully met — stale data reappears at the critical moment of reconnect. The fix makes partial progress (correct behavior during non-running states) but the bug's core symptom (stale data visible after hardware disconnect) is still reproducible. A FAIL verdict is the correct gate.

## Scope Violations
None

## Remaining Work
The fix requires a rework — see QA verdict for Option A/B/C remediation paths. Recommended: backend adapter clears `_devices`/`_players` on crash/disconnect (`scue/bridge/adapter.py`).

## Blocked On
None

## Missteps
- Attempted to use `urllib.request` in a Python 3.13 async context for HTTP calls — timed out. Switched to `subprocess.run(["curl", ...])` which worked correctly.
- The `POST /api/bridge/restart` endpoint blocks until the bridge restarts (not async fire-and-forget). This meant triggering it from within an async WS observation loop required a thread. Used `threading.Thread` to run the curl call concurrently with WS message collection.
- First frontend dev server started on port 5174 (5173 was occupied by a pre-existing process). Noted in Environment section.

## Learnings
- The frontend `status === "running"` gate is a necessary but not sufficient fix for stale data. The backend adapter retaining state across bridge restarts means the first `bridge_status` with `status="running"` after a reconnect will carry stale data. Frontend-only fixes cannot fully protect against stale data that arrives in a trusted (running) state message. The proper fix is upstream in the adapter.
- The `POST /api/bridge/restart` endpoint is synchronous (blocks until restart completes), which complicates test harnesses that need to observe WS state transitions concurrently with triggering the restart.
- Bridge crash-restart cycles cause stale data re-exposure on every cycle iteration, not just once. This multiplies the user-visible impact: every ~2-minute crash cycle the stale data briefly reappears before being cleared again.
