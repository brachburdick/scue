# QA Verdict: FIX-STALE-DEVICES

<!-- Written by: QA Tester agent -->
<!-- Consumed by: Orchestrator (to decide proceed vs. rework) -->
<!-- A bug fix is not COMPLETE until this verdict is PASS. -->

## Verdict: FAIL

## Environment

- Server: `uvicorn scue.main:app --reload`, port 8000, cwd `/Users/brach/Documents/THE_FACTORY/DjTools/scue`
- Frontend: `npm run dev`, port 5174 (5173 was occupied)
- Hardware: XDJ-AZ, USB-Ethernet adapter (en7), board powered ON then OFF during testing
- Browser: Operator-verified UI (localhost:5174, Bridge page)
- Date: 2026-03-19

## Scenarios Executed

| Scenario | Status | Notes |
|----------|--------|-------|
| FE-SD-01 | PASS | Store populates devices/players when status=running (22 unit tests, all pass) |
| FE-SD-02 | PASS | Store force-clears on status transition to crashed/starting/waiting_for_hardware |
| FE-SD-03 | PASS | setWsConnected(false) clears devices/players (store unit test + logic verified) |
| FE-SD-04 | PASS | Store repopulates from fresh bridge_status data after reconnect |
| FE-SD-05 | PASS | Stale backend payloads in non-running states are ignored (injection tests, all pass) |
| FE-SD-06 | PASS | dotStatus computation correct for all 7 status values |
| UI-01 (PlayerList empty state) | PASS | "No active players." box renders correctly — dashed border, gray text, visible |
| UI-02 (DeviceList empty state) | PASS | "No Pioneer devices found on en7." box renders correctly |
| UI-03 (non-running clears UI) | PASS | During crashed/starting states, device and player sections show empty state boxes |
| UI-04 (reconnect repopulates) | FAIL | After bridge returns to running, stale devices and players reappear in UI |
| LIVE-WS-01 | PASS | Backend sends bridge_status immediately on WS connect with correct field shape |
| LIVE-WS-02 | PASS | devices={}, players={} when no hardware connected |
| LIVE-WS-03 | PASS | pioneer_status received periodically, is_receiving=False with no hardware |
| RESTART-01 | PASS | Status transitions running→starting→running observed during restart cycle |

## Failures

### UI-04: Stale device and player data reappears after bridge reconnect in running state

- **Expected:** After board is powered off and bridge goes through a crash-restart cycle, when bridge reconnects and status returns to "running", DeviceList and PlayerList should be empty (no stale data from before the disconnect).
- **Observed:** When bridge status returned to "running" after the crash-restart cycle, Player 2 (inferred-player-1) reappeared under Devices, and p1/p2 reappeared under Players. These were stale entries from before the board was powered off. The empty-state boxes showed correctly DURING the crashed and starting states, then stale data snapped back in when running was restored.
- **Logs (from operator console):**
  ```
  09:01:21.520 PIO Pioneer traffic lost
  09:01:21.520 PIO Bridge connection lost
  09:01:25.004 BRG Device lost: 192.168.3.2
  09:01:25.523 PIO Pioneer traffic resumed
  09:01:25.523 PIO Bridge connection restored
  09:01:31.527 PIO Pioneer traffic lost
  09:01:31.527 PIO Bridge connection lost
  09:01:47.440 BRG Bridge crashed (restart 1/3)
  09:01:47.441 BRG Bridge restarted (count: 1)
  09:02:02.949 BRG Bridge crashed → starting
  09:02:04.026 BRG Bridge connected on en7 (port 17400)
  ```
  After the final log line (bridge reconnected), stale Devices and Players data reappeared in the UI.
- **Root cause:** The frontend fix gates on `status !== "running"` to clear stale data. This is correct and works during crashed/waiting states. However, the backend bridge adapter (`scue/bridge/adapter.py`) never clears its `_devices` and `_players` dicts when the bridge crashes or restarts. When the new bridge subprocess connects back, the adapter already has stale entries. `to_status_dict()` serializes these stale entries into the first `bridge_status` payload sent with `status="running"`. The frontend sees `status="running"` and trusts the data — passing it through to the store and components. The Developer's session summary documented this root cause as an out-of-scope backend bug; the frontend-only fix is insufficient to fully resolve it.
- **Severity:** BLOCKING — the bug report's core symptom (stale data visible after hardware disconnect) is not fully resolved. The fix works during the intermediate non-running states but fails at the critical moment: when the bridge reconnects.

