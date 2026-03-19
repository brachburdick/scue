# QA Verdict: Bridge Lifecycle — BUG-BRIDGE-CYCLE Fix Verification

<!-- Written by: QA Tester -->
<!-- Sessions: 2026-03-18 (two sessions — API-only + live hardware) -->
<!-- Consumed by: Orchestrator (to decide proceed vs. rework) -->
<!-- A bug fix is not COMPLETE until this verdict is PASS. -->

## Verdict: FAIL

**Two distinct failures confirmed:**

1. **`_last_message_time` not reset in `start()` — critical regression.** All disconnect/reconnect scenarios (SC-001 through SC-004, SC-010) result in crash-restart cycles due to a stale health check timestamp. The BUG-BRIDGE-CYCLE fix did not address this. Root cause: `self._last_message_time` is never reset to `0.0` before launching a new subprocess. At initial cold start `_last_message_time=0.0` so the health check guard `if self._last_message_time > 0` is false — health check doesn't fire, bridge stays stable. After any crash, `_last_message_time` holds the timestamp of the last message from the *previous* run — health check fires within 10s of restart, before beat-link can reconnect — drives another crash — repeat.

2. **Route fix API returns raw kernel error.** `POST /api/network/route/fix` with a nonexistent interface returns `"route: bad address: en16"`. The fix was applied to `BridgeManager.fix_route()` only; `scue/api/network.py:fix_route_endpoint()` calls the network module directly.

**JVM flags work correctly.** Zero macOS focus stealing or menu bar flashes confirmed across all tested scenarios.

---

## Environment

### Session 1 (API-only, 2026-03-18 morning)
- Server: `.venv/bin/python -m uvicorn scue.main:app --port 8765 --log-level info`
- Hardware: Real Pioneer XDJ-AZ connected on interface `en7` (route_correct: true; two inferred players). No mock_bridge.py used.
- Pre-existing Java bridge processes from earlier sessions (PIDs 27093, 53056) on port 17400.
- Unit test baseline: **136/136 PASS**

### Session 2 (Live hardware, 2026-03-18 evening)
- Server: `.venv/bin/python -m uvicorn scue.main:app --reload` (default port 8000)
- Hardware: Pioneer XDJ-AZ on en7 (192.168.3.2). Operator physically present for checkpoints.
- Orphaned Java processes from Session 1 killed before session began.
- Unit test baseline: **136/136 PASS** (verified at start of Session 2)

---

## Scenarios Executed

| Scenario | Status | Session | Notes |
|----------|--------|---------|-------|
| SC-001 | FAIL | 2 | Crash cycle × 3 → `waiting_for_hardware`. `_last_message_time` bug. |
| SC-002 | FAIL | 2 | No recovery from `waiting_for_hardware`. `_last_message_time` bug. |
| SC-003 | FAIL | 2 | Crash cycle × 3 → `waiting_for_hardware`. `_last_message_time` bug. |
| SC-004 | FAIL | 2 | No recovery (board boots too slow vs 10s health check window). `_last_message_time` bug. |
| SC-005 | PASS | 2 | Cold start with board off: no crash cycle, bridge idles in "running" with empty devices. `_last_message_time=0.0` guard works. |
| SC-006 | NOT_TESTED | — | Skipped — SC-004 already confirmed recovery fails for same root cause. |
| SC-007 | FAIL | 1 | Route fix API returns raw kernel error. |
| SC-008 | NOT_TESTED | — | Physical hot-plug detection; not tested this session. |
| SC-009 | CONDITIONAL PASS | 1+2 | restart_count climbs to 2 post-restart (health check fires twice) but bridge stays "running". |
| SC-010 | FAIL | 2 | Crash cycle after user-initiated restart with board off. Slow-poll → 3 crashes → `waiting_for_hardware` → slow-poll → repeat. |
| SC-011 | CANNOT_TEST | — | Cannot safely simulate crash cycle with real hardware. |
| SC-012 | CANNOT_TEST | — | Depends on SC-011. |
| SC-013 | NOT_TESTED | — | Port-conflict / orphaned process scenario; documented as concern in Session 1. |
| SC-014 | FAIL | 1 | Route fix API with absent interface. See SC-007 failure. |

---

## Failures

### FAIL-1: `_last_message_time` not reset in `start()` — drives crash cycle on all restarts

**Affected scenarios:** SC-001, SC-002, SC-003, SC-004, SC-010 (and by extension SC-006, SC-012)

**Symptom observed across SC-001, SC-003 (live hardware):**
- Adapter unplugged / board powered off
- Bridge WebSocket goes silent → health check fires ~20s after disconnect
- Bridge crashes, `_schedule_restart()` called
- `start()` launches new subprocess — but `_last_message_time` still holds timestamp from previous run
- Health check fires within 10s of restart (old timestamp is >20s stale relative to now)
- Crash × 3 → `_enter_waiting_for_hardware()` → restart_count reset to 0
- No recovery unless `_last_message_time` gets refreshed — which requires beat-link to send messages faster than the health check fires

**Symptom observed in SC-010 (user restart, board off):**
- `POST /api/bridge/restart` called
- restart_count climbs: 0 → 1 → 2 at 15s/40s marks
- At ~65s: `waiting_for_hardware`, restart_count=0
- After slow-poll fires: crash cycle re-enters. restart_count climbs again.
- Oscillates forever: `waiting_for_hardware` → 3 fast crashes → `waiting_for_hardware` → repeat

