# Orchestrator State Snapshot

**Last updated:** 2026-03-19 (session 8) — FIX-STALE-DEVICES handoff generated. Protocol blocker resolved.

<!-- This file is written at the end of every Orchestrator session and read at the start. -->
<!-- If this file is absent or stale, request it by name before proceeding. -->

## Active Milestone
**M3 (Cue Stream, Layer 2)** — Architect spec complete at `specs/feat-M3-cue-stream/`. 9 implementation tasks ready. One contract change pending (`deck_number` field on CueEvent).
**FE-2 (Console)** — COMPLETE. All 6 tasks implemented. Needs Validator.

## Task Status
| Task ID | Status | Notes |
|---------|--------|-------|
| BUG-BRIDGE-CYCLE | **COMPLETE** | 6 root causes fixed. QA verified. |
| FE-bridge-waiting-state | **COMPLETE** | Validator PASS. |
| CONTRACTS-waitingforhw | **COMPLETE** | CONTRACTS.md updated. |
| FE-2-console-design | **COMPLETE** | Designer spec at `specs/feat-FE-2-console/`. |
| FE-2-console-impl | **COMPLETE** | All 6 tasks. Needs Validator. |
| DEVELOPER-md-mock-tip | **COMPLETE** | Inline fix. |
| M3-spec | **COMPLETE** | 9 atomized tasks at `specs/feat-M3-cue-stream/`. |
| VALIDATOR-fe-waiting | **COMPLETE** | PASS. |
| FIX-LAST-MESSAGE-TIME | **COMPLETE** | Validator PASS. Merged into BUG-BRIDGE-CYCLE. |
| FIX-SC007-ROUTE-API | **COMPLETE** | Validator PASS. Merged into BUG-BRIDGE-CYCLE. |
| PROTOCOL-PIPELINE-FE | **COMPLETE** | Protocol review applied 2026-03-19. Changes in COMMON_RULES, ORCHESTRATOR, DEVELOPER, DESIGNER preambles + templates. |
| FIX-STALE-DEVICES | **READY** | Handoff generated at `specs/feat-FE-BLT/handoff-FIX-STALE-DEVICES.md`. State behavior defined with operator. Ready for Developer dispatch. |
| VALIDATOR-fe-2-console | PENDING | Required per protocol. |
| CONTRACTS-deck-number | PENDING | Add `deck_number: int` to CueEvent. Bundle into M3 TASK-001. |
| M3-TASK-001 through M3-TASK-009 | PENDING | Full dependency chain in previous state snapshots. |

## Open Blockers
None.

## Open FE Bugs (non-blockers, logged, no fix scheduled)
See `docs/bugs/frontend.md` for full entries:
1. Route mismatch warning doesn't auto-clear on reconnect
2. Interface score stays at 5 for active en7 interface
3. ~~Devices and players show stale data after hardware disconnect~~ → FIX-STALE-DEVICES dispatched
4. Route status / bridge connection false-positive during restart
5. Console logs disappear when bridge reconnects

## Pending Decisions
- `[DECISION OPPORTUNITY]`: M3 transition intensity defaults — tuning after real-world testing.
- `[DECISION OPPORTUNITY]`: M3 section progress intensity curves — adjustable post-deployment.

## Validator Warnings (non-blocking)
- `test_waiting_state_has_next_retry_set` in `test_manager.py` has a vacuous assertion. Tighten in future.

## Recent Context
Session 8 (2026-03-19): Protocol blocker PROTOCOL-PIPELINE-FE resolved — FE state-behavior protocol changes applied across preambles and templates. Generated FIX-STALE-DEVICES handoff for the stale devices/players bug. State behavior defined with operator: both components clear to empty state on hardware disconnect and bridge non-running states. StatusBanner handles bridge-level context separately.

## Recurring Missteps
- **Fix applied at wrong layer / wrong call path:** Check ALL callers when fixing error handling.
- ~~**FE state behavior inferred instead of asked:**~~ RESOLVED — protocol changes applied 2026-03-19.
- ~~**Operator concerns not escalated from session summaries:**~~ RESOLVED — Orchestrator preamble updated with [DECISION NEEDED] gate.

## Next Session Priorities
1. **FIX-STALE-DEVICES** — Dispatch Developer with handoff at `specs/feat-FE-BLT/handoff-FIX-STALE-DEVICES.md`. Follow with Validator, then QA Tester (per protocol: bug fix → Validator → QA).
2. **VALIDATOR-fe-2-console** — Validate FE-2 console implementation. Can run parallel with FIX-STALE-DEVICES.
3. **M3-TASK-001 + CONTRACTS-deck-number** — Begin M3 implementation after Validator pass.
4. **Remaining FE bugs** — Schedule after FIX-STALE-DEVICES pattern established (may inform approach for similar stale-state bugs).
