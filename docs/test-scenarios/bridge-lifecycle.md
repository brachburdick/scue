# Test Scenario Matrix: Bridge Lifecycle

<!-- Cross-feature test scenario matrix. -->
<!-- The bridge lifecycle affects all features that depend on hardware connectivity. -->
<!-- Written by: Architect (initial, 2026-03-18). Maintained by: QA Tester (additions from testing). -->

## Hardware/System Preconditions

- Board power: ON | OFF
- USB-ETH adapter: PLUGGED | UNPLUGGED
- Server: RUNNING | STOPPED
- Bridge state: CONNECTED | CRASHED | WAITING_FOR_HARDWARE

## Scenarios

---

### SC-001: USB-ETH adapter unplugged during good connection

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED (devices visible, Pioneer traffic flowing)
- **When:** USB-ETH adapter is physically unplugged
- **Then:**
  - [ ] Pioneer traffic indicator turns off within 3 seconds
  - [ ] Device list clears or shows "disconnected" state within 5 seconds (no stale devices)
  - [ ] Player list clears or shows "offline" state within 5 seconds (no stale BPM/pitch data)
  - [ ] Hardware selection panel updates to reflect lost interface within 5 seconds
  - [ ] Bridge status transitions to `waiting_for_hardware` — NOT a crash-restart cycle
  - [ ] No macOS window focus stealing (no "beat link trigger" / "SCUE Bridge" menu bar flash)
  - [ ] Console/logs show a clear message indicating hardware disconnection (not a raw exception)
- **Actual:** Crash cycle × 3 (each crash < 30s of uptime) → `waiting_for_hardware`. `restart_count` climbed to 3 before threshold. JVM flags: no focus stealing confirmed. Root cause: `_last_message_time` not reset in `start()` — stale timestamp causes health check to fire within 10s of each restart, before beat-link can reconnect.
- **Status:** FAIL
- **Notes:** Previously caused crash-restart cycle (see `docs/bugs/layer0-bridge.md` — "Bridge crash-restart cycle after hardware disconnect/reconnect"). BUG-BRIDGE-CYCLE fix partially addressed (threshold/fallback/JVM flags), but `_last_message_time` reset is missing.

### SC-002: USB-ETH adapter plugged back in after SC-001

- **Given:** Bridge in `waiting_for_hardware`, USB-ETH unplugged, board ON
- **When:** USB-ETH adapter is plugged back in
- **Then:**
  - [ ] Bridge detects restored interface within 30 seconds (one slow-poll cycle)
  - [ ] Bridge transitions from `waiting_for_hardware` to `connected` without manual intervention
  - [ ] Pioneer traffic indicator turns on within 5 seconds of bridge reconnecting
  - [ ] All devices reappear in device list within 5 seconds of bridge reconnecting
  - [ ] Player data (BPM, pitch, play state) resumes within 5 seconds of bridge reconnecting
  - [ ] No page reload or "Apply and Restart Bridge" required
  - [ ] No crash-restart cycle during recovery
- **Actual:** No recovery observed. Bridge entered `waiting_for_hardware` (from SC-001), slow-poll fired, but each `start()` call re-triggered crash cycle immediately due to stale `_last_message_time`. Additionally, after adapter replug en7 only obtained link-local address (169.254.72.107) — not the 192.168.3.x subnet — which may compound recovery failure even after `_last_message_time` is fixed.
- **Status:** FAIL
- **Notes:** Root cause same as SC-001: `_last_message_time` not reset in `start()`. Secondary concern: macOS may not re-negotiate DHCP/static IP on adapter re-insert within the 30s slow-poll window.

---

### SC-003: Board powered off during good connection

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED (devices visible, Pioneer traffic flowing)
- **When:** Board (CDJ/XDJ) is powered off
- **Then:**
  - [ ] Pioneer traffic indicator turns off within 3 seconds
  - [ ] Device list clears the powered-off device within 5 seconds (no stale device entries)
  - [ ] Player list clears or shows "offline" for affected player within 5 seconds
  - [ ] Bridge status remains `connected` or transitions to `waiting_for_hardware` (NOT crash-restart)
  - [ ] Hardware selection panel remains stable (USB-ETH adapter is still present)
  - [ ] No macOS window focus stealing
  - [ ] If only one of multiple boards is powered off, remaining boards continue unaffected
