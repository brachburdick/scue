# Handoff Packet: FIX-LAST-MESSAGE-TIME

## Objective
`BridgeManager.start()` must reset `self._last_message_time = 0.0` before launching the
subprocess, so the health check silence condition cannot fire against a stale timestamp
from a previous bridge run.

## Role
Developer (Bridge / L0)

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/bridge/manager.py` — add one line in `start()` before `_launch_subprocess()`
  - `tests/test_bridge/test_manager.py` — add regression test
- Files this agent must NOT touch:
  - `scue/api/network.py` — a separate fix is running in parallel on this file; do NOT touch it
  - `scue/network/route.py`
  - `scue/bridge/adapter.py`, `scue/bridge/messages.py`
  - Any frontend files
  - Any other test files

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `docs/bugs/layer0-bridge.md` — see the BUG-BRIDGE-CYCLE entry; 6th root cause addendum at bottom
- `docs/qa-verdicts/bridge-lifecycle-2026-03-18.md` — see FAIL-1 section for full diagnosis
- `LEARNINGS.md` — read before starting

## Background
The BUG-BRIDGE-CYCLE fix (2026-03-18) correctly addressed 5 root causes, but QA live hardware
testing (2026-03-18 evening) revealed a 6th: `_last_message_time` is never reset in `start()`.

**How the crash cycle reoccurs:**
1. Bridge runs, sets `_last_message_time` to a real timestamp (e.g., `T=1000.0`)
2. Hardware disconnects → Java subprocess crashes
3. `start()` is called (via `_schedule_restart()` or slow-poll)
4. `_last_message_time` is still `1000.0` — NOT reset
5. Health check guard: `if self._last_message_time > 0` → **True**
6. Health check calculates silence duration: `now - 1000.0` → already stale by 20s+
7. Health check fires a restart before beat-link has time to connect
8. Repeat → crash cycle

**Why SC-005 (cold start) passes without this fix:**
- At process start, `_last_message_time = 0.0` (class default)
- Health check guard: `if self._last_message_time > 0` → **False**
- Health check never fires → bridge stays stable

**The fix:** One line, added at the top of `start()` before `_launch_subprocess()`:
```python
self._last_message_time = 0.0
```

This gives every new subprocess launch a clean health check window identical to cold start.

## Constraints
- Do NOT change health check logic, timing constants, or any other part of `_health_check_loop`.
- Do NOT change `_schedule_restart()`, `_enter_waiting_for_hardware()`, or any other method.
- The fix is one line in one method. If you find yourself changing more, stop and flag it.
- All pre-existing tests must continue to pass.
- Type hints required on any modified function signatures.
- No print() — use logging module.
- Do NOT touch `scue/api/network.py` — a parallel fix is running there.

## Acceptance Criteria
- [ ] `BridgeManager.start()` resets `self._last_message_time = 0.0` before calling
      `_launch_subprocess()`.
- [ ] Regression test in `tests/test_bridge/test_manager.py`: simulate a bridge that has
      previously run (set `manager._last_message_time` to a non-zero value), call `start()`,
      assert `manager._last_message_time == 0.0` immediately after the call (before any
      WebSocket messages arrive).
- [ ] All 136 pre-existing tests pass.
- [ ] No changes to any file outside the scope boundary.

## Dependencies
- Requires completion of: none
- Runs in parallel with: FIX-SC007-ROUTE-API (different files, no conflict)
- Blocks: QA re-test of SC-001, SC-002, SC-003, SC-004, SC-010 (live hardware)

## Open Questions
None. The fix is a single line; the exact insertion point is the top of `start()` before
`_launch_subprocess()`.
