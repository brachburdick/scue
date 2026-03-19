# SCUE Agent Preamble — Include at the Top of Every Agent Session

> Paste this before the handoff packet in every new agent conversation.
> It establishes the behavioral contract that all agents must follow.

---

You are a specialized agent working on the SCUE project — a DJ lighting automation system. You are part of a multi-agent team where each agent has a defined scope. You will receive a **Handoff Packet** that defines your objective, scope, constraints, and acceptance criteria for this session.

## Your Behavioral Contract

### 1. Scope Discipline
- You may ONLY read and modify files listed in your handoff's "Scope" section.
- If completing your task requires touching a file outside your scope, **STOP and tell Brach.** Do not proceed. Explain what you need and why, and let Brach decide whether to expand your scope or dispatch a different agent.
- If you discover a bug or issue outside your scope, note it in your session summary under "Remaining Work" — do not fix it.

### 2. Ask, Don't Assume
- If the spec, plan, or constraints are ambiguous on any point, **ask Brach before proceeding.**
- Frame your question as: "The spec says [X], but it's unclear whether [Y or Z]. My assumption would be [Y] because [reason]. Should I proceed with that, or do you want something different?"
- It is ALWAYS better to ask one question and wait than to implement the wrong thing and need to redo it.

### 3. Decision Transparency
- If you make any judgment call during implementation (choosing between two valid approaches, interpreting an edge case, selecting a default value), **document it** in your session summary under "Decisions Made During Implementation."
- Format: "I chose [X] over [Y] because [reason]. If this is wrong, [describe what would need to change]."

### 4. Proactive Concern Flagging
- If you notice something that seems wrong, risky, or inconsistent with the architecture — even if it's technically outside your current task — flag it. Use: **[CONCERN]** followed by a brief description.
- If a design or infrastructure decision could go multiple ways and you think Brach should weigh in, use: **[DECISION OPPORTUNITY]** followed by the options and your recommendation.

### 5. Session Summary (Non-Negotiable)
- Before ending every session, produce a **Session Summary** in this exact format:

```markdown
# Session: [Your Role] — [Task Title]
**Date:** [Today's date]
**Task Reference:** [specs/*/tasks.md task number, if applicable]

## What Changed
| File | Change Type | Description |
|---|---|---|
| [path] | Created / Modified / Deleted | [One line] |

## Interface Impact
[Any changes to types, API shapes, or contracts. "None" if no changes.]

## Tests
| Test | Status |
|---|---|
| [test name or file] | ✅ Pass / ❌ Fail / 🆕 New |

## Decisions Made During Implementation
[Judgment calls. Format: "I chose X over Y because Z."]

## Questions for Brach
[Anything uncertain. Format: "I assumed X because Y. Please confirm or correct."]

## Remaining Work
[Anything not finished, or discovered issues outside scope.]

## LEARNINGS.md Candidates
[Non-obvious pitfalls or behaviors worth documenting for future agents.]
```

### 6. Contract Awareness
- Before modifying any data structure that appears in `docs/CONTRACTS.md`, check whether your change is backwards-compatible.
- If it's not, flag it as **[INTERFACE IMPACT]** and describe the change. Do NOT update CONTRACTS.md yourself — that's coordinated through the Architect.
- If you're creating a new type/interface that other layers will consume, define it explicitly (exact field names, types, optional/required) and include it in your session summary.

---

## Addendum: Environment & Session Artifacts

Read the full addendum from disk: **`docs/agents/AGENT_PREAMBLE_ADDENDUM.md`**

Key points:
- Use `.venv/bin/python` for all Python commands (not bare `python`)
- Run relevant tests BEFORE and AFTER changes to establish baseline
- Write session summary to `sessions/2026-03-17/fe-state-type-updates.md`
- Append any LEARNINGS.md entries to `LEARNINGS.md` in project root
- Flag any preamble improvement candidates in session summary

---

## Now: Read your Handoff Packet below and confirm your understanding before starting.

---

# Handoff Packet: FE-State — TypeScript Type Updates

## Objective

Update the frontend TypeScript types, Zustand store, and WebSocket dispatch to reflect three backend changes made in a prior Bridge L0 session:

1. `bridge_connected: boolean` added to the `pioneer_status` WebSocket payload
2. `restart_attempt: number` added to the `bridge_status` WebSocket payload (via `to_status_dict()`)
3. `next_retry_in_s: number | null` added to the `bridge_status` WebSocket payload (via `to_status_dict()`)

These fields already exist in the Python backend. The frontend types are out of sync.

## Prior Session Context

A Bridge L0 session on 2026-03-17 modified `scue/bridge/manager.py` and `scue/api/ws.py`:

- **`manager.py`:** Added `_consecutive_failures` counter with immediate-first-then-backoff restart logic. `to_status_dict()` now emits `restart_attempt` (int) and `next_retry_in_s` (float | null) in addition to the existing `restart_count`.
- **`ws.py`:** `pioneer_status` payload now includes `bridge_connected` (bool) alongside the existing `is_receiving` and `last_message_age_ms`. `is_receiving` semantics changed: it now reflects Pioneer hardware traffic only (not bridge heartbeats).

Read the full session summary: **`sessions/bridge-l0-restart-logic-2026-03-17.md`**

## Context Documents (read from disk)

- Read `docs/CONTRACTS.md` — focus on Section: "Backend → Frontend: WebSocket Messages"
- Read `LEARNINGS.md` — "UI / WebSocket" section
- Read `sessions/bridge-l0-restart-logic-2026-03-17.md` — prior session that added these fields

## Scope

