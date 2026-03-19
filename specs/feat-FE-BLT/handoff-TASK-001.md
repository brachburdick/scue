# Handoff Packet: TASK-001 — Clear adapter state on crash/restart and reset pioneer timestamp

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
After a bridge crash or restart, `to_status_dict()` must return empty devices/players until fresh data arrives from the new bridge session. `pioneer_status.is_receiving` must be `false` until fresh Pioneer traffic arrives.

## Role
Developer

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/bridge/adapter.py` — add `clear()` method
  - `scue/bridge/manager.py` — call `adapter.clear()` in `_cleanup()` and `start()`; reset `_last_pioneer_message_time` in `start()`
  - `tests/test_bridge/` — add/update tests for new behavior
  - `docs/bugs/frontend.md` — update "[PARTIAL] Devices and players show stale data after hardware disconnect" entry
- Files this agent must NOT touch:
  - `scue/api/*.py` — API layer (consumed by other tasks)
  - `frontend/` — all frontend files
  - `scue/bridge/client.py` — WebSocket client (no changes needed)
  - `scue/bridge/messages.py` — message types (no changes needed)
  - `docs/CONTRACTS.md` — propose changes via [INTERFACE IMPACT] flag, don't edit directly

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `scue/bridge/adapter.py` — full file. Key: `_devices` (line 122), `_players` (line 123). No `clear()` method exists.
- `scue/bridge/manager.py` — full file. Key: `_cleanup()` (line 580), `start()` (line 155, note existing `_last_message_time = 0.0` at line 160), `to_status_dict()` (line 614, reads `self._adapter.devices` and `self._adapter.players`)
- `scue/api/ws.py` — read-only context. `_build_pioneer_status()` (line 54) reads `_last_pioneer_message_time` to compute `is_receiving`. Understand how the timestamp reset affects this.
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-1 and TR-2 (full requirements)
- `specs/feat-FE-BLT/sessions/session-003-qa-tester.md` — QA failure details showing stale data reappearing on reconnect
- `specs/feat-FE-BLT/sessions/session-004-architect.md` — Architect audit findings
- `LEARNINGS.md` — "BridgeAdapter is a long-lived singleton" entry (bottom of Cross-Cutting section)

## State Behavior
N/A — backend only, no UI components affected directly.

## Constraints
- The `BridgeAdapter` is instantiated once in `BridgeManager.__init__()` (line 94) and is never re-created. Your fix must work with this singleton pattern — do NOT re-instantiate the adapter.
- `clear()` must only reset `_devices` and `_players`. Do NOT reset callbacks (`on_device_change`, `on_player_update`, etc.) — those are wired once at startup in `main.py` (lines 106-107) and must survive across restarts.
- Call `adapter.clear()` in BOTH `_cleanup()` AND `start()` for defense-in-depth. `_cleanup()` is the primary path (runs on every crash/stop); `start()` is belt-and-suspenders.
- Do not modify the `to_status_dict()` return shape — no new fields, no removed fields.
- All pre-existing tests must continue to pass.

## Acceptance Criteria
- [ ] `BridgeAdapter.clear()` method exists, resets `_devices = {}` and `_players = {}`
- [ ] `BridgeAdapter.clear()` does NOT reset callbacks, `bridge_connected`, or `bridge_version`
- [ ] `BridgeManager._cleanup()` calls `self._adapter.clear()`
- [ ] `BridgeManager.start()` calls `self._adapter.clear()` before `self._status = "starting"` (after the existing `_last_message_time = 0.0` line)
- [ ] `BridgeManager.start()` sets `self._last_pioneer_message_time = 0.0` (alongside existing `_last_message_time = 0.0`)
- [ ] After crash → restart, `to_status_dict()` returns `devices={}`, `players={}` until fresh `device_found`/`player_status` messages arrive
- [ ] After restart, `pioneer_status.is_receiving` is `false` until fresh Pioneer traffic arrives (no false-positive from stale `_last_pioneer_message_time`)
- [ ] All pre-existing tests pass (`python -m pytest tests/test_bridge/`)
- [ ] Bug entry "[PARTIAL] Devices and players show stale data after hardware disconnect" in `docs/bugs/frontend.md` updated to reflect backend fix
- [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.

## Dependencies
- Requires completion of: none
- Blocks: TASK-002 (same file, must not conflict), TASK-006 (UX work needs backend fixes in place)

## Open Questions
None — all decisions resolved by operator in Architect session.
