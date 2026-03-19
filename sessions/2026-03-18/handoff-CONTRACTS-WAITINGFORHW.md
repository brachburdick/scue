# Handoff Packet: TASK-CONTRACTS-WAITINGFORHW

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/ARCHITECT.md`

## Objective
`docs/CONTRACTS.md` accurately documents `"waiting_for_hardware"` as a valid `mode` value in the `bridge_status` WebSocket payload, and the existing mode documentation is unambiguous.

## Role
Architect

## Scope Boundary
- Files this agent MAY read/modify:
  - `docs/CONTRACTS.md`
- Files this agent must NOT touch:
  - Any source code files (`.py`, `.ts`, `.tsx`, `.java`)
  - Any other doc files

## Context Files
- `docs/CONTRACTS.md` — the file to update
- `scue/bridge/manager.py` — read to confirm the exact mode values emitted (do not modify)
- `scue/bridge/messages.py` — read to confirm BridgeStatusPayload schema (do not modify)

## Background
`BridgeManager` now emits three distinct `mode` values in `bridge_status` WS payloads:
- `"bridge"` — full beat-link running
- `"fallback"` — UDP degraded mode
- `"waiting_for_hardware"` — bridge started, no hardware detected yet, polling at 30s intervals

The current `docs/CONTRACTS.md` bridge_status section documents only `"bridge"` and `"fallback"`, and the existing note at the bottom of the bridge_status block is ambiguous:
> `"mode": "bridge"` with status indicating availability

This note must be clarified or removed as part of this update.

## Constraints
- Documentation change only — no code edits.
- The Change Protocol at the bottom of CONTRACTS.md requires: discussion (done — this handoff is the record), DECISIONS.md entry (not required for an additive doc fix to an existing contract; note that in session summary), and updated tests on both sides (frontend type update is handled by TASK-FE-WAITING-STATE; backend already emits this value).
- Be precise: show the full updated `mode` field comment with all three valid values.

## Acceptance Criteria
- [ ] The `bridge_status` payload block in CONTRACTS.md shows `mode` as `"bridge" | "fallback" | "waiting_for_hardware"` with a one-line description of each
- [ ] The ambiguous note about `"mode": "bridge" with status indicating availability` is removed or replaced with clear prose
- [ ] No other sections of CONTRACTS.md are modified
- [ ] Session summary documents what was changed and why

## Dependencies
- Requires completion of: none
- Blocks: nothing (informational update)

## Open Questions
None — proceed.
