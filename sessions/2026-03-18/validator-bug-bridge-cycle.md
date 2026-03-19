# Validator Verdict: BUG-BRIDGE-CYCLE

## Verdict: PASS (with WARNING)

## Pre-Check: Session Summary
- Session summary exists: YES
- All required fields present: YES — all template fields are present: Role, Objective, Status, Work Performed, Files Changed, Interfaces Added or Modified, Decisions Made, Scope Violations, Remaining Work, Blocked On, Missteps, Learnings.

## Tests
- Pre-existing tests pass: YES — baseline established at 121 bridge + 20 API = 141 passing; full suite after changes runs 156 tests, 0 failed (run output: `156 passed, 3 warnings in 3.97s`).
- New tests added: YES — 15 new tests added across 4 new test classes: `TestNoHardwareStableState` (6), `TestHealthCheckSilenceBehaviour` (2), `TestJVMFlags` (4), `TestRouteFriendlyError` (3). Three existing tests renamed and updated for the `fallback → waiting_for_hardware` behavior change.
- New tests pass: YES — all 156 pass.

## Acceptance Criteria Check

- [x] **AC-1: Graceful hardware disconnect** — MET.
  `_schedule_restart()` now routes to `_enter_waiting_for_hardware()` once `_consecutive_failures >= max_crash_before_fallback` (`manager.py` line 460–468). The `waiting_for_hardware` status is a stable non-cycling state. The `_MIN_STABLE_UPTIME_S` circuit breaker (`manager.py` line 187) prevents the failure counter from resetting during quick crash cycles, ensuring the threshold is actually reached. Tests `test_rapid_crash_cycle_enters_waiting_state` and `test_quick_start_crash_does_not_reset_failures` directly verify these two behaviors. JVM flags at `manager.py` lines 47–51 address focus stealing once the bridge reaches this stable state (fewer subprocess launches overall).

- [x] **AC-2: Auto-recovery after reconnect** — MET.
  `_wait_for_hardware_loop()` (`manager.py` lines 514–538) calls `self.start()` every `_HARDWARE_POLL_INTERVAL_S = 30.0 s`. On a successful start the status transitions to `"running"` and the loop exits naturally (line 523: `while self._status == "waiting_for_hardware"`). `_consecutive_failures` is reset to 0 on entry to `waiting_for_hardware` (`manager.py` line 504) so the next successful start goes through the normal path. Test `test_restart_from_waiting_state_resets_and_starts` confirms that `restart()` from `waiting_for_hardware` reaches `"running"` with counter at 0.

- [x] **AC-3: Bridge restart without hardware present** — MET (route error sub-criterion).
  The stable waiting state on start-with-no-hardware is covered under AC-1 (same `waiting_for_hardware` path). The route fix friendly error is implemented in `fix_route()` (`manager.py` lines 296–308): "bad address" and "no such interface" errors are wrapped with a user-readable message explaining the adapter must be connected. Test `test_bad_address_error_wrapped` confirms the raw "route: bad address" string is replaced with interface/adapter guidance.

- [x] **AC-4: OS focus behavior (bonus)** — MET.
  `_JVM_FLAGS` (`manager.py` lines 47–51) contains `-Djava.awt.headless=true` and `-Dapple.awt.UIElement=true`. Flags are inserted between `"java"` and `"-jar"` in `_launch_subprocess()` (`manager.py` lines 328–340). Test `test_jvm_flags_in_launch_command` captures the actual `subprocess.Popen` call and verifies flag presence and ordering.

- [x] **AC-5: App name (bonus)** — MET.
  `-Xdock:name=SCUE Bridge` is present in `_JVM_FLAGS` (`manager.py` line 50). Test `test_dock_name_flag_present` confirms it.

- [x] **Baseline: pre-existing tests pass** — MET. Full `tests/test_bridge/` + `tests/test_api/` suite at 156 passed, 0 failed. The 3 warnings (coroutine never awaited in mocks) are pre-existing mock interaction artifacts in test infrastructure, not regressions.

## Scope Check

- Files declared in session summary "Files Changed":
  1. `scue/bridge/manager.py`
  2. `tests/test_bridge/test_manager.py`
  3. `docs/bugs/layer0-bridge.md`

- Files actually modified (from `git diff --name-only HEAD`):
  1. `scue/bridge/manager.py` — in scope, declared.
  2. `tests/test_bridge/test_manager.py` — in scope, declared.
  3. `docs/bugs/layer0-bridge.md` — in scope, declared.
  4. `LEARNINGS.md` — in scope (required by COMMON_RULES §9), declared in session summary Learnings section.
  5. `tests/test_api/test_bridge_api.py` — **NOT declared in session summary "Files Changed."**

  The handoff scope boundary permits `tests/test_bridge/` and `scue/api/ws.py` but does not explicitly include `tests/test_api/`. The `tests/test_api/test_bridge_api.py` diff shows the addition of a `TestWebSocketBroadcasting` class (3 tests covering WebSocket connect/broadcast/disconnect). This is not a scope-violating change in content — the tests cover existing WS infrastructure, not new code, and all pass — but the file was modified outside declared scope and was not listed in "Files Changed."

