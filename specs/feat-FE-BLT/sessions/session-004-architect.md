# Session Summary: ARCHITECT-DISCONNECT-AUDIT

## Role
Architect

## Objective
Audit the full bridge disconnect/reconnect data flow across Layer 0 (backend adapter/manager) and the frontend, define what should happen at each state transition, and produce a spec with a state transition table, interface changes, and atomized tasks for implementation.

## Status
COMPLETE

## Work Performed
- Read all backend bridge files: adapter.py, manager.py, client.py, ws.py, ws_manager.py, bridge.py, main.py
- Read all frontend bridge files: bridgeStore.ts, ws.ts, consoleStore.ts, consoleMapper.ts, network.ts
- Read all context files: CONTRACTS.md, ARCHITECTURE.md, bugs/frontend.md, test-scenarios/bridge-lifecycle.md, LEARNINGS.md
- Read all 3 prior session summaries (developer, validator, QA)
- Traced the full data flow: Java bridge → BridgeWebSocket → BridgeManager._listen_loop → BridgeAdapter → to_status_dict() → WSManager.broadcast → frontend ws.ts dispatch → bridgeStore → components
- Identified 9 gaps in the current implementation
- Assessed the crash-restart loop behavior and proposed interface pre-check fix
- Built complete state transition table (backend + frontend) covering all states and transitions
- Produced gap analysis with file:line citations
- Surfaced 3 [DECISION NEEDED] items; all 3 resolved by operator (recommendations accepted)
- Wrote spec: `specs/feat-FE-BLT/spec-disconnect-reconnect.md`
- Wrote task breakdown: `specs/feat-FE-BLT/tasks-disconnect-reconnect.md` (6 tasks, dependency graph)
- Wrote 6 handoff packets: `specs/feat-FE-BLT/handoff-TASK-001.md` through `handoff-TASK-006.md`
- Updated test scenarios: `docs/test-scenarios/bridge-lifecycle.md` with 6 new post-fix scenarios (SC-017 through SC-022)
- Updated LEARNINGS.md with 2 entries under Cross-Cutting / Workflow

## Files Changed
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — NEW: full spec with state transition table, interface definitions, edge cases
- `specs/feat-FE-BLT/tasks-disconnect-reconnect.md` — NEW: 6 atomized tasks with dependency graph, QA tags, state behavior tags
- `specs/feat-FE-BLT/handoff-TASK-001.md` — NEW: handoff for adapter clear + timestamp reset
- `specs/feat-FE-BLT/handoff-TASK-002.md` — NEW: handoff for interface pre-check in poll loop
- `specs/feat-FE-BLT/handoff-TASK-003.md` — NEW: handoff for FE query invalidation + console mapper reset
- `specs/feat-FE-BLT/handoff-TASK-004.md` — NEW: handoff for interface score fix
- `specs/feat-FE-BLT/handoff-TASK-005.md` — NEW: handoff for console log disappearance fix
- `specs/feat-FE-BLT/handoff-TASK-006.md` — NEW: handoff for Designer UX narrative
- `docs/test-scenarios/bridge-lifecycle.md` — UPDATED: added SC-017 through SC-022 (post-fix validation scenarios)
- `LEARNINGS.md` — UPDATED: 2 entries added under Cross-Cutting / Workflow
- `specs/feat-FE-BLT/sessions/session-004-architect.md` — NEW: this session summary

## Interfaces Added or Modified
None. The spec proposes internal changes only (adapter.clear() method, pioneer timestamp reset, interface pre-check). No changes to the bridge_status or pioneer_status WebSocket payload shapes. The operator approved not adding a connection_epoch field.

## Decisions Made
1. **No connection_epoch in bridge_status payload**: Clearing adapter state at the source is sufficient. Adding a connection_epoch would be unnecessary interface complexity. Alternative considered: adding connection_epoch as belt-and-suspenders — rejected because we control the adapter code and the clearing fix is definitive.

2. **Interface pre-check in waiting_for_hardware loop (Option A)**: Rather than keeping the crash-restart loop or making waiting_for_hardware permanent, the manager will check if the configured interface exists before attempting a restart. This eliminates wasted crash cycles while preserving automatic recovery. Alternative considered: Option B (don't reset _consecutive_failures, permanent wait) — rejected because it prevents automatic recovery. Option C (accept the loop) — rejected because 3 unnecessary crash cycles per 30s poll is wasteful.

3. **Query invalidation in ws.ts, not in stores**: Route/interface query invalidation on bridge reconnect belongs in the WS dispatch layer, not in bridgeStore. This keeps stores as pure state containers and avoids importing TanStack queryClient into Zustand stores. Alternative considered: putting invalidation in bridgeStore — rejected because it violates the "stores are independent silos" architecture rule.

4. **Console mapper reset on WS reconnect**: Call resetMapperState() in onOpen() so the first bridge_status after reconnect is treated as a fresh session. This may produce a "Bridge status: running" entry even if status hasn't changed, but that's a feature (clear audit trail) not a bug. Alternative considered: not resetting, accepting missed transitions — rejected because missing transitions in the console makes debugging harder.

5. **Interface score in this audit's scope**: The scoring fix is included as TASK-004 because the operator approved it and the stuck score compounds the disconnect/reconnect confusion (user sees score=5 for an active interface). Alternative considered: tracking separately — rejected by operator decision.

## Scope Violations
None. All work was read-only audit + spec/task artifact production.

## Remaining Work
None — all acceptance criteria from the handoff packet are met.

## Blocked On
None.

## Missteps
- Initially declared session COMPLETE without writing handoff packets or test scenarios. The Architect preamble (lines 169-175) explicitly lists both as required session artifacts. Operator caught the omission. Fixed by writing all 6 handoff packets and 6 new test scenarios before finalizing. Root cause: focused on the spec + tasks deliverables from the handoff packet's ACs and missed the broader artifact requirements in the role preamble.
- Failed to mark `handoff-FIX-STALE-DEVICES.md` as superseded. My 6 tasks replace the work that handoff was dispatching. The Orchestrator caught the stale artifact. Fixed by adding `## Status: SUPERSEDED` header with pointer to the replacement. Root cause: when producing new tasks that replace prior work, must explicitly mark prior artifacts as superseded.

## Learnings
- The BridgeAdapter is a long-lived singleton (created once in BridgeManager.__init__) that accumulates state across the entire server lifetime. There is no mechanism to reset it. Any state-clearing fix for crash/restart must account for this — you can't rely on the adapter being re-instantiated.
- The on_state_change callback in BridgeManager fires synchronously via a sync wrapper (_sync_state_change in main.py) that schedules an async broadcast. This means to_status_dict() is called on every state change, and whatever the adapter holds at that moment goes to the frontend. There's no "sanitize before broadcast" layer — the adapter IS the source of truth.
- The consoleMapper.ts uses module-level mutable state for diff detection. This state persists across WS reconnects because the module is never re-imported. Any reconnect-aware behavior must explicitly call resetMapperState().
