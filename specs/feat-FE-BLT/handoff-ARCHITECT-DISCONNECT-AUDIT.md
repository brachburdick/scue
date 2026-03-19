# Handoff Packet: ARCHITECT-DISCONNECT-AUDIT

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/ARCHITECT.md`

## Objective
Audit the full bridge disconnect/reconnect data flow across Layer 0 (backend adapter/manager) and the frontend, define what *should* happen at each state transition, and produce a spec with a state transition table, interface changes, and atomized tasks for implementation.

## Role
Architect

## Scope Boundary
- Files this agent MAY read:
  - `scue/bridge/adapter.py` — stateful adapter, `_devices`/`_players` dicts, `to_status_dict()`
  - `scue/bridge/manager.py` — subprocess lifecycle, crash detection, restart logic, state transitions
  - `scue/bridge/client.py` — WebSocket client, reconnection handling
  - `scue/bridge/messages.py` — BridgeMessage dataclass, payload types
  - `scue/api/ws.py` — WebSocket broadcasting, pioneer_status watchdog
  - `scue/api/bridge.py` — bridge status endpoint
  - `frontend/src/stores/bridgeStore.ts` — frontend bridge state management
  - `frontend/src/api/ws.ts` — WebSocket client, dispatch logic
  - `frontend/src/components/bridge/*.tsx` — all bridge page components
  - `frontend/src/components/layout/TopBar.tsx` — StatusDot, TrafficDot
  - `docs/CONTRACTS.md` — current interface contracts
  - `docs/ARCHITECTURE.md` — layer definitions
  - `docs/bugs/frontend.md` — full bug history
  - `docs/test-scenarios/bridge-lifecycle.md` — existing test scenarios
  - `specs/feat-FE-BLT/sessions/*.md` — all session summaries for this feature
  - `LEARNINGS.md` — known pitfalls
- Files this agent must NOT modify:
  - Any source code (`.py`, `.ts`, `.tsx`, `.java`)
  - `docs/CONTRACTS.md` (propose changes in spec, don't apply)

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/ARCHITECT.md`
- `docs/CONTRACTS.md` — current WebSocket message schemas (`bridge_status`, `pioneer_status`)
- `docs/ARCHITECTURE.md` — Layer 0 definition
- `docs/bugs/frontend.md` — all open and partial bugs (read the full file)
- `docs/test-scenarios/bridge-lifecycle.md` — existing scenarios
- `LEARNINGS.md` — bridge crash-restart lifecycle context
- `specs/feat-FE-BLT/sessions/session-001-developer.md` — FIX-STALE-DEVICES Developer session
- `specs/feat-FE-BLT/sessions/session-002-validator.md` — FIX-STALE-DEVICES Validator verdict
- `specs/feat-FE-BLT/sessions/session-003-qa-tester.md` — FIX-STALE-DEVICES QA verdict (FAIL)

## State Behavior
This is the core deliverable. The Architect must define a complete state transition table for the disconnect/reconnect flow, covering:
- What states exist (backend adapter, manager, frontend store)
- What triggers each transition
- What the backend sends at each transition (exact `bridge_status` payload changes)
- What the frontend should display at each transition
- Where the current implementation diverges from the correct behavior

## Constraints
- Read-only. Do not modify source code.
- This is an audit + spec, not implementation. Output is a spec document + task breakdown.
- Propose interface changes in the spec; do not apply them to `docs/CONTRACTS.md` directly.
- The bridge crash-restart loop (every ~2 min when hardware is off) is a backend concern. Assess whether the manager should settle into a stable `waiting_for_hardware` state instead of looping.
- Flag any `[DECISION NEEDED]` items for the operator before finalizing tasks.
- Tag each task with `QA Required:` and `State Behavior:` per protocol.
- Mark any frontend state-behavior decisions that need Designer input as `[REQUIRES DESIGNER]`.

## Acceptance Criteria
- [ ] Complete state transition table for the disconnect/reconnect flow (backend + frontend)
- [ ] Gap analysis: where current implementation diverges from correct behavior (cite file + line)
- [ ] Proposed interface changes to `bridge_status` and/or `pioneer_status` payloads (if any)
- [ ] Assessment of the crash-restart loop: should the manager settle into a stable state when hardware is absent?
- [ ] Atomized task breakdown with dependency graph, one task per layer boundary
- [ ] Each task tagged with `QA Required:` and `State Behavior:`
- [ ] Frontend tasks flagged `[REQUIRES DESIGNER]` if state-dependent display has ≥3 components or ≥4 distinct states
- [ ] All `[DECISION NEEDED]` items surfaced — no inferred defaults
- [ ] Session summary written to `specs/feat-FE-BLT/sessions/`
- [ ] Spec written to `specs/feat-FE-BLT/spec-disconnect-reconnect.md`
- [ ] Tasks written to `specs/feat-FE-BLT/tasks-disconnect-reconnect.md`

## Dependencies
- Requires completion of: none
- Blocks: all implementation work on disconnect/reconnect bugs

## Open Questions
None — the Architect is expected to surface questions via `[DECISION NEEDED]` tags during the audit.
