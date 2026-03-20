# Orchestrator State Snapshot

**Last updated:** 2026-03-19 (session 10, continued) — M3 on hold. M0-M2 feature scoping complete. Architect intake ready.

<!-- This file is written at the end of every Orchestrator session and read at the start. -->
<!-- If this file is absent or stale, request it by name before proceeding. -->

## Active Milestone
**FE-Analysis-Viewer** — Architect spec needed. Screen for viewing TrackAnalysis results: Pioneer-style colored waveform (from analysis RGB 3-band data) with section overlays, section list (selectable, filterable), placeholder for Tier 2 events. Prep/debugging use. No editing for v1.

**FE-Live-Deck-Monitor** — Architect spec needed. Screen showing 2 decks with waveform + beat-synced cursor, track metadata, real-time section/event overlay (Layer 1 output). Track matching via `rekordbox_id → fingerprint → TrackAnalysis`. Debugging use, eventually user-facing.

**Research: Waveform Sources & Track ID** — Research Request needed. Waveform data availability across hardware types, track ID reliability on DLP hardware, data flow direction (deck-first vs analysis-first), audio fingerprinting timeline.

**M3 (Cue Stream, Layer 2)** — ON HOLD. 9 tasks defined at `specs/feat-M3-cue-stream/`. TASK-001 handoff written but paused. Resumes after M0-M2 foundational features and research settle.

## Operator Decisions (this session)

1. **Waveform source for both screens:** Use analysis-sourced RGB 3-band waveform data (already computed at 60 FPS, stored in TrackAnalysis JSON). Pioneer-style coloring (bass=blue, mids=green/cyan, highs=red/white) — the analysis data is already in this shape (3 frequency bands). No legacy hardware waveform streaming needed for v1.
2. **Pioneer-style rendering:** Waveforms must match industry standard (rekordbox/Serato colored-by-frequency style). Analysis RGB data maps directly to this.
3. **Build order for screens:** Architect decides based on dependency analysis.
4. **Analysis Viewer editing:** No editing for v1. Getting section/event output visible is the priority; accuracy tuning comes later.
5. **Analysis Viewer parameter tweaking:** Stub/placeholder area only. Actual UX depends on future research into what parameters need tuning.
6. **Tier 2 events (M7):** Screens should have placeholder slots ready but no event detection implementation.
7. **Live Deck Monitor deck count:** 2 decks for v1. Up to 6 eventually.
8. **Screens are separate pages**, not combined.
9. **No cross-screen editing** — analysis corrections happen in the Analysis Viewer, not the Live Monitor.
10. **Future 4th screen idea:** Section/event taxonomy manager where users name/manage classes of sections and acoustic events. Deferred, not in current scope.
11. **M3 paused** until M0-M2 foundational features and research are settled.

## Completed Features

### FE-BLT Disconnect/Reconnect — CLOSED
Spec: `specs/feat-FE-BLT/spec-disconnect-reconnect.md`
Tasks: `specs/feat-FE-BLT/tasks-disconnect-reconnect.md`
Test scenarios: `docs/test-scenarios/bridge-lifecycle.md` (SC-017 through SC-022)

| Task ID | Status | Validator | QA | Session Summary |
|---------|--------|-----------|-----|-----------------|
| TASK-001 | **COMPLETE** | ✅ PASS | — | `session-006-developer-task001.md`, `validator-task001.md` |
| TASK-002 | **COMPLETE** | ✅ PASS | — | `session-007-developer-task002.md`, `validator-task002.md` |
| TASK-003 | **COMPLETE** | ✅ PASS | — | `session-005-developer-task003.md`, `validator-task003.md` |
| TASK-004 | **COMPLETE** | ✅ PASS | — | `session-005-developer-task004.md`, `validator-task004.md` |
| TASK-005 | **COMPLETE** | ✅ PASS | — | `session-007-developer-task005.md`, `validator-task005.md` (no code change) |
| TASK-006 | **COMPLETE** | ✅ PASS | ✅ PASS | Designer: `session-008-designer-task006.md`, Developer: `session-009-developer-task006a.md` + `session-009-developer-task006b.md`, Validator: `session-010-validator-task006ab.md`, QA: `session-011-qa-tester-task006ab.md` |

**Totals:** 6 tasks, 6 Developer sessions, 6 Validator PASS, 1 QA PASS, 0 FAILs, 26 new tests.

### FE-2 Console — CLOSED
Spec: `specs/feat-FE-2-console/`

| Phase | Status | Session |
|-------|--------|---------|
| Designer | **COMPLETE** | `specs/feat-FE-2-console/sessions/session-000-designer.md` |
| Developer (all 6 tasks) | **COMPLETE** | `specs/feat-FE-2-console/sessions/session-001-developer.md` |
| Validator | ✅ PASS | `specs/feat-FE-2-console/sessions/session-002-validator.md` |
| Architect Review | ✅ PASS (ADVISORY) | `specs/feat-FE-2-console/sessions/session-003-architect-review.md` |

**Advisory items deferred to follow-up backlog** (see below).

## Task Status — M3 Cue Stream (ON HOLD)

Spec: `specs/feat-M3-cue-stream/spec.md`
Tasks: `specs/feat-M3-cue-stream/tasks.md`
Handoff: `specs/feat-M3-cue-stream/sessions/handoff-m3-task001.md` (status: ON HOLD)

All 9 tasks PENDING. Wave strategy documented in handoff. Resumes after M0-M2 work settles.

