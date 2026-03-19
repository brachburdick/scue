# Handoff Packet: TASK-002 — Interface pre-check in waiting_for_hardware poll loop

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
When the bridge is in `waiting_for_hardware` state and the slow-poll fires, the manager must check if the configured network interface exists before attempting `start()`. If the interface is unavailable, skip the restart attempt and continue polling — eliminating wasted crash cycles.

## Role
Developer

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/bridge/manager.py` — modify `_wait_for_hardware_loop()`
  - `tests/test_bridge/` — add/update tests for new behavior
- Files this agent must NOT touch:
  - `scue/bridge/adapter.py` — modified by TASK-001
  - `scue/api/*.py` — API layer
  - `frontend/` — all frontend files
  - `docs/CONTRACTS.md` — propose changes via flag, don't edit directly

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `scue/bridge/manager.py` — full file. Key: `_wait_for_hardware_loop()` (line 515), `_network_interface` property. Note that TASK-001 adds `adapter.clear()` and `_last_pioneer_message_time` reset in `start()` — your changes must coexist.
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-3 (full requirements + code sketch)
- `docs/test-scenarios/bridge-lifecycle.md` — SC-001, SC-002, SC-010 (adapter unplug scenarios showing the crash-restart loop behavior)
- `LEARNINGS.md` — "_last_message_time not reset in start()" entry for context on the crash cycle

## State Behavior
N/A — backend only, no UI components affected directly.

## Constraints
- Use `socket.if_nametoindex()` (stdlib, no new dependencies) to check interface existence. It raises `OSError` if the interface doesn't exist.
- When `_network_interface` is `None` (auto-detect mode), skip the pre-check entirely and call `start()` as before — auto-detect mode doesn't have a specific interface to verify.
- Log skipped attempts at `debug` level, not `info` or `warning` — these are expected during hardware-absent periods and should not spam logs.
- Do not change the poll interval (`_HARDWARE_POLL_INTERVAL_S = 30.0`).
- All pre-existing tests must continue to pass.

## Acceptance Criteria
- [ ] `_wait_for_hardware_loop()` checks interface availability via `socket.if_nametoindex(self._network_interface)` before calling `start()`
- [ ] When interface is unavailable (OSError): logs at debug level with interface name, skips this poll cycle via `continue`, remains in `waiting_for_hardware`
- [ ] When interface is available: calls `start()` as before
- [ ] When `self._network_interface is None`: skips the check, calls `start()` as before
- [ ] No crash-restart cycles occur when hardware is off and interface is missing — bridge stays in `waiting_for_hardware` with zero subprocess launches
- [ ] When interface reappears (adapter re-plugged), next poll cycle detects it and calls `start()` — bridge recovers automatically
- [ ] `import socket` is added at the top of the file (if not already present)
- [ ] All pre-existing tests pass (`python -m pytest tests/test_bridge/`)
- [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.

## Dependencies
- Requires completion of: TASK-001 (same file — `start()` changes must be in place)
- Blocks: TASK-006 (UX work needs backend fixes in place)

## Open Questions
None — all decisions resolved by operator in Architect session.
