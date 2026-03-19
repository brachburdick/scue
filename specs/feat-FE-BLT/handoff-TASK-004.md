# Handoff Packet: TASK-004 — Interface score accounts for active traffic and route state

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
The backend interface scoring logic must factor in whether Pioneer traffic is actively flowing on an interface and whether the macOS broadcast route points to it. An interface with active traffic and a correct route must score higher than a baseline interface without.

## Role
Developer

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/network/` — all files in the network module (scoring logic lives here)
  - `scue/api/network.py` — interface list endpoint (may need to pass bridge manager context to scoring)
  - `scue/bridge/manager.py` — read-only context. May need to expose `_last_pioneer_message_time` or adapter device presence via a property. If modification is needed, limit to adding a read-only property.
  - `tests/` — add/update tests for scoring
  - `docs/bugs/frontend.md` — update "Interface score stays at 5" entry
- Files this agent must NOT touch:
  - `frontend/` — all frontend files (score is already displayed from API response)
  - `scue/bridge/adapter.py` — modified by TASK-001
  - `scue/bridge/client.py`
  - `docs/CONTRACTS.md` — flag changes, don't edit directly

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `scue/api/network.py` — interface list endpoint. Trace how interfaces are scored and returned.
- `scue/network/` — investigate the scoring module. Find the function that computes interface scores. Understand what factors currently contribute to the score.
- `scue/bridge/manager.py` — read-only. Key properties: `_last_pioneer_message_time` (line 101), `_route_correct` (line 103), `adapter.devices` (line 124-125). These are the data sources for boosting the score.
- `scue/main.py` — understand how bridge_manager is wired to the API layer (lines 67-77). Check if the network endpoint has access to bridge_manager.
- `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-5 (requirements)
- `docs/bugs/frontend.md` — "[OPEN] Interface score stays at 5 for active en7 interface" entry

## State Behavior
N/A — backend only. Frontend already displays the score from the API response without transformation.

## Constraints
- This task requires investigation first — the scoring logic location and current factors are not fully mapped in the spec. Read the network module before implementing.
- Do NOT add bridge_manager as a hard dependency of the network module. If the scoring function needs bridge context (active traffic, route state), pass it as parameters to the scoring function rather than importing bridge_manager directly. This preserves layer separation.
- The interface list endpoint (`GET /api/network/interfaces`) response shape should NOT change — the score is already a field in the response. Only the computed value changes.
- All pre-existing tests must continue to pass.

## Acceptance Criteria
- [ ] Interface scoring function identified and documented in session summary
- [ ] Scoring considers whether Pioneer traffic is currently flowing on the interface (via a bridge-provided signal: adapter device presence, `_last_pioneer_message_time`, or similar)
- [ ] Scoring considers whether the macOS broadcast route points to the interface (via `_route_correct` or equivalent)
- [ ] An interface with active traffic and correct route scores higher than a baseline interface without
- [ ] Score updates are reflected in `GET /api/network/interfaces` responses
- [ ] No hard coupling between network scoring module and bridge module (data passed as parameters)
- [ ] All pre-existing tests pass
- [ ] Bug entry "[OPEN] Interface score stays at 5" updated in `docs/bugs/frontend.md`
- [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.

## Dependencies
- Requires completion of: none (can run in parallel with all other tasks)
- Blocks: none directly (TASK-006 UX work benefits from accurate scores but doesn't strictly depend)

## Open Questions
None — operator approved including this in the task breakdown.
