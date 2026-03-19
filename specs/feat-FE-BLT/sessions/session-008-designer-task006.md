# Session Summary: TASK-006

## Role
Designer

## Objective
Produce a UI State Behavior artifact defining what the Bridge page shows during each phase of the disconnect/reconnect lifecycle (7 system states x 6 components), addressing the operator feedback: "WAY too slow, needs better visual indication of what's actually happening."

## Status
COMPLETE

## Work Performed
- Read all context files: AGENT_BOOTSTRAP, COMMON_RULES, DESIGNER preamble, LEARNINGS, handoff packet, template, spec, tasks, bridgeStore, TopBar, frontend CLAUDE.md, frontend bugs, test scenarios, BridgePage, and all bridge components (BridgeStatusPanel, StatusBanner, DeviceList, PlayerList, HardwareSelectionPanel, ActionBar, RouteStatusBanner, InterfaceSelector)
- Analyzed the current component behavior and state shape to identify gaps in the disconnect/reconnect UX narrative
- Produced the UI State Behavior artifact covering all 7 system states x 6+ components (8 components when counting sub-components of HardwareSelectionPanel separately)
- Defined transitional feedback for the full crash -> restart -> running lifecycle
- Defined countdown behavior for both `crashed` (restart countdown) and `waiting_for_hardware` (poll countdown)
- Defined status banner narrative text for every state
- Identified 2 new derived states (`isRecovering`, `countdownSecondsRemaining`)
- Flagged 6 `[ASK OPERATOR]` items for ambiguous UX decisions with options, tradeoffs, and recommendations
- Wrote the full transition narrative (Phase 1-4) describing the user-visible story during a complete hardware disconnect/reconnect cycle
- Defined priority ordering for empty-state messages in DeviceList and PlayerList

## Files Changed
- `specs/feat-FE-BLT/ui-state-behavior-disconnect.md` — NEW: UI State Behavior artifact (deliverable)
- `specs/feat-FE-BLT/sessions/session-008-designer-task006.md` — NEW: this session summary

## Interfaces Added or Modified
None. Designer is read-only; no code or contract changes.

Two new derived states proposed for bridgeStore (implementation is Developer's responsibility):
- `isRecovering: boolean` — true for a time window after `status` transitions to `running` from non-running
- `countdownSecondsRemaining: number | null` — client-side countdown initialized from `nextRetryInS`

## Decisions Made
- **Included BridgeStatusPanel > TrafficIndicator as a separate component row** even though it was not explicitly listed in the handoff's 6 components. Rationale: it has distinct state behavior from the TopBar TrafficDot and is part of the Bridge page. Alternative: fold into BridgeStatusPanel table (rejected because the behaviors are component-specific).
- **Proposed priority-ordered empty-state branching for DeviceList and PlayerList** rather than parallel if/else. Rationale: with 7 states, a priority ordering prevents ambiguous rendering when multiple conditions are true simultaneously (e.g., `status=crashed` AND `wsConnected=false`). Alternative: individual state checks without priority (rejected because compound states need deterministic resolution).
- **Kept TrafficIndicator hidden in S5 (waiting_for_hardware)** rather than showing it. Rationale: the StatusBanner carries the full narrative in this state. Showing a traffic indicator with "none" adds no information. Alternative: show it for consistency (rejected as visual noise).
- **Proposed disabling ActionBar button in S3/S4** rather than leaving it enabled. Rationale: user-initiated restart during automatic crash-restart could interfere with the recovery sequence and reset failure counters. Alternative: leave enabled (rejected because it creates confusing state interactions).

## Scope Violations
None. Designer is read-only per scope boundary.

## Remaining Work
None for the Designer role. Next steps:
1. Brach resolves the 6 `[ASK OPERATOR]` items in the artifact
2. Developer implements the UI State Behavior artifact

## Blocked On
N/A

## Missteps
None.

## Learnings
- The `isStartingUp` derived state does not cover all the states where components should show non-interactive UI. For example, `waiting_for_hardware` has `isStartingUp=false` (WS is connected, status is not `starting`), so TanStack queries fire normally. This is actually correct for `waiting_for_hardware` (the backend can serve interface/route data even when the bridge is waiting), but it was initially confusing when mapping states to component behavior.

---

## Revision Pass (2026-03-19)

Incorporated all 6 operator decisions and 1 new design principle into the UI State Behavior artifact. All `[ASK OPERATOR]` markers removed; artifact is now a complete, unambiguous spec.

### Operator Decisions Resolved

1. **Recovery window duration** -> 15 seconds. `isRecovering` becomes false when devices become non-empty OR 15s timeout expires, whichever comes first.
2. **StartupIndicator during crash-restart** -> Show during starting phase. Brief flicker acceptable; StatusBanner carries the continuous narrative.
3. **Waiting-for-hardware banner** -> Single message regardless of interface state. Interface-aware messaging deferred to follow-up.
4. **StatusBanner transition animation** -> 300ms fade using Tailwind `transition-opacity duration-300`.
5. **RouteStatusBanner in non-running states** -> Dimmed with explanation text. Layout stability is critical in a DJ performance environment.
6. **ActionBar button in waiting_for_hardware** -> "Force Restart" button, enabled, triggers immediate restart() bypassing poll timer.

### New Design Principle Added

"Visual Feedback for Waits" -- any wait >1 second must have a visual progress indicator (countdown, spinner, pulsing animation). Static text alone is insufficient. Added as a top-level section after States Reference. Audited all component tables and added spinner/pulsing indicators to:
- S4 (starting) StatusBanner: added spinner alongside "Launching bridge subprocess..."
- S6 (recovering) StatusBanner: added pulsing indicator alongside "Discovering devices..."
- S6 (recovering) TrafficDot: added pulsing opacity animation
- S6 (recovering) TrafficIndicator: added pulsing animation
- S4/S6 DeviceList empty states: added spinner/pulsing indicators
- S4/S6 PlayerList empty states: added spinner/pulsing indicators
- S7 StatusBanner: added spinner alongside "Reconnecting..."

### Follow-Up Items Section Added

Three items documented as out of scope: faster interface detection polling (5s instead of 30s), beat-link discovery cycle optimization, and interface-aware waiting_for_hardware messaging (requires contract change).

### Files Changed
- `specs/feat-FE-BLT/ui-state-behavior-disconnect.md` — REVISED: all 6 operator decisions applied, design principle added, follow-up section added, zero `[ASK OPERATOR]` markers remaining
- `specs/feat-FE-BLT/sessions/session-008-designer-task006.md` — UPDATED: this revision pass appended
