# Handoff Packet: FIX-STALE-DEVICES

## Status: SUPERSEDED

> This handoff is superseded by `specs/feat-FE-BLT/handoff-TASK-001.md` (and the broader 6-task breakdown in `tasks-disconnect-reconnect.md`). The frontend-only fix produced by this handoff (session-001-developer) passed Validator but failed QA — the backend adapter root cause was out of scope. The Architect audit (session-004-architect) addresses the full data flow. Do not dispatch this handoff.

---

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
When Pioneer hardware disconnects (adapter unplugged, board powered off) or the bridge enters a non-running state, the DeviceList and PlayerList components must clear stale device/player data and show an empty state — not continue displaying last-known values.

## Role
Developer (FE-State)

## Scope Boundary
- Files this agent MAY read/modify:
  - `frontend/src/stores/bridgeStore.ts`
  - `frontend/src/components/bridge/DeviceList.tsx`
  - `frontend/src/components/bridge/PlayerList.tsx` (or wherever player cards are rendered)
  - `frontend/src/types/bridge.ts` (if type changes needed)
  - `docs/bugs/frontend.md` (to update bug entry on fix)
- Files this agent must NOT touch:
  - `scue/**` (no backend changes)
  - `frontend/src/api/ws.ts` (WebSocket client)
  - `frontend/src/components/bridge/StatusBanner.tsx`
  - `frontend/src/components/bridge/HardwareSelectionPanel.tsx`
  - `docs/CONTRACTS.md`

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `docs/CONTRACTS.md` — WebSocket message schemas (`bridge_status`, `pioneer_status`)
- `docs/bugs/frontend.md` — bug entry: "Devices and players show stale data after hardware disconnect"
- `LEARNINGS.md` — bridge crash-restart lifecycle context

## State Behavior

### Component: DeviceList

| System State | Expected Display | Notes |
|---|---|---|
| Bridge connected, hardware present (traffic flowing) | Live device cards with name, IP, type, device number | Normal operation |
| Bridge connected, hardware absent (no traffic, `is_receiving` false for >8s) | Empty state: "No Pioneer devices detected." with contextual sub-text (route-aware, per existing logic) | Clear all device cards. Use existing `recentTraffic` grace window logic. |
| Bridge disconnected (`status` not `"running"`) | Empty state: "No Pioneer devices detected." | Same empty state as hardware-absent. StatusBanner handles bridge context separately. |
| Bridge `waiting_for_hardware` mode | Empty state: "No Pioneer devices detected." | Same as above. |
| Bridge reconnecting (restart in progress) | Empty state: "No Pioneer devices detected." | Do not show stale data during restart. |

### Component: PlayerList

| System State | Expected Display | Notes |
|---|---|---|
| Bridge connected, hardware present, players active | Live player cards with BPM, pitch, playback state, on-air status | Normal operation |
| Bridge connected, hardware absent | Empty state: "No active players." | Clear all player cards. |
| Bridge disconnected | Empty state: "No active players." | Same as hardware-absent. |
| Bridge `waiting_for_hardware` mode | Empty state: "No active players." | Same as above. |
| Bridge reconnecting | Empty state: "No active players." | Do not show stale data during restart. |

## Constraints
- Do NOT add backend changes. This is a frontend-only fix.
- The bridge already emits `bridge_status` messages with `devices: {}` and `players: {}` during non-running states and hardware-absent states. The store likely retains stale data because it only *merges* incoming data rather than *replacing* it. Verify this assumption by reading the store code.
- Preserve the existing `recentTraffic` grace window in DeviceList (8s threshold). Do not introduce flicker on momentary traffic gaps.
- The `devices` and `players` fields in the `bridge_status` WebSocket payload reflect the bridge's current knowledge. When hardware disconnects, these fields should eventually be empty (`{}`). If the store is not clearing when these fields arrive empty, that's the bug.
- Do not modify the StatusBanner or any bridge-level status display — those are out of scope.
- All pre-existing tests must continue to pass.

## Acceptance Criteria
- [ ] When Pioneer hardware disconnects (adapter unplugged), DeviceList clears to "No Pioneer devices detected" within a reasonable time (seconds, not minutes)
- [ ] When Pioneer hardware disconnects, PlayerList clears to "No active players" within a reasonable time
- [ ] When bridge enters `waiting_for_hardware` mode, both components show empty state
- [ ] When bridge status is `disconnected`, both components show empty state
- [ ] When hardware reconnects, devices and players repopulate from fresh `bridge_status` data
- [ ] No flicker on momentary traffic gaps (existing grace window preserved)
- [ ] All pre-existing tests pass (`cd frontend && npm run typecheck`)
- [ ] Bug entry in `docs/bugs/frontend.md` updated with root cause, fix, and file(s)
- [ ] **AC — Interface Impact:** If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` — or flag `[INTERFACE IMPACT]` in the session summary and stop. Do not silently defer.

## Dependencies
- Requires completion of: none (protocol blocker PROTOCOL-PIPELINE-FE resolved 2026-03-19)
- Blocks: none (non-blocker bug fix)

## Open Questions
None — all state-behavior decisions resolved with operator.
