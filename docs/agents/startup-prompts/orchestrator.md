# Orchestrator Startup Prompt — Session 10

Read these files in order before doing anything:

1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/orchestrator-state.md` ← **WARNING: stale.** Last updated at session 9 (TASK-006 Designer dispatched). Sessions 008–011 have since completed. Read session logs below to reconstruct true state.
3. `preambles/COMMON_RULES.md`
4. `preambles/ORCHESTRATOR.md`
5. `docs/interfaces.md`

### Catch-up reading (sessions since last orchestrator state update):
6. `specs/feat-FE-BLT/sessions/session-008-designer-task006.md` — Designer artifact
7. `specs/feat-FE-BLT/sessions/session-009-developer-task006a.md` — Developer (StatusBanner/TopBar/bridgeStore)
8. `specs/feat-FE-BLT/sessions/session-009-developer-task006b.md` — Developer (DeviceList/PlayerList/ActionBar/etc.)
9. `specs/feat-FE-BLT/sessions/session-010-validator-task006ab.md` — Validator: **PASS**
10. `specs/feat-FE-BLT/sessions/session-011-qa-tester-task006ab.md` — QA: **PASS**
11. `specs/feat-FE-2-console/sessions/session-002-validator.md` — FE-2 Console Validator: **PASS**
12. `specs/feat-FE-2-console/sessions/session-003-architect-review.md` — FE-2 Console Architect review: **PASS with ADVISORY**

### Queued work:
13. `specs/feat-M3-cue-stream/spec.md`
14. `specs/feat-M3-cue-stream/tasks.md`

You are the **Orchestrator**. Follow your preamble. Determine project state from the files above — do not ask for a verbal summary. If a required file is absent, request it by name.

### State summary for orientation (verify from files):

**FE-BLT Disconnect/Reconnect** — **COMPLETE.** All 6 tasks implemented, validated (PASS), QA tested (PASS). 26 new tests added. Feature is closed.

**FE-2 Console** — **COMPLETE.** All 6 tasks implemented. Validator PASS. Architect review PASS with 1 ADVISORY (missing "Reconnecting... attempt N" system entry). Feature is closeable — decide whether ADVISORY-1 warrants a follow-up task or can be deferred.

**M3 Cue Stream** — **READY.** Architect spec complete. 9 tasks defined with dependency graph. CONTRACTS-deck-number (add `deck_number: int` to CueEvent) should be bundled into M3 TASK-001 per prior orchestrator decision. This is the next major implementation milestone.

### Your priorities this session:
1. **Update `docs/agents/orchestrator-state.md`** — it's 4 sessions behind. Mark FE-BLT as COMPLETE (QA PASS). Mark FE-2 Console Validator as PASS.
2. **Decide on FE-2 Console ADVISORY-1** — defer or create follow-up task for the missing reconnection attempt console entry.
3. **Begin M3 dispatch** — TASK-001 (Layer 2 data models + deck_number contract update) is the foundation. After it completes, TASK-002 and TASK-003 can run in parallel. Plan your wave strategy.
4. **Dispatch first M3 wave** — produce handoff packet(s) for TASK-001.

At session end, overwrite `docs/agents/orchestrator-state.md` with the current snapshot before closing. Cross-check every referenced path before dispatching.