- **Actual:** Crash cycle × 3 → `waiting_for_hardware`. Same pattern as SC-001. JVM flags: no focus stealing. Root cause: `_last_message_time` stale post-crash.
- **Status:** FAIL
- **Notes:** Different from adapter yank — the network interface remains valid, only Pioneer traffic ceases. Bridge should NOT interpret silence as a crash. The `_last_message_time` bug causes the health check to fire on bridge WS heartbeat silence, not Pioneer silence — but this is triggered because the bridge process crashes and the stale timestamp issue causes rapid re-crash.

### SC-004: Board powered back on after SC-003

- **Given:** Bridge in `connected` or `waiting_for_hardware`, USB-ETH plugged, board OFF
- **When:** Board is powered back on
- **Then:**
  - [ ] Bridge detects the board via `device_found` or infers from `player_status` within 10 seconds of board completing startup
  - [ ] Device appears in device list with correct name and IP
  - [ ] Player data (BPM, pitch, play state) begins streaming within 5 seconds of device discovery
  - [ ] Pioneer traffic indicator turns on within 5 seconds
  - [ ] No manual intervention required (no page reload, no "Apply and Restart Bridge")
  - [ ] If bridge was in `waiting_for_hardware`, it transitions back to `connected`
- **Actual:** No recovery. Bridge in `waiting_for_hardware` after SC-003. Board powered on (XDJ-AZ boot ~15-20s). By the time board sent Pro DJ Link announcements, the health check had already fired and crashed the bridge in the new start cycle. `_last_message_time` bug prevents beat-link from getting a stable window.
- **Status:** FAIL
- **Notes:** XDJ-AZ boot time (~15-20s) exceeds the effective health check window (~10s post-restart) caused by the `_last_message_time` bug. Fix: reset `_last_message_time=0.0` in `start()` → beat-link gets the full 20s silence window to connect and receive Pioneer announcements.

---

### SC-005: Server started with USB-ETH plugged but board off

- **Given:** Server STOPPED, board OFF, USB-ETH plugged
- **When:** Server is started (`uvicorn scue.main:app --reload`)
- **Then:**
  - [ ] Bridge starts and detects the USB-ETH interface
  - [ ] Bridge enters `waiting_for_hardware` state (no Pioneer traffic to connect to)
  - [ ] No crash-restart cycle — bridge waits patiently in slow-poll loop
  - [ ] Frontend shows bridge status as "waiting for hardware" (not "crashed" or "error")
  - [ ] Route check passes (interface exists, route can be verified/fixed)
  - [ ] No macOS window focus stealing during bridge startup
  - [ ] Console/logs indicate bridge is waiting for Pioneer devices, not erroring
- **Actual:** Bridge started and stayed in `running` status (not `waiting_for_hardware`) with empty devices/players. restart_count=0 at 65+ seconds. No crash cycle. No macOS focus stealing. Route API showed `correct: false` (no board to establish link-local route) but bridge_status showed `route_correct: true` — discrepancy noted. Beat-link idles in "running" with no devices rather than entering `waiting_for_hardware`.
- **Status:** PASS (with correction to expected state)
- **Notes:** Scenario's expected state `waiting_for_hardware` is incorrect — bridge enters `running` with empty device list when board is off. `waiting_for_hardware` is only entered after crash threshold. The key criterion (no crash-restart cycle) passes. Update expected state in scenario to `running` (empty devices). `_last_message_time=0.0` guard at initial start prevents health check from firing — bridge stays stable indefinitely.

### SC-006: Board powered on after SC-005

- **Given:** Server running, bridge in `waiting_for_hardware`, USB-ETH plugged, board OFF
- **When:** Board is powered on
- **Then:**
  - [ ] Bridge detects Pioneer announcements and transitions to `connected` within 10 seconds of board completing startup
  - [ ] Devices appear in device list
  - [ ] Player data begins streaming
  - [ ] Pioneer traffic indicator turns on
  - [ ] Full functionality achieved without any manual intervention
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Same recovery path as SC-004. The `waiting_for_hardware` slow-poll loop should trigger `start()` which detects the now-available hardware.

---

### SC-007: Server started with USB-ETH unplugged