**Why SC-005 passes (cold start):**
- At process start, `_last_message_time = 0.0` (class default)
- Health check guard: `if self._last_message_time > 0` — evaluates False
- Health check silence condition never fires
- Bridge stays in "running" indefinitely with empty device list

**Root cause:** `scue/bridge/manager.py` — `start()` does not reset `_last_message_time` to `0.0`
before launching the subprocess.

**Fix required:**
```python
# In BridgeManager.start(), before _launch_subprocess():
self._last_message_time = 0.0
```

**Expected impact of fix:** All reconnect/restart scenarios (SC-001 through SC-004, SC-010) will
stop crash-cycling. Beat-link will have the full health check window (20s) to connect and send
its first heartbeat.

---

### FAIL-2: Route fix API returns raw kernel error (SC-007 / SC-014)

- **Expected:** `POST /api/network/route/fix {"interface": "en16"}` returns a user-friendly error.
- **Observed:** HTTP 500:
  ```json
  {"detail": {"success": false, "error": "route: bad address: en16", "previous_interface": "en7", "new_interface": "en16"}}
  ```
- **Root cause:** `scue/api/network.py:114` — `fix_route_endpoint()` calls `fix_route(body.interface)` directly from `scue.network.route`, bypassing `BridgeManager.fix_route()` (lines 296-308) where the friendly error wrapping lives.
- **Fix required in:** `scue/api/network.py:fix_route_endpoint()` — route call through `_bridge_manager.fix_route()` or apply wrapping directly in the endpoint.

---

## Passes

### JVM flags — macOS focus stealing suppressed

Across all tested scenarios (SC-001 three crash+restart cycles, SC-002, SC-003, SC-005 cold
start, SC-009 explicit restart, SC-010 crash cycle): **zero macOS window focus stealing events,
zero "beat link trigger" or "SCUE Bridge" menu bar flashes reported by operator.**

`_JVM_FLAGS = ["-Djava.awt.headless=true", "-Dapple.awt.UIElement=true", "-Xdock:name=SCUE Bridge"]`
is confirmed working. This was one of the four root causes fixed in BUG-BRIDGE-CYCLE.

### `_consecutive_failures` threshold and waiting_for_hardware state

Confirmed working across SC-001, SC-003, SC-010: exactly 3 crashes → `_consecutive_failures`
reaches `max_crash_before_fallback` → `_enter_waiting_for_hardware()` → `restart_count` resets
to 0 → slow-poll starts. No UDP fallback entered (that path is now JAR/JRE-absent only).

---

## Regression Check

- Unit tests 136/136: PASS
- Previously-working SC-009 (explicit restart): CONDITIONAL PASS — restart_count climbs to 2
  post-restart (health check fires twice due to `_last_message_time` bug) but bridge stays
  "running" and devices remain visible throughout. Degraded but functional.

---

## Concerns (Non-Blocking)

### [CONCERN] SC-009: Orphaned Java bridge subprocesses (pre-existing issue)

`BridgeManager._launch_subprocess()` verifies port 17400 is accepting connections but does NOT
verify the subprocess it just launched is the one holding the port. If a pre-existing bridge
holds port 17400, the newly launched subprocess is orphaned and the manager silently connects
to the old bridge. Three coexisting Java processes (PIDs 27093, 53056, 69048) observed in
Session 1. Pre-existing issue, not introduced by BUG-BRIDGE-CYCLE fix. Tracked in SC-013.

### [CONCERN] bridge_status `route_correct` vs `/api/network/route` `correct` discrepancy

In SC-005: bridge status API reported `route_correct: true` while `/api/network/route` reported
`correct: false`. These two endpoint's route checks may use different code paths or cache
different state. Not investigated further — does not affect hardware connectivity when board is
off, but worth investigating separately.

### [CONCERN] Bridge manager INFO logs not surfaced in server output

`scue.bridge.manager` uses `logger.info()` for lifecycle events. Python root logger defaults to
WARNING level, so these don't appear in uvicorn output. Only `logger.warning()` events surface.
Makes live bridge lifecycle tracing difficult.

---

## Mock Tool Gaps

- **SC-001, SC-002, SC-003, SC-004, SC-006, SC-008**: Physical Pioneer hardware manipulation
  required (USB-ETH plug/unplug, board power toggle). No mock equivalent — checkpoints used.
- **SC-011, SC-012**: Cannot safely simulate crash cycles in a live environment with real hardware.
  Require software-level crash simulation. `SCUE_FORCE_MOCK_BRIDGE=1` env var would unblock these.

---

## Recommendation

**FAIL — Do not mark BUG-BRIDGE-CYCLE as COMPLETE.**

**Required before marking complete:**

1. **Fix `_last_message_time` not reset in `start()`.** Add `self._last_message_time = 0.0` at
   the start of `BridgeManager.start()` before subprocess launch. Re-run SC-001, SC-003
   (adapter yank, board power off) and SC-010 (restart with board off) with live hardware.

2. **Fix `scue/api/network.py:fix_route_endpoint()`.** Apply friendly error wrapping for
   "bad address" / "no such interface" kernel errors. Re-run SC-007
   (`POST /api/network/route/fix {"interface": "en16"}`) and confirm user-friendly error returned.

**Optional follow-up (non-blocking):**
- Investigate port-conflict scenario in `_launch_subprocess()` (SC-013).
- Improve bridge lifecycle logging visibility in development.
- Add `route_correct` consistency between bridge status and `/api/network/route` endpoint.
