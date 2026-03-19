# Handoff Packet: TASK-FE-WAITING-STATE

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
`bridgeStore` correctly handles the `"waiting_for_hardware"` bridge mode value, and `BridgeStatusPanel` displays a clear "Waiting for hardware..." state instead of an unknown/stale badge.

## Role
Developer (FE-State)

## Scope Boundary
- Files this agent MAY read/modify:
  - `frontend/src/stores/bridgeStore.ts`
  - `frontend/src/components/bridge/BridgeStatusPanel.tsx` (or wherever the bridge status badge/banner lives — confirm by reading)
  - `frontend/src/types/bridge.ts` (read only, to confirm existing mode type; update the mode type union if `"waiting_for_hardware"` is not already present)
  - `frontend/src/types/ws.ts` (read only)
- Files this agent must NOT touch:
  - Any Python backend files
  - Any other frontend pages or stores
  - `docs/CONTRACTS.md` (Architect handles that separately)

## Context Files
- `docs/CONTRACTS.md` — bridge_status WS payload schema (note: `"waiting_for_hardware"` mode value not yet documented here; treat this handoff as the ground truth for that value)
- `docs/bugs/frontend.md` — prior FE bug context
- `LEARNINGS.md` — known pitfalls

## Background
The `BridgeManager` (`scue/bridge/manager.py`) now emits `mode: "waiting_for_hardware"` in bridge_status WebSocket payloads when the Java bridge starts but no Pioneer hardware is detected within the initial window. The frontend currently has no handling for this mode value — it will fall through to an unknown/stale state.

The three known mode values are now:
- `"bridge"` — full beat-link running, hardware may or may not be connected
- `"fallback"` — UDP degraded mode
- `"waiting_for_hardware"` — bridge started, polling for hardware at 30s intervals

## Constraints
- Do not modify any existing API endpoints or backend files.
- All type changes must maintain TypeScript strict-mode compliance.
- All pre-existing tests must continue to pass (run `cd frontend && npm run typecheck` to verify).
- The `"waiting_for_hardware"` state is **not an error** — display it as a neutral/pending state, not red.

## Acceptance Criteria
- [ ] `bridgeStore` recognizes `"waiting_for_hardware"` as a valid mode value (no fallthrough to unknown)
- [ ] `BridgeStatusPanel` (or equivalent) displays a "Waiting for hardware..." label/badge when `mode === "waiting_for_hardware"` — distinct from both the healthy running state and error states
- [ ] The mode type union in `frontend/src/types/bridge.ts` (or wherever mode is typed) includes `"waiting_for_hardware"`
- [ ] `npm run typecheck` passes with zero errors
- [ ] All pre-existing tests pass
- [ ] **AC — Interface Impact:** No new WS fields or contracts introduced; if any interface changes are made, flag `[INTERFACE IMPACT]` in session summary and stop.

## Dependencies
- Requires completion of: none
- Blocks: FE-2-console (minor — consoleStore will log mode transitions; `"waiting_for_hardware"` should be a loggable event)

## Open Questions
None — proceed.