### SC-004 / CRASH-LOOP: Bridge crash-restart loop with hardware off, stale data persists across cycles

- **Expected:** When hardware is powered off and bridge enters crash-restart cycle, the system should eventually stabilize in waiting_for_hardware with empty device/player state.
- **Observed:** Bridge entered crash-restart loops approximately every 2 minutes when hardware remained off (observed at 09:01, ~09:03, ~09:06). During each loop, stale data was correctly cleared while in crashed/starting state, but reappeared each time the bridge briefly re-entered running state before detecting hardware was gone. The stale data snap-back happened on each crash cycle, not just once.
- **Logs:** Crash pattern repeating at ~2-minute intervals (see operator observation above).
- **Root cause:** Same as UI-04. The adapter retains stale `_devices`/_players` across restarts. Combined with the known `_last_message_time` bug (SC-001/SC-003 in bridge-lifecycle.md), the bridge repeatedly enters running then quickly crashes, giving the stale data multiple opportunities to reappear.
- **Severity:** BLOCKING — compounds the primary failure. Every crash cycle re-exposes the stale data.

## Regression Check

- Previously passing scenarios still pass: YES — store unit tests (22 assertions), typecheck, live WS baseline all pass. No regressions introduced by the fix. The fix correctly handles all non-running states it was designed for.
- The failure is a coverage gap in the fix, not a regression.

## Mock Tool Gaps

- UI-04 requires physical hardware (board power-off while bridge is connected) to reproduce the stale-data-on-reconnect failure. The mock_bridge.py tool does not support simulating a bridge that reconnects with stale adapter state. A mock that can inject a `bridge_status` message with `status="running"` and non-empty stale `devices`/`players` payloads would allow this scenario to be tested without hardware. This is a gap in the mock infrastructure.

## What Passed (partial credit for the fix)

The fix is not without value. The following behaviors now work correctly that did not work before:

1. PlayerList renders "No active players." visible empty state instead of returning null. This is a genuine improvement — the component was previously invisible on empty, which was a separate presentation bug.
2. During non-running states (crashed, starting, waiting_for_hardware), DeviceList and PlayerList correctly show empty state and do not display stale data. This is the intended behavior and works.
3. WebSocket disconnect correctly clears store — if the WS drops entirely, stale data is cleared.

The fix is correct for the states it covers. The gap is the running-state re-entry with stale backend data.

## Recommendation

FAIL — return to Developer for a targeted rework. The fix requires one of the following resolutions:

**Option A (backend fix — preferred, proper upstream fix):** Clear `_devices` and `_players` in `BridgeAdapter` when the bridge connection drops or the manager transitions out of running state. This ensures `to_status_dict()` never includes stale data regardless of frontend behavior. Likely in `scue/bridge/adapter.py` and/or `scue/bridge/manager.py`. The Developer's session summary flagged this as the proper upstream fix but deferred it as out of scope.

**Option B (frontend-only fix — acceptable if backend change is too risky):** Instead of only gating on status, the frontend should track the last time it entered `running` state and reject device/player data from the first `bridge_status` message received after a non-running period (a "reconnect grace window"). Alternatively, the backend could include a `session_id` or `connection_epoch` field in bridge_status payloads that increments on each new bridge subprocess start — the frontend clears its device/player cache whenever the epoch changes.

**Option C (belt-and-suspenders):** Implement both A and B.

The Developer handoff for the rework should reference:
- This verdict (UI-04, SC-004/CRASH-LOOP failures)
- `scue/bridge/adapter.py` — `_devices` and `_players` never cleared on disconnect
- `scue/bridge/manager.py` — `to_status_dict()` serializes adapter state directly

**Separate operator concern — out of scope for this fix but logged:** The operator noted that the overall disconnect/reconnect flow is "WAY too slow and needs better visual indication of what's actually happening." The crash-restart cycle takes ~1-2 minutes to stabilize, with no clear UI feedback during that window. This is a UX issue separate from the stale data bug. It should be tracked as a new feature request or UX improvement task, not bundled into the FIX-STALE-DEVICES rework.
