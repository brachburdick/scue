# Session Summary: BUG-BRIDGE-CYCLE

## Role
Developer (Bridge — Layer 0)

## Objective
Fix the bridge crash-restart cycle that occurs when Pioneer hardware connectivity is disrupted, so that the bridge enters a stable waiting state (not an infinite restart loop) and auto-recovers when hardware returns — without user intervention.

## Status
COMPLETE

## Work Performed
- Read all required preamble and context files: AGENT_BOOTSTRAP.md, COMMON_RULES.md, DEVELOPER.md, docs/bugs/layer0-bridge.md, LEARNINGS.md (Bridge section), docs/CONTRACTS.md (Layer 0 → Layer 1B section).
- Ran baseline test suite: 121 bridge + 20 API = 141 passed, 0 failed.
- Analysed `manager.py` in full, traced all crash → restart → crash paths.
- Identified 5 root causes (see "Decisions Made" below).
- Implemented all fixes in `scue/bridge/manager.py`.
- Updated 3 existing tests whose behaviour changed (fallback → waiting_for_hardware).
- Added 15 new tests covering: no-hardware stable state, circuit breaker, health check silence, JVM flags, route fix friendly errors.
- Final test count: 156 bridge + API tests, 0 failed. Pre-existing librosa failures in test_layer1/test_analysis_edge_cases.py (6 failures, outside scope, caused by missing librosa module — unchanged from baseline).
- Updated docs/bugs/layer0-bridge.md: marked OPEN entry as FIXED, added full fix details.

## Files Changed
- `scue/bridge/manager.py` — Five fixes: (1) added `_MIN_STABLE_UPTIME_S` circuit breaker to prevent `_consecutive_failures` resetting on quick start-crash cycles; (2) fixed health check to NOT restart on Pioneer silence, only on bridge WebSocket heartbeat silence; (3) added `waiting_for_hardware` state with 30s slow-poll loop via `_enter_waiting_for_hardware()` and `_wait_for_hardware_loop()` — replaces aggressive fallback transition when hardware is absent; (4) added `_JVM_FLAGS` constant and applied to subprocess launch to suppress AWT focus-stealing and "beat link trigger" menu-bar name; (5) added user-friendly error wrapper in `fix_route()` for "route: bad address" kernel errors.
- `tests/test_bridge/test_manager.py` — Updated 3 tests that tested the old fallback-transition behaviour (now transitions to `waiting_for_hardware`). Added import for `RouteFixResult`. Added 4 new test classes: `TestNoHardwareStableState` (6 tests), `TestHealthCheckSilenceBehaviour` (2 tests), `TestJVMFlags` (4 tests), `TestRouteFriendlyError` (3 tests).
- `docs/bugs/layer0-bridge.md` — Marked `[OPEN]` entry as `[FIXED]`, added full fix details for all 5 root causes.

## Interfaces Added or Modified
- New state value `"waiting_for_hardware"` added to `BridgeManager._status` state machine. The `to_status_dict()` `mode` field now returns `"waiting_for_hardware"` when in this state (in addition to existing `"fallback"` and `"bridge"`).
- `_enter_waiting_for_hardware()` — new async method, internal only.
- `_wait_for_hardware_loop()` — new async method, internal only.
- `_cancel_wait_task()` — new sync method, internal only.
- `_last_stable_start_time: float` — new instance attribute, internal only.
- `_wait_task: asyncio.Task | None` — new instance attribute, internal only.
- Module-level constants: `_MIN_STABLE_UPTIME_S = 30.0`, `_HARDWARE_POLL_INTERVAL_S = 30.0`, `_JVM_FLAGS: list[str]`.

None of these are in `docs/CONTRACTS.md`. The `mode` field in `bridge_status` WS payload now has a new possible value `"waiting_for_hardware"`. This is additive — frontend currently handles `"bridge"` and `"fallback"`; `"waiting_for_hardware"` will render as an unknown mode until the frontend is updated (non-breaking for existing frontend logic).

**[DECISION NEEDED — flag for Orchestrator]:** The `bridge_status` WS payload `mode` field now has a third value `"waiting_for_hardware"`. The frontend bridge store/display logic should be updated to surface this as a user-readable state ("Waiting for hardware...") rather than showing a stale/fallback badge. This is a separate frontend task.

## Decisions Made

- **Chose `waiting_for_hardware` state over simply entering `fallback` (UDP parser) when hardware is absent.** Rationale: UDP fallback requires a working network interface to listen on. If hardware is absent (adapter unplugged), the fallback would fail too. More importantly, fallback has no auto-recovery path back to full bridge mode. The waiting state polls every 30 s with `start()`, which naturally recovers when hardware returns. Alternative considered: always start fallback (UDP parser) in degraded mode. Rejected because it doesn't solve the "no interface" case and doesn't recover.

- **Chose 30 s as hardware poll interval.** Rationale: frequent enough to recover within ~30 s of hardware reconnect, infrequent enough to not spam macOS with subprocess launches or steal focus (even with JVM flags). Alternative considered: 60 s (too slow for DJ use case) or 10 s (too aggressive, focus risk).