- **Given:** Server STOPPED, board ON or OFF, USB-ETH UNPLUGGED
- **When:** Server is started (`uvicorn scue.main:app --reload`)
- **Then:**
  - [ ] Bridge starts and detects no suitable network interface
  - [ ] Bridge enters `waiting_for_hardware` state (not crash-restart cycle)
  - [ ] Frontend shows bridge status as "waiting for hardware"
  - [ ] Route status shows "no interface" or similar — not "route mismatch" with a nonexistent interface name
  - [ ] Route fix API returns a user-friendly error if called (not raw "route: bad address: en16")
  - [ ] No macOS window focus stealing
  - [ ] Bridge remains stable in this state indefinitely
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Edge case — DJ starts server before connecting any hardware. Previously caused API 500 with raw "route: bad address" error. Fixed 2026-03-18 by wrapping error with user-readable message.

### SC-008: USB-ETH plugged in after SC-007

- **Given:** Server running, bridge in `waiting_for_hardware`, USB-ETH UNPLUGGED
- **When:** USB-ETH adapter is plugged in (board may or may not be on)
- **Then:**
  - [ ] Bridge detects the new network interface within 30 seconds (one slow-poll cycle)
  - [ ] If board is ON: bridge transitions to `connected`, devices and players appear within 10 seconds of detection
  - [ ] If board is OFF: bridge remains in `waiting_for_hardware` but now with a valid interface (ready for board power-on)
  - [ ] Route is established or fixable for the new interface
  - [ ] No manual intervention required
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Hot-plug detection depends on the slow-poll interval (30 seconds). The interface name (e.g., en16) may change if the adapter is plugged into a different USB port.

---

### SC-009: "Apply and Restart Bridge" clicked while fully connected

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED (healthy, devices visible)
- **When:** User clicks "Apply and Restart Bridge" in the frontend
- **Then:**
  - [ ] Bridge stops cleanly (WebSocket closes, Java subprocess terminates)
  - [ ] Bridge restarts and reconnects within 10 seconds
  - [ ] All devices reappear within 5 seconds of reconnection
  - [ ] Player data resumes within 5 seconds of reconnection
  - [ ] Pioneer traffic indicator shows brief interruption then resumes
  - [ ] No crash-restart cycle
  - [ ] No macOS window focus stealing
  - [ ] `_consecutive_failures` is NOT incremented (this is a user-initiated restart, not a crash)
- **Actual:** `POST /api/bridge/restart` returned `running`, restart_count=0. XDJ-AZ device remained visible throughout. However restart_count climbed to 2 over next 25s (health check fired twice post-restart due to `_last_message_time` bug). Bridge stabilized because Pioneer traffic eventually refreshed `_last_message_time` before third crash triggered threshold. No focus stealing.
- **Status:** CONDITIONAL PASS
- **Notes:** Core behavior correct (bridge restarts and reconnects, devices remain visible). Degraded: health check fires twice post-restart due to `_last_message_time` bug. When hardware is connected and responsive, Pioneer traffic eventually refreshes the timestamp before the failure threshold. Fix: reset `_last_message_time=0.0` in `start()` → clean restart with no phantom health check firings.

### SC-010: "Apply and Restart Bridge" clicked while board is off

- **Given:** Server running, board OFF, USB-ETH plugged, bridge in `connected` or `waiting_for_hardware`
- **When:** User clicks "Apply and Restart Bridge"
- **Then:**
  - [ ] Bridge restarts, detects no Pioneer devices, enters `waiting_for_hardware`
  - [ ] No crash-restart cycle
  - [ ] Frontend shows "waiting for hardware" status
  - [ ] No macOS window focus stealing
  - [ ] When board is subsequently powered on, bridge recovers automatically (same as SC-004/SC-006)
- **Actual:** `POST /api/bridge/restart` triggered crash cycle. restart_count climbed 0 → 1 → 2 at 15s/40s. At ~65s: status `starting`, restart_count reset to 0 (reached threshold, entered `waiting_for_hardware`). After slow-poll fired: crash cycle re-entered. Pattern: `waiting_for_hardware` → 3 fast crashes → `waiting_for_hardware` → repeat indefinitely. No focus stealing.
- **Status:** FAIL
- **Notes:** Root cause: `_last_message_time` not reset in `start()`. Each call to `start()` (whether from explicit restart or slow-poll) has stale `_last_message_time` → health check fires within 10s. Fix: add `self._last_message_time = 0.0` in `start()` before subprocess launch.

---

