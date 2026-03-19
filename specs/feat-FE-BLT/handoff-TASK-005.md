# Handoff Packet: TASK-005 — Investigate and fix console logs disappearing on reconnect

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
Console entries from before a bridge disconnect must remain visible after the bridge reconnects. Investigate the root cause of entries disappearing and fix it.

## Role
Developer

## Scope Boundary
- Files this agent MAY read/modify:
  - `frontend/src/stores/consoleStore.ts` — verify no flush on reconnect; fix if needed
  - `frontend/src/api/ws.ts` — verify no `clearEntries()` call path on reconnect (TASK-003 will have already added `resetMapperState()` here — do not conflict)
  - `frontend/src/utils/consoleMapper.ts` — read-only context (TASK-003 adds the reset call)
  - `frontend/src/pages/` — find and inspect the Console page component
  - `frontend/src/components/` — find and inspect Console-related components
  - `docs/bugs/frontend.md` — update "Console logs disappear" entry
- Files this agent must NOT touch:
  - `scue/` — all backend files
  - `frontend/src/stores/bridgeStore.ts` — no changes needed
  - `frontend/src/api/network.ts` — no changes needed
  - `docs/CONTRACTS.md`

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `frontend/src/stores/consoleStore.ts` — full file. Key: `entries` array (ring buffer, MAX_ENTRIES=200), `clearEntries()` (line 67), `addEntry()` (line 34). Verify no external caller triggers `clearEntries()` on reconnect.
- `frontend/src/api/ws.ts` — full file. After TASK-003: `onOpen()` now calls `resetMapperState()`. Verify no `clearEntries()` call on close/open.
- `frontend/src/utils/consoleMapper.ts` — full file. After TASK-003: mapper state resets on WS reconnect. New console entries will be generated correctly. But this doesn't explain entries *disappearing*.
- `docs/bugs/frontend.md` — "[OPEN] Console logs disappear when bridge connection is reestablished" entry
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-7 (requirements)

## State Behavior
`[INLINE — simple]` — console entries are a flat list in a ring buffer. No complex state-dependent display variations.

## Constraints
- TASK-003 must be completed first — the console mapper reset may partially resolve this issue. If so, document that in the session summary and mark the fix as "resolved by TASK-003."
- If the root cause is a React component unmounting/remounting on bridge state change (e.g., conditional rendering that removes the console component from the tree), fix it by ensuring the component stays mounted OR that it reads from the persisted store on remount.
- Do NOT add `clearEntries()` calls anywhere in the reconnect flow. The store should retain entries across reconnects.
- The ring buffer (200 entries) is a separate concern — if entries are being pushed out by a flood of messages on reconnect, that's a capacity issue, not a disappearance bug. Note the distinction in your session summary.
- `npm run typecheck` must pass.

## Acceptance Criteria
- [ ] Root cause identified and documented in session summary
- [ ] Console entries from before a bridge disconnect/reconnect remain visible in the console panel
- [ ] No `clearEntries()` call triggered by WS reconnect, bridge state change, or component remount
- [ ] If the root cause is a component unmount/remount issue, the fix ensures entries survive remount
- [ ] If the root cause was already resolved by TASK-003 (mapper reset), document this and verify
- [ ] `npm run typecheck` passes
- [ ] Bug entry "[OPEN] Console logs disappear" updated in `docs/bugs/frontend.md` with root cause and fix
- [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.

## Dependencies
- Requires completion of: TASK-003 (console mapper reset may partially fix this — test after TASK-003 is in place)
- Blocks: none

## Open Questions
None.
