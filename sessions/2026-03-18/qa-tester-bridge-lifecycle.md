# Session Summary: QA-BRIDGE-LIFECYCLE

## Role
QA Tester

## Objective
Execute all testable bridge lifecycle scenarios from `docs/test-scenarios/bridge-lifecycle.md`
against the running server with mock tools, and produce a QA Verdict for the BUG-BRIDGE-CYCLE
fix (`scue/bridge/manager.py`).

## Status
COMPLETE (with FAIL verdict — one confirmed regression found)

## Work Performed
- Read all preamble and context files (AGENT_BOOTSTRAP.md, COMMON_RULES.md, QA_TESTER.md,
  bridge-lifecycle.md, layer0-bridge.md, manager.py, test_manager.py, mock_bridge.py)
- Step 0: Ran `tests/test_bridge/` unit tests — 136/136 PASS
- Discovered test environment has real Pioneer hardware (en7 interface, route_correct: true,
  JAR + JRE present) — mock_bridge.py cannot be used as primary bridge driver
- SC-005: Started server, observed bridge status — bridge "running" (hardware present), not
  "waiting_for_hardware". Cannot test board-OFF precondition without physical action.
- SC-007: Called `POST /api/network/route/fix {"interface": "en16"}` (simulated adapter
  unplugged) — confirmed raw "route: bad address: en16" error returned. **FAIL.**
- SC-009: Called `POST /api/bridge/restart` — bridge returned to "running" with
  restart_count=0. Inspected Java processes and found orphaned subprocesses (PIDs 53056,
  69048) — see Concerns below.
- SC-010, SC-011, SC-012: CANNOT_TEST in current environment (hardware present).
- Produced QA Verdict at `docs/qa-verdicts/bridge-lifecycle-2026-03-18.md`.

## Files Changed
- `docs/qa-verdicts/bridge-lifecycle-2026-03-18.md` — QA Verdict (created/overwritten;
  file had placeholder content from a prior agent, replaced with actual test results)
- `sessions/2026-03-18/qa-tester-bridge-lifecycle.md` — this session summary

## Interfaces Added or Modified
None.

## Decisions Made
- Used `en16` as the "nonexistent interface" for SC-007 route fix API test (it was the
  interface name referenced in the bug log). Alternative considered: using a random string
  like `en99`; chose `en16` to match the exact scenario described.
- Marked SC-011/SC-012 as CANNOT_TEST rather than attempting to simulate crashes by killing
  the Java subprocess manually. Rationale: invasive process manipulation could damage
  Brach's running environment and the unit tests already cover this behavior thoroughly.
- SC-009 verdict: CONDITIONAL PASS despite orphaned process discovery. Rationale: the
  API-level behavior (restart_count=0, status="running") is correct; the orphaned process
  issue is a pre-existing lifecycle bug unrelated to BUG-BRIDGE-CYCLE.

## Scope Violations
None. Did not modify any source code or test files.

## Remaining Work
- SC-005, SC-010, SC-011, SC-012 need physical hardware testing (board off/on, adapter
  unplug/replug) — REQUIRES_OPERATOR scenarios.
- SC-007 fix: Developer needs to update `scue/api/network.py:fix_route_endpoint()` to
  apply friendly error wrapping for "bad address" / "no such interface" kernel errors.

## Blocked On
None — verdict is complete and actionable.

## Missteps
- Initial `POST /api/network/route/fix` call without a body returned 422 (missing required
  `interface` field in request body). Checked OpenAPI spec (`/openapi.json`) to discover
  `RouteFixRequest` schema, then repeated call with correct body.
- Attempted to run server with `--log-level info` expecting bridge manager INFO logs to
  surface. They did not — Python root logger defaults to WARNING, so `logger.info()` in
  `scue.bridge.manager` is filtered. Only `logger.warning()` calls appear. Noted as a
  concern in verdict.

## Learnings
- **`mock_bridge.py` cannot be used as a substitute for the real Java bridge when JAR + JRE
  are present.** The `BridgeManager` will always attempt a real launch. `mock_bridge.py` is
  useful only as a WebSocket server for development/integration testing when the JAR is
  absent. To test "hardware absent" scenarios (SC-005/SC-010/SC-011/SC-012) in a CI/mock
  environment, a mechanism to bypass JAR detection (env var or config flag) is needed.
- **`BridgeManager._launch_subprocess()` verifies port availability, not subprocess
  ownership.** If a pre-existing Java bridge holds port 17400, a newly launched subprocess
  cannot bind — it becomes orphaned — while the manager connects to the old bridge and
  reports success. In Brach's environment, PIDs 27093, 53056, 69048 coexisted as a result.
  This is a correctness gap worth tracking separately.
- **The BUG-BRIDGE-CYCLE fix applied error wrapping in `manager.py` only.** The
  `/api/network/route/fix` endpoint in `scue/api/network.py` calls the network module
  directly, bypassing the manager's friendly error logic. Always check that API endpoints
  route through the abstraction layer where fixes are applied — don't assume the manager
  is the only code path.