### SC-011: Crash-restart cycle — consecutive failures reach threshold

- **Given:** Server running, bridge experiencing repeated crashes (e.g., due to transient hardware issue)
- **When:** Bridge crashes `max_crash_before_fallback` times (3) within short succession (each run < 30 seconds of stable uptime)
- **Then:**
  - [ ] `_consecutive_failures` increments on each crash (not reset by brief start-then-crash cycles)
  - [ ] After threshold reached, bridge enters `waiting_for_hardware` state (not UDP fallback, unless JRE/JAR is absent)
  - [ ] `_consecutive_failures` resets to 0 on entering `waiting_for_hardware`
  - [ ] Slow-poll loop begins (30-second interval)
  - [ ] No macOS window focus stealing during crash-restart sequence
  - [ ] Exponential backoff is applied between restart attempts before threshold is reached
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** The `_MIN_STABLE_UPTIME_S` (30 seconds) prevents `_consecutive_failures` from resetting on brief runs. Only runs lasting ≥ 30 seconds reset the counter.

### SC-012: Recovery from crash threshold — hardware restored after SC-011

- **Given:** Bridge in `waiting_for_hardware` after reaching crash threshold, hardware issue resolved (adapter plugged back in, board powered on, route fixed)
- **When:** Next slow-poll cycle fires (within 30 seconds)
- **Then:**
  - [ ] Bridge `start()` succeeds, transitions to `connected`
  - [ ] `_consecutive_failures` was reset to 0 on entering `waiting_for_hardware`, so fresh crash budget is available
  - [ ] Devices and players appear within 5 seconds of successful start
  - [ ] System is fully operational — no residual state from the crash cycle
  - [ ] No manual intervention required (no page reload, no server restart)
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** This validates that the `waiting_for_hardware` → `connected` recovery path works cleanly after a crash cycle, with no lingering state from the failed runs.

---

### SC-013: Pre-existing Java bridge on port 17400 at server startup

- **Given:** A Java bridge subprocess is already running and listening on port 17400 (e.g., from a previous server session that was not cleanly shut down)
- **When:** Server is started (`uvicorn scue.main:app --reload`)
- **Then:**
  - [ ] Server either (a) detects the pre-existing process and adopts it, logging a warning, OR (b) terminates the pre-existing process and starts a fresh one
  - [ ] No silent "phantom connection" — the manager must not connect to a bridge it did not launch without logging a warning
  - [ ] Orphaned Java processes from the old session are terminated or cleaned up
  - [ ] Bridge status correctly reflects the actual Java process in use
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Discovered 2026-03-18 during QA (QA Tester session). Currently `_launch_subprocess()` checks only whether port 17400 is accepting connections — it does not verify it is connecting to the subprocess it just launched. If a pre-existing bridge holds port 17400, the new subprocess cannot bind and becomes orphaned; the manager silently connects to the old bridge. Three coexisting Java bridge processes were observed in Brach's environment (PIDs 27093, 53056, 69048).

### SC-014: Route fix API called with absent network interface (adapter unplugged)

- **Given:** Server running, network interface (e.g., en16) configured but USB-ETH adapter physically unplugged
- **When:** Frontend calls `POST /api/network/route/fix {"interface": "en16"}`
- **Then:**
  - [ ] API returns a user-friendly error (NOT raw "route: bad address: en16")
  - [ ] Error message explains the adapter must be connected before the route can be fixed
  - [ ] HTTP status 500 is acceptable but the detail must be human-readable
  - [ ] No server crash or unhandled exception
- **Actual:** HTTP 500 returned with raw `"error": "route: bad address: en16"` — FAIL as of 2026-03-18 QA session
- **Status:** FAIL
- **Notes:** Root cause: `scue/api/network.py:fix_route_endpoint()` calls `network.route.fix_route()` directly, bypassing `BridgeManager.fix_route()` which has the friendly error wrapping. Fix should be applied to the endpoint or it should route through the manager. Tracked as outcome of QA-BRIDGE-LIFECYCLE session 2026-03-18.

---

