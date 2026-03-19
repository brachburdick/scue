# Handoff Packet: TASK-FE-2-CONSOLE-IMPL

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
The FE-2 Console panel is fully functional: log entries from existing WebSocket messages display in a scrollable panel with Clean/Verbose mode toggle, record-to-file capability, and clear button.

## Role
Developer (FE-State + FE-UI, combined — all 6 tasks are frontend-only)

## Scope Boundary
- Files this agent MAY create:
  - `frontend/src/types/console.ts`
  - `frontend/src/stores/consoleStore.ts`
  - `frontend/src/utils/consoleMapper.ts`
  - `frontend/src/utils/consoleExport.ts`
  - `frontend/src/components/layout/ConsoleHeader.tsx`
  - `frontend/src/components/layout/ConsolePanel.tsx`
  - `frontend/src/components/layout/LogEntry.tsx`
- Files this agent MAY modify:
  - `frontend/src/types/index.ts` (re-export console types)
  - `frontend/src/api/ws.ts` (add console dispatch)
  - `frontend/src/components/layout/Console.tsx` (compose new components)
- Files this agent must NOT touch:
  - Any Python backend files
  - Any files outside `frontend/src/`
  - `docs/CONTRACTS.md`
  - Any store other than `consoleStore` (store independence rule)

## Context Files
- `specs/feat-FE-2-console/spec.md` — **PRIMARY REFERENCE** — full design spec with state model, component hierarchy, log entry format, mode toggle behavior, record mode flow, visual hierarchy, edge cases
- `specs/feat-FE-2-console/tasks.md` — task breakdown with acceptance criteria per task
- `docs/CONTRACTS.md` — bridge_status and pioneer_status WS payload schemas
- `frontend/src/stores/bridgeStore.ts` — reference for Zustand store pattern
- `frontend/src/api/ws.ts` — existing WS dispatch logic (where console dispatch will be added)
- `frontend/src/components/layout/Console.tsx` — existing console placeholder to refactor
- `LEARNINGS.md` — known pitfalls

## Task Sequence
Execute these in order (dependencies are sequential):

1. **TASK-001:** Create `consoleStore` + types (`consoleStore.ts`, `types/console.ts`, update `types/index.ts`)
2. **TASK-002:** Create `consoleMapper` utility (`utils/consoleMapper.ts`)
3. **TASK-003:** Wire mapper into `ws.ts` dispatch
4. **TASK-004:** Build `ConsoleHeader` with mode toggle, record button, clear button
5. **TASK-005:** Build `LogEntry` + `ConsolePanel` (scrollable log area with auto-scroll)
6. **TASK-006:** Implement record stop + `.log` file export (`utils/consoleExport.ts`)

After TASK-001, tasks 002+003 and 004+005 are independent of each other, but within a single agent the sequential order above is fine.

## Constraints
- **Store independence:** `consoleStore` must not import from any other store.
- **No new WS message types:** Console sources from existing `bridge_status` and `pioneer_status` messages only.
- **No backend changes:** All work is frontend-only.
- **Render-time filtering:** Clean/Verbose filtering happens at render time via the `verbose` boolean on entries. Do NOT filter at insertion time.
- **Record captures all entries:** `addEntry` appends to `recordBuffer` regardless of current `verboseMode`.
- **Ring buffer max 200 entries.**
- **Absolute timestamps:** Display as `HH:MM:SS.mmm`, export as ISO 8601.
- **All pre-existing tests must continue to pass.**

## Acceptance Criteria
- [ ] `consoleStore` with ring buffer (200 cap), recording state, all actions per spec
- [ ] `consoleMapper` with diff detection for Clean mode entries, verbose entries for every message
- [ ] `ws.ts` dispatches to both existing stores AND consoleStore via mapper
- [ ] System entries for WS connect/disconnect
- [ ] `ConsoleHeader` with mode toggle, record button (idle/recording/saving states), clear button
- [ ] `LogEntry` component with timestamp (HH:MM:SS.mmm), source badge (BRG/PIO/SYS), severity dot, message
- [ ] `ConsolePanel` with auto-scroll (pause when user scrolls up, resume at bottom)
- [ ] Clean mode shows only `verbose === false` entries; Verbose shows all
- [ ] Record mode: start → accumulate → stop → export to `.log` file with ISO timestamps
- [ ] Empty state: "No console entries yet."
- [ ] Pulsing red indicator visible even when console is collapsed
- [ ] `npm run typecheck` passes with zero errors
- [ ] All pre-existing tests pass
- [ ] **AC — Interface Impact:** No new WS fields or backend contracts introduced. If any interface changes are needed, flag `[INTERFACE IMPACT]` and stop.

## Dependencies
- Requires completion of: FE-bridge-waiting-state (COMPLETE), CONTRACTS-waitingforhw (COMPLETE)
- Blocks: Validator session for FE-2-console

## Open Questions
None — the spec is fully defined in `specs/feat-FE-2-console/spec.md`. If you encounter an ambiguity, check the spec first. If still unclear, flag `[BLOCKED]` and proceed with the rest.