- Out-of-scope modifications: `tests/test_api/test_bridge_api.py` modified but undisclosed.

## What Went Well

- **Circuit breaker logic is well-reasoned and cleanly implemented.** The `_MIN_STABLE_UPTIME_S` guard at `manager.py` line 187 uses a precise two-condition check (`_last_stable_start_time == 0.0 or uptime >= _MIN_STABLE_UPTIME_S`) that correctly handles first-run and subsequent-run cases in a single expression. The accompanying test `test_quick_start_crash_does_not_reset_failures` sets `_last_stable_start_time = time.time()` to simulate a truly recent start — this is a high-quality test because it tests the boundary condition the circuit breaker was designed to enforce.

- **The `waiting_for_hardware` state is architecturally correct.** The Developer's decision to route `waiting_for_hardware` instead of `fallback` for hardware-absent crashes is the right call — it's documented in Decisions Made with clear rationale and rejected alternative. The fallback (UDP parser) is now correctly reserved for JRE/JAR absent cases only. This is a clean separation of failure modes.

- **Health check comments are precise and defensive.** `_health_check_loop` (`manager.py` lines 399–445) has explicit inline comments distinguishing what IS and IS NOT a restart trigger. The docstring calls out Pioneer silence as a non-trigger. This prevents the same misreading that caused the original bug.

- **Test isolation is rigorous.** `TestHealthCheckSilenceBehaviour::test_pioneer_silence_does_not_restart` correctly simulates continuous bridge heartbeats with a background `keep_heartbeat_fresh` task, avoiding the false-positive that caused the misstep during development. The fix (background refresher) is more realistic than setting a future timestamp.

- **LEARNINGS.md was updated with substantive entries.** The "Bridge crash-restart cycle when hardware absent (fixed)" entry (`LEARNINGS.md` lines 165–183) precisely documents all four root causes and their fixes with Prevention rules, following the established format.

## Issues Found

- **WARNING**: `tests/test_api/test_bridge_api.py` was modified but not listed in the session summary's "Files Changed" section. The modification adds `TestWebSocketBroadcasting` (3 tests). The content is legitimate and passes, but the omission means the session summary does not accurately reflect all files changed. Per VALIDATOR.md Step 1, all modified files must appear in "Files Changed."

  Evidence: `git diff --name-only HEAD` includes `tests/test_api/test_bridge_api.py`. Session summary "Files Changed" lists only 3 files; this is the 4th.

- **WARNING**: The `bridge_status` WS payload `mode` field now has a third value `"waiting_for_hardware"`, but `docs/CONTRACTS.md` has not been updated to reflect this. The Developer flagged this correctly under "Remaining Work" and it is a known forward item. However, the fact that a new state value is now emitted over the wire to all WebSocket consumers without a contract update means the Orchestrator should prioritize the CONTRACTS.md update promptly. This is not a CRITICAL issue (the change is additive and the Developer proactively flagged it), but it should be tracked.

- **WARNING** (observation): `test_waiting_state_has_next_retry_set` at line 593–597 has a loose assertion: `assert status["next_retry_in_s"] is None or status["next_retry_in_s"] >= 0`. This passes whether `next_retry_in_s` is `None` or a non-negative number, so it does not actually verify that a retry is scheduled. The test name says "next_retry_set" but the assertion allows `None`. The test verifies `status["status"] == "waiting_for_hardware"` and `status["mode"] == "waiting_for_hardware"` correctly, but the retry-time assertion is effectively vacuous. This is not blocking — the state machine behavior is covered by other tests — but the assertion should be tightened to `is not None`.

## Recommendation

PASS. Proceed to next task.

Three WARNINGs to address (non-blocking, prioritized):
1. **Next Developer session touching this area:** Retroactively add `tests/test_api/test_bridge_api.py` to the BUG-BRIDGE-CYCLE session summary "Files Changed" — or note the omission so it doesn't confuse future Validators reviewing the session.
2. **Orchestrator:** Dispatch an Architect session to update `docs/CONTRACTS.md` with the new `"waiting_for_hardware"` value in the `bridge_status` WS message `mode` field. The Developer flagged this in Remaining Work.
3. **Next Developer touching `TestNoHardwareStableState`:** Tighten the `test_waiting_state_has_next_retry_set` assertion from `is None or >= 0` to `is not None`.