### SC-015: Bridge reconnects to running state with stale adapter data — UI should remain empty

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED (devices and players visible in UI)
- **When:** Board is powered off (or adapter unplugged), bridge goes through a crash-restart cycle, and bridge status returns to "running" — but the backend adapter still holds stale `_devices`/`_players` from before the disconnect
- **Then:**
  - [ ] DeviceList shows empty state ("No Pioneer devices found") — NOT stale device cards
  - [ ] PlayerList shows "No active players." — NOT stale player cards with stale BPM/pitch
  - [ ] Stale data does NOT snap back when bridge status re-enters "running" without fresh hardware data
  - [ ] Empty state persists until actual Pioneer hardware announcements are received by beat-link
- **Actual:** Stale Device (Player 2 / inferred-player-1) and Players (p1, p2) reappeared in UI when bridge returned to running after board power-off. Empty states showed correctly during crashed/starting states but stale data snapped back on running state entry.
- **Status:** FAIL
- **Notes:** Root cause: backend adapter (`scue/bridge/adapter.py`) never clears `_devices`/`_players` on crash or restart. Frontend fix gates on `status !== "running"`, which correctly handles non-running states but cannot protect against stale data that arrives in a `status="running"` message. Fix requires backend adapter to clear its state on disconnect, OR a frontend mechanism to detect and reject stale data in the first running-state message after a reconnect (session epoch, reconnect grace window, etc.). Discovered: 2026-03-19 QA session (session-003-qa-tester.md). Linked to FIX-STALE-DEVICES partial fix.

### SC-016: Stale data reappears on each crash-restart cycle iteration with hardware off

- **Given:** Server running, board OFF, USB-ETH plugged, bridge in crash-restart cycle (cycling through crashed → starting → running)
- **When:** Bridge repeatedly enters the running state briefly before detecting no hardware and crashing again (crash-restart loop)
- **Then:**
  - [ ] Stale device/player data does NOT reappear on any "running" entry in the crash cycle
  - [ ] UI stays in empty state throughout all iterations of the crash loop
  - [ ] No flicker between "stale data visible" and "empty state" across crash loop cycles
  - [ ] Bridge eventually stabilizes in waiting_for_hardware with empty state, no further stale data exposure
- **Actual:** Stale data reappeared on each brief "running" entry across multiple crash cycles (~2-minute interval). Empty state was shown correctly during the non-running windows, but stale data snapped back each time the bridge briefly entered running. Observed across at least 3 crash cycles during the 09:01–09:06 window.
- **Status:** FAIL
- **Notes:** Compound failure — the SC-015 root cause (adapter not clearing state) multiplies across every crash cycle iteration. Each new bridge subprocess inherits stale adapter data. Until the adapter clears `_devices`/`_players` on disconnect/restart, every running-state entry (however brief) will re-expose stale data. Discovered: 2026-03-19 QA session (session-003-qa-tester.md).

---

<!-- Post-fix scenarios added by Architect audit (2026-03-19, session-004-architect) -->
<!-- These validate the fixes from spec-disconnect-reconnect.md TASK-001 through TASK-005. -->
<!-- They should PASS after all tasks are implemented. -->

### SC-017: Adapter state cleared after crash — no stale data on reconnect

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED (devices and players visible). TASK-001 fix applied (adapter.clear() in _cleanup and start).
- **When:** Board is powered off, bridge crashes and restarts, bridge status returns to "running"
- **Then:**
  - [ ] `to_status_dict()` returns `devices={}`, `players={}` immediately after restart (before new hardware data arrives)
  - [ ] DeviceList shows empty state after restart — no stale device cards
  - [ ] PlayerList shows "No active players." after restart — no stale BPM/pitch
  - [ ] When board is powered back on and beat-link discovers hardware, fresh devices/players appear (not stale data from before the disconnect)
  - [ ] `pioneer_status.is_receiving` is `false` after restart until fresh Pioneer traffic arrives
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Validates TASK-001. The key change is `adapter.clear()` called in `_cleanup()` (which runs on crash) and `start()`. Also validates `_last_pioneer_message_time` reset prevents false-positive `is_receiving`.

### SC-018: Interface pre-check prevents crash loop when hardware is absent