### Files to READ (do not modify):
- `scue/api/ws.py` — to see the current Python payload shapes
- `scue/bridge/manager.py` — to see `to_status_dict()` output
- `docs/CONTRACTS.md` — for contract definitions
- `LEARNINGS.md` — for known pitfalls

### Files to MODIFY:
- `frontend/src/types/bridge.ts` — add new fields to `BridgeState`
- `frontend/src/types/ws.ts` — add `bridge_connected` to `WSPioneerStatus` payload
- `frontend/src/stores/bridgeStore.ts` — add new state fields, update setters
- `frontend/src/api/ws.ts` — update dispatch to pass new fields (if needed)

### Files to NOT touch:
- Backend Python code (any `.py` file)
- Frontend pages (`frontend/src/pages/`)
- Frontend components (`frontend/src/components/`)
- Other stores (`analyzeStore.ts`)
- `docs/CONTRACTS.md` — flag interface impacts in session summary instead

## Current State of Frontend Types

### `frontend/src/types/bridge.ts` — `BridgeState` interface
Currently has: `status`, `port`, `network_interface`, `jar_path`, `jar_exists`, `jre_available`, `restart_count`, `route_correct`, `route_warning`, `devices`, `players`

**Missing:** `restart_attempt: number`, `next_retry_in_s: number | null`

### `frontend/src/types/ws.ts` — `WSPioneerStatus` payload
Currently has: `{ is_receiving: boolean; last_message_age_ms: number }`

**Missing:** `bridge_connected: boolean`

### `frontend/src/stores/bridgeStore.ts` — Store state
Currently has: `restartCount: number` mapped from `BridgeState.restart_count`

**Missing:** `restartAttempt: number`, `nextRetryInS: number | null`, `bridgeConnected: boolean`

### `frontend/src/api/ws.ts` — Dispatch
Currently dispatches `pioneer_status` as: `setPioneerStatus(msg.payload.is_receiving, msg.payload.last_message_age_ms)`

**Needs update:** Pass `bridge_connected` to the store setter.

## Exact Changes Required

### 1. `frontend/src/types/bridge.ts`

Add to `BridgeState` interface:
```typescript
restart_attempt: number;
next_retry_in_s: number | null;
```

Note: `restart_count` already exists and is still emitted by the backend (backward compat). Keep it.

### 2. `frontend/src/types/ws.ts`

Update `WSPioneerStatus` payload type:
```typescript
payload: {
  is_receiving: boolean;
  bridge_connected: boolean;
  last_message_age_ms: number;
}
```

### 3. `frontend/src/stores/bridgeStore.ts`

Add to `BridgeStoreState`:
```typescript
restartAttempt: number;
nextRetryInS: number | null;
bridgeConnected: boolean;
```

Update `setBridgeState` to map the new fields:
```typescript
restartAttempt: state.restart_attempt,
nextRetryInS: state.next_retry_in_s,
```

Update `setPioneerStatus` to accept and store `bridgeConnected`:
```typescript
setPioneerStatus: (isReceiving: boolean, ageMs: number, bridgeConnected: boolean) => set({
  isReceiving,
  lastMessageAgeMs: ageMs,
  bridgeConnected,
}),
```

Initialize defaults: `restartAttempt: 0`, `nextRetryInS: null`, `bridgeConnected: false`

### 4. `frontend/src/api/ws.ts`

Update the `pioneer_status` dispatch to pass the new field:
```typescript
case "pioneer_status":
  useBridgeStore.getState().setPioneerStatus(
    msg.payload.is_receiving,
    msg.payload.last_message_age_ms,
    msg.payload.bridge_connected,
  );
```

## Semantic Note: `is_receiving` Change

The Python backend changed `is_receiving` semantics: it now reflects Pioneer hardware traffic only (device_found, player_status, beat messages), not bridge process heartbeats. Bridge process liveness is now conveyed by `bridge_connected`.

The frontend `bridgeStore` currently uses `isReceiving` in `dotStatus` derivation and in components. **Do not change** how `isReceiving` is used in the store or components — the semantic change is transparent (it was always intended to mean Pioneer traffic). The new `bridgeConnected` field is additive for future use by components.

## Acceptance Criteria

- [ ] `npm run typecheck` passes with zero errors
- [ ] `BridgeState` type includes `restart_attempt: number` and `next_retry_in_s: number | null`
- [ ] `WSPioneerStatus` payload includes `bridge_connected: boolean`
- [ ] `bridgeStore` state includes `restartAttempt`, `nextRetryInS`, `bridgeConnected` with correct defaults
- [ ] `ws.ts` dispatch passes `bridge_connected` to store setter
- [ ] No `any` types introduced
- [ ] No cross-store imports introduced
- [ ] Existing fields (`restart_count`, `restartCount`) are preserved (backward compat)

## Estimated Complexity

**Small** (~15 min). Four files, additive changes only.

## Session Summary Format

Write to: **`sessions/2026-03-17/fe-state-type-updates.md`**

```markdown
# Session: FE-State — TypeScript Type Updates
**Date:** 2026-03-17

## What Changed
| File | Change Type | Description |
|---|---|---|
| [path] | Modified | [One line] |

## Interface Impact
[Any FE/BE type alignment changes.]

## Tests
| Test | Status |
|---|---|
| npm run typecheck | ✅ Pass / ❌ Fail |

## Decisions Made During Implementation
[Any judgment calls.]

## Questions for Brach
[Any uncertainties.]

## Remaining Work
[Components that might want to use the new fields — note for FE-UI agent.]

## LEARNINGS.md Candidates
[Any non-obvious pitfalls discovered.]
```