- **Chose `_MIN_STABLE_UPTIME_S = 30 s` as the minimum uptime threshold.** Rationale: a bridge that runs stably for 30 seconds has clearly had a hardware connection — resetting the failure counter is appropriate. A bridge that crashes within 30 seconds of starting almost certainly had no hardware. Alternative considered: 60 s (overkill), 5 s (too short, could allow reset on spurious crashes).

- **Chose to reset `_consecutive_failures` to 0 on entry to `waiting_for_hardware`.** Rationale: allows the next poll-triggered start to go through the normal crash→backoff→threshold cycle fresh, rather than immediately re-entering `waiting_for_hardware` on the first crash. Alternative considered: preserve count (rejected — would make the state loop tight immediately on first crash in the next cycle).

- **Chose to apply JVM flags globally (all platforms) rather than macOS-only.** Rationale: `-Djava.awt.headless=true` and `-Dapple.awt.UIElement=true` are no-ops on Linux/Windows (JVM accepts unknown `-D` flags silently). `-Xdock:name=...` is macOS-only but also silently ignored on other JVMs. Alternative considered: platform-gating the flags with `if platform.system() == "Darwin"`. Rejected because it adds complexity with no benefit — cross-platform JVMs handle unknown flags gracefully.

- **Chose to wrap the "bad address" error in `manager.py`'s `fix_route()` rather than in `network/route.py`.** Rationale: `scue/network/` is outside the Agent's scope boundary. The `manager.py` `fix_route()` method wraps the result before returning it to the API, which is the correct interception point. Alternative considered: patching `route.py` (rejected — out of scope).

- **Updated 3 existing tests that tested the old `_start_fallback` transition path.** The tests `test_third_failure_transitions_to_fallback`, `test_crash_threshold_transitions_to_fallback`, and `test_consecutive_failures_preserved_after_fallback_transition` explicitly tested the old behaviour (crash threshold → `_start_fallback`). The new behaviour is crash threshold → `_enter_waiting_for_hardware`. I renamed and updated these tests to match. The rename is clearly intentional and documented here.

## Scope Violations
None.

## Remaining Work
- **Frontend stale-state display:** The frontend bridge store/display logic does not yet handle `"waiting_for_hardware"` as a bridge mode. It will receive the new status value but likely show it as an unknown state. This was noted as a separate task in the handoff ("Frontend stale-state fix, dispatched after this"). No frontend changes were made.
- **CONTRACTS.md update:** The `bridge_status` WS message `mode` field has a new possible value `"waiting_for_hardware"`. This should be documented in `docs/CONTRACTS.md` by the Architect in a separate session.
- **Java AWT flags — confirmation needed:** The JVM flags (`-Djava.awt.headless=true`, `-Dapple.awt.UIElement=true`, `-Xdock:name=SCUE Bridge`) have been added to the subprocess launch command. These are the correct flags based on documented Java/macOS behaviour. However, whether `-Djava.awt.headless=true` breaks beat-link's AWT-dependent functionality (beat-link uses Java Swing/AWT internally for its UI model) could not be tested without live hardware. If beat-link AWT initialization is required for its network sockets (unlikely but possible), the headless flag may need to be removed. Monitor on next live hardware test.

## Blocked On
None.

## Missteps
- First run of new tests had 4 failures: (1) `test_rapid_crash_cycle_enters_waiting_state` — test's `mock_start` function created an asyncio task interaction that produced unexpected status; simplified test to use `_schedule_restart()` directly with mocked `_enter_waiting_for_hardware`. (2) `test_pioneer_silence_does_not_restart` — set `_last_message_time = time.time()` once, but 0.15s elapsed exceeded `2 × 0.05s` interval, triggering the bridge-silence check; fixed by adding a background heartbeat task that continuously refreshes `_last_message_time`. (3) & (4) `RouteFixResult` was not imported in the test file; added import.
- Three existing tests needed updating when `_start_fallback` transition was replaced by `_enter_waiting_for_hardware`. This was expected and documented.

## Learnings
- **Health check silence check must distinguish "bridge went silent" from "hardware went silent."** Bridge WebSocket heartbeats (`bridge_status` messages) update `_last_message_time` even when hardware is off. The health check should check `_last_message_time` (all WS traffic) for bridge liveness, not `_last_pioneer_message_time`. These are different failure modes: bridge dead vs hardware absent.
- **Quick start-crash cycles bypass failure counters if `_consecutive_failures` resets on every "running" transition.** Need a minimum stable uptime check before resetting. This pattern applies to any system with a "consecutive failure → fallback" circuit breaker where the protected code can briefly "succeed" (reach a connected state) before crashing.
- **`waiting_for_hardware` is a better terminal state than `fallback` for hardware-absent scenarios.** Fallback (UDP parser) requires a working interface and has no auto-recovery path. A slow-polling wait state is simpler, safer, and recovers automatically.
- **JVM flags for macOS AWT suppression:** `-Djava.awt.headless=true` + `-Dapple.awt.UIElement=true` + `-Xdock:name=SCUE Bridge` are the correct flags to suppress focus-stealing and menu-bar name. They are no-ops on other platforms. Confirm with live hardware that `-Djava.awt.headless=true` doesn't interfere with beat-link's network code.