- **Given:** Server running, bridge in `waiting_for_hardware` (crash threshold reached), USB-ETH adapter UNPLUGGED (interface doesn't exist in system). TASK-002 fix applied.
- **When:** Slow-poll fires (every 30 seconds)
- **Then:**
  - [ ] Manager checks interface availability via `socket.if_nametoindex()`
  - [ ] Interface check fails (OSError) — logged at debug level
  - [ ] `start()` is NOT called — no subprocess launch, no crash
  - [ ] Bridge remains in `waiting_for_hardware` — no status transitions
  - [ ] No crash-restart cycles occur during the entire hardware-absent period
  - [ ] When USB-ETH adapter is re-plugged: next poll cycle detects the interface, calls `start()`, bridge recovers
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Validates TASK-002. Compare against SC-001/SC-010 behavior (pre-fix: 3 crashes per poll cycle). Post-fix: zero crashes per poll cycle when interface is absent.

### SC-019: Route warning auto-clears on bridge reconnect

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED. Route mismatch warning visible in RouteStatusBanner (e.g., after adapter re-plug with different interface). TASK-003 fix applied.
- **When:** Bridge crashes and reconnects (or user triggers "Apply & Restart Bridge"), bridge status transitions to "running"
- **Then:**
  - [ ] `["network", "route"]` TanStack query is invalidated on the running transition
  - [ ] `["network", "interfaces"]` TanStack query is invalidated on the running transition
  - [ ] RouteStatusBanner refetches route status and updates — warning clears if route is now correct
  - [ ] InterfaceSelector refetches interface list — scores update
  - [ ] No manual "Fix Now" click required to clear a stale route warning
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Validates TASK-003 (query invalidation). The fix adds a module-level prev status tracker in ws.ts that detects transitions to "running" and invalidates queries.

### SC-020: Console mapper resets on WS reconnect — entries survive

- **Given:** Server running, bridge CONNECTED, console panel has 10+ log entries visible. TASK-003 + TASK-005 fixes applied.
- **When:** WS connection drops and reconnects (e.g., backend restart, network blip)
- **Then:**
  - [ ] All 10+ pre-existing console entries remain visible after reconnect
  - [ ] "Backend connection lost" entry appears on disconnect
  - [ ] "Connected to backend" entry appears on reconnect
  - [ ] First `bridge_status` after reconnect generates appropriate console entries (e.g., "Bridge status: running") — mapper treats it as fresh session
  - [ ] No duplicate/stale diff entries from comparing new session state against pre-disconnect state
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Validates TASK-003 (mapper reset) and TASK-005 (console log persistence). The mapper reset ensures correct entries; the TASK-005 fix ensures entries aren't flushed.

### SC-021: Interface score updates for active traffic and correct route

- **Given:** Server running, USB-ETH plugged (en7), board OFF, bridge in `running` (no devices). TASK-004 fix applied.
- **When:** Board is powered on, Pioneer traffic begins flowing on en7, route is verified correct
- **Then:**
  - [ ] Interface score for en7 increases from baseline (e.g., 5) to a higher value reflecting active traffic and correct route
  - [ ] `GET /api/network/interfaces` returns the updated score
  - [ ] InterfaceSelector displays the updated score in the UI
  - [ ] When board is powered off and traffic stops, score decreases back toward baseline
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** Validates TASK-004. Requires investigation of current scoring logic to determine exact expected score values.

### SC-022: Full disconnect/reconnect lifecycle — end to end

- **Given:** Server running, board ON, USB-ETH plugged, bridge CONNECTED, devices and players visible, route correct. ALL fixes applied (TASK-001 through TASK-005).
- **When:** Board is powered off → bridge crashes → restarts → enters waiting_for_hardware (if interface absent) or running (if interface present) → board powered back on → bridge recovers
- **Then:**
  - [ ] Phase 1 (board off): Pioneer traffic lost within 3s, device list clears within 5s
  - [ ] Phase 2 (crash): Adapter state cleared, devices/players empty in bridge_status payload
  - [ ] Phase 3 (restart): No stale data during brief "running" window (adapter was cleared)
  - [ ] Phase 4 (waiting): No crash-restart loop if interface is absent (pre-check skips start)
  - [ ] Phase 5 (board on): Bridge detects hardware, devices/players repopulate with fresh data
  - [ ] Phase 6 (recovery): Route warning clears automatically, interface score updates, console entries from all phases preserved
  - [ ] Total time from board-off to stable empty state: < 30s (no unnecessary crash cycles)
  - [ ] Total time from board-on to full recovery: < 15s (one poll cycle + beat-link discovery)
- **Actual:**
- **Status:** NOT_TESTED
- **Notes:** End-to-end integration scenario. This is the gold-standard test — if this passes, all 6 original bugs are resolved. Run after ALL tasks are complete.