## Previously Completed
| Task ID | Status | Notes |
|---------|--------|-------|
| BUG-BRIDGE-CYCLE | **COMPLETE** | 6 root causes fixed. QA verified. |
| FE-bridge-waiting-state | **COMPLETE** | Validator PASS. |
| CONTRACTS-waitingforhw | **COMPLETE** | CONTRACTS.md updated. |
| DEVELOPER-md-mock-tip | **COMPLETE** | Inline fix. |
| M3-spec | **COMPLETE** | 9 atomized tasks at `specs/feat-M3-cue-stream/`. |
| VALIDATOR-fe-waiting | **COMPLETE** | PASS. |
| FIX-LAST-MESSAGE-TIME | **COMPLETE** | Validator PASS. Merged into BUG-BRIDGE-CYCLE. |
| FIX-SC007-ROUTE-API | **COMPLETE** | Validator PASS. Merged into BUG-BRIDGE-CYCLE. |
| PROTOCOL-PIPELINE-FE | **COMPLETE** | Protocol review applied 2026-03-19. |
| FIX-STALE-DEVICES | **SUPERSEDED** | Replaced by FE-BLT TASK-001–006. |

## Active Sessions
None active. Next dispatches: Architect (2 feature specs) + Researcher (waveform/track ID).

## Open Blockers
None.

## Open FE Bugs
All 6 disconnect/reconnect bugs resolved (see FE-BLT section above).

## Pending Decisions
- `[DECISION OPPORTUNITY]`: M3 transition intensity defaults — tuning after real-world testing. (ON HOLD with M3)
- `[DECISION OPPORTUNITY]`: M3 section progress intensity curves — adjustable post-deployment. (ON HOLD with M3)
- ~~`[DECISION OPPORTUNITY]`: Waveform resolution — 60 FPS may be insufficient for zoomed detail view.~~ **RESOLVED (2026-03-19):** 60 FPS is sufficient for v1. Increasing resolution later is trivial (single pipeline parameter). Ship and iterate.
- `[DECISION OPPORTUNITY]`: Future section/event taxonomy manager screen — deferred, operator noted as a future 4th screen.

## Validator Warnings (non-blocking)
- `test_waiting_state_has_next_retry_set` in `test_manager.py` has a vacuous assertion. Tighten in future.

## Recent Context
Session 10 (2026-03-19): Orchestrator session — major priority redirect.
- Caught up on sessions 008–011 (FE-BLT) and 002–003 (FE-2 Console). Both features closed.
- Operator redirected from M3 implementation to M0-M2 foundational features:
  1. Analysis Viewer screen (view/debug TrackAnalysis with waveform + section overlays)
  2. Live Deck Monitor screen (2-deck real-time Layer 1 output visualization)
  3. Research: waveform sources, track ID reliability, data flow direction
- M3-TASK-001 handoff put ON HOLD.
- Investigated waveform data sources: analysis-sourced RGB 3-band waveform is sufficient for v1. Pioneer-style coloring is already the natural output format. No need to re-enable legacy hardware waveform streaming.
- Investigated DLP track ID issues: documented in LEARNINGS.md (rekordbox_id instability on XDJ-AZ). Audio fingerprinting fully designed but deferred (see `docs/FUTURE_AUDIO_FINGERPRINTING (1).md`).

## Recurring Missteps
- **Fix applied at wrong layer / wrong call path:** Check ALL callers when fixing error handling.
- **Architect omitting required artifacts:** Session-004 initially missed handoff packets, test scenarios, and superseded marking. Caught by operator. Execution gap, not process gap.
- **Navigating to wrong project directory:** QA (session-011) and Developer (session-009b) navigated to CRUCIBLE instead of DjTools/scue. Working directory awareness issue — include explicit `project_root` in handoffs.
- ~~**FE state behavior inferred instead of asked:**~~ RESOLVED — protocol changes applied 2026-03-19.
- ~~**Operator concerns not escalated from session summaries:**~~ RESOLVED — Orchestrator preamble updated.

## Follow-Up Backlog
- **FE-2-ADVISORY-1:** Missing "Reconnecting... (attempt N)" system entry in console during WS reconnection. Small change to `scheduleReconnect()` in `ws.ts`. Deferred.
- **FE-2-ADVISORY-2:** Chevron direction (down/right triangle) differs from spec (up/down chevron). Cosmetic. Deferred.
- **FE-2-ADVISORY-4:** No tests written for consoleStore ring buffer or consoleMapper diff detection. High-value test targets. Deferred.
- **FE-BLT-FOLLOWUP-1:** Faster interface detection polling (5s vs 30s) during `waiting_for_hardware`. From Designer session-008.
- **FE-BLT-FOLLOWUP-2:** Beat-link discovery cycle optimization. From Designer session-008.
- **FE-BLT-FOLLOWUP-3:** Interface-aware `waiting_for_hardware` messaging (requires contract change). From Designer session-008.
- **FE-BLT-QA-GAP-1:** Mock tool / fixture data for DeviceInfo/PlayerInfo shapes to enable recovery-to-S1 testing. From QA session-011.

## Next Session Priorities
1. **Dispatch Architect** — Produce specs for FE-Analysis-Viewer and FE-Live-Deck-Monitor (Architect decides build order). Key context: analysis-sourced RGB waveform, Pioneer-style coloring, no editing v1, 2-deck monitor, placeholder for Tier 2 events.
2. **Dispatch Researcher** — Waveform sources across hardware types, track ID reliability on DLP, data flow direction question, audio fingerprinting feasibility/timeline.
3. **After specs land** — Standard pipeline: Designer → Developer → Validator per feature.
4. **After research lands** — Architect reviews findings, proposes any ADRs, may revise screen specs or Layer 1 architecture.
