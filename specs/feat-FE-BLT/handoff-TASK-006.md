# Handoff Packet: TASK-006 — [REQUIRES DESIGNER] Disconnect/reconnect UX narrative

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DESIGNER.md`

## Objective
Produce a UI State Behavior artifact defining what the Bridge page shows during each phase of the disconnect/reconnect lifecycle. The user must always know what's happening and what to expect. This addresses the operator feedback: "WAY too slow, needs better visual indication of what's actually happening."

## Role
Designer (produces UI State Behavior artifact) → then Developer (implements it)

## Scope Boundary
- Files this agent MAY read (Designer is read-only):
  - `frontend/src/components/bridge/*.tsx` — all bridge page components
  - `frontend/src/components/layout/TopBar.tsx` — StatusDot, TrafficDot, StartupIndicator
  - `frontend/src/stores/bridgeStore.ts` — state shape and computed values
  - `frontend/src/pages/BridgePage.tsx` — page layout
  - `frontend/CLAUDE.md` — frontend conventions
- Files this agent must NOT modify:
  - All source code files (Designer is read-only; Developer phase follows separately)

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DESIGNER.md`
- `templates/ui-state-behavior.md` — use this template for the artifact
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — state transition table (reference for all states and transitions)
- `specs/feat-FE-BLT/tasks-disconnect-reconnect.md` — state transition table at bottom of file
- `frontend/src/stores/bridgeStore.ts` — current state shape: `status`, `dotStatus`, `isStartingUp`, `devices`, `players`, `restartCount`, `nextRetryInS`, `isReceiving`, `bridgeConnected`
- `frontend/src/components/layout/TopBar.tsx` — StatusDot (green/yellow/red), TrafficDot (cyan pulse), StartupIndicator (spinning pill)
- `frontend/CLAUDE.md` — TopBar components section, bridgeStore patterns, Bridge page layout
- `docs/bugs/frontend.md` — "[OPEN] Hardware disconnect/reconnect flow is too slow with poor visual feedback" entry
- `docs/test-scenarios/bridge-lifecycle.md` — SC-001 through SC-016 for the full range of disconnect/reconnect scenarios

## State Behavior
This IS the state behavior task. The Designer produces the authoritative `ui-state-behavior.md` artifact covering:

**Components to define behavior for:**
1. TopBar StatusDot (green/yellow/red circle)
2. TopBar TrafficDot (cyan pulse indicator)
3. BridgeStatusPanel status banner (text + icon)
4. DeviceList (device cards or empty state)
5. PlayerList (player cards or empty state)
6. HardwareSelectionPanel (interface list + route banner + action bar)

**System states to cover:**
1. `running` — healthy, hardware present, traffic flowing
2. `running` — no hardware, empty devices, no traffic
3. `crashed` — with restart countdown (1st, 2nd failure)
4. `starting` — subprocess launching
5. `waiting_for_hardware` — crash threshold reached, slow polling with countdown
6. `running` — recovering (just reconnected, fresh data arriving)
7. WS disconnected — backend unreachable

**Key UX questions for the Designer:**
- What transitional feedback does the user see during crash → restart → running? (Currently: nothing for ~20s, then a brief green flash, then back to red.)
- Should `waiting_for_hardware` show a countdown to the next poll attempt? (`nextRetryInS` is available in the store.)
- Should the status banner show a narrative text describing what's happening? (e.g., "Bridge crashed. Restarting in 4s...", "Waiting for hardware. Checking in 28s...")
- How should the "recovering" state (just reconnected, data arriving) differ from steady-state "running"?

## Constraints
- The Designer produces an artifact only — no code changes. Implementation is a separate Developer task.
- The UI State Behavior artifact must use `templates/ui-state-behavior.md`.
- All state data referenced in the artifact must already exist in `bridgeStore` (or be derivable from existing fields). If new derived state is needed, note it as `[NEW DERIVED STATE]` with the computation.
- FE state behavior is a product decision — the Designer should present options to Brach where there's ambiguity, not infer behavior.

## Acceptance Criteria
- [ ] UI State Behavior artifact produced using `templates/ui-state-behavior.md`
- [ ] All 7 system states covered for all 6 components
- [ ] Transitional feedback defined for crash → restart → running sequence
- [ ] `waiting_for_hardware` behavior includes countdown/progress indication
- [ ] Status banner narrative text defined for each state
- [ ] Any new derived state clearly marked with `[NEW DERIVED STATE]`
- [ ] Options presented to Brach for any ambiguous UX decisions
- [ ] Artifact written to `specs/feat-FE-BLT/ui-state-behavior-disconnect.md`

## Dependencies
- Requires completion of: TASK-001 + TASK-002 + TASK-003 (backend and FE-state fixes must be in place so the Designer works from correct state behavior — stale data is gone, crash loop is reduced, queries auto-refresh)
- Blocks: Developer implementation of the UX changes

## Open Questions
None for the Architect. The Designer will surface UX questions to Brach per protocol.
