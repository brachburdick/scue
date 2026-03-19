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
- Run `tests/test_bridge/` BEFORE and AFTER changes to establish baseline
- Write session summary to `sessions/2026-03-17/bridge-l0-fallback-integration.md`
- Append any LEARNINGS.md entries to `LEARNINGS.md` in project root
- Flag any preamble improvement candidates in session summary

---

## Now: Read your Handoff Packet below and confirm your understanding before starting.

---

# Handoff Packet: Bridge L0 — Fallback Parser Integration

## Objective

Wire the existing `FallbackParser` (`scue/bridge/fallback.py`) into `BridgeManager` (`scue/bridge/manager.py`) so that when the bridge subprocess is unavailable, the manager transitions to `fallback` state and starts the UDP fallback parser instead of dead-ending at `no_jre`/`no_jar`/permanent `crashed`.

## Context Documents (read from disk)

- Read `specs/audit-2026-03-17/fallback-parser-integration.md` — **the full task spec with desired behavior, implementation notes, and test plan**
- Read `sessions/bridge-l0-restart-logic-2026-03-17.md` — prior session context (restart logic already added)
- Read `docs/CONTRACTS.md` — Section: "Layer 0 → Layer 1B" interface
- Read `LEARNINGS.md` — "Layer 0 — Beat-Link Bridge" section
- Read `scue/bridge/CLAUDE.md` — layer-specific conventions (if it exists)
- Read `docs/agents/AGENT_PREAMBLE_ADDENDUM.md` — environment setup instructions

## Prior Session Context

A Bridge L0 session on 2026-03-17 modified `manager.py` with restart logic:

- **`_consecutive_failures`** counter: tracks consecutive crash-restart failures
- **Immediate-first-then-backoff** pattern: first failure retries immediately (0 delay), subsequent failures use exponential backoff (`RESTART_BASE_DELAY * 2^(failures-1)`, capped at `RESTART_MAX_DELAY`)
- **`RESTART_BASE_DELAY = 2.0`** and **`RESTART_MAX_DELAY = 30.0`** are constants at lines 30-31 (with TODO comments to move to config)
- **`to_status_dict()`** now emits `restart_attempt` and `next_retry_in_s` fields
- **`_restart_count`** is a backward-compat property alias for `_consecutive_failures`
- **108 bridge tests passing** as baseline

Your task builds on top of this: after N consecutive failures, stop retrying the bridge and fall through to fallback mode.

## Scope

### Files to READ (do not modify):
- `specs/audit-2026-03-17/fallback-parser-integration.md` — full spec
- `sessions/bridge-l0-restart-logic-2026-03-17.md` — prior session
- `docs/CONTRACTS.md`
- `LEARNINGS.md`
- `scue/bridge/CLAUDE.md`
- `scue/bridge/messages.py` — BridgeMessage type (fallback emits these)
- `scue/bridge/adapter.py` — adapter pipeline (fallback messages flow through this)
- `scue/bridge/client.py` — for understanding the normal message path

### Files to MODIFY:
- `scue/bridge/manager.py` — add fallback transition logic
- `scue/bridge/fallback.py` — minor changes if needed (likely none — already complete)
- `tests/test_bridge/test_manager.py` — add fallback state transition tests
- `tests/test_bridge/test_fallback.py` — **NEW** — standalone fallback parser tests

### Files to NOT touch:
- `scue/layer1/` — Layer 1 internals
- `scue/api/` — API routers
- `frontend/` — frontend code
- `scue/bridge/adapter.py` — adapter should not need changes (fallback emits BridgeMessage)
- `scue/bridge/messages.py` — message types should not change
- `docs/CONTRACTS.md` — flag interface impacts in session summary instead
- Other test files outside `tests/test_bridge/`

## What Needs to Happen

### 1. Fallback on `no_jre` / `no_jar`

When `BridgeManager.start()` detects no JRE or no JAR:
- Log a warning: `"Bridge unavailable ({reason}), starting UDP fallback parser (degraded mode)"`
- Transition to `fallback` state (not `no_jre`/`no_jar`)
- Instantiate `FallbackParser` with the configured network interface
- Call `await parser.start()`
- Route `FallbackParser.on_message` callback through the same adapter pipeline (`self._adapter.handle_message()`)
- Also call `self._external_on_message(msg)` if set (same as bridge messages)

### 2. Fallback after N consecutive crash-restart failures

The `_consecutive_failures` counter and backoff logic already exist. Add:
- A configurable threshold: `MAX_CRASH_BEFORE_FALLBACK = 3` (hardcode for now — the YAML config task will extract it later)
- In `_schedule_restart()`: if `_consecutive_failures >= MAX_CRASH_BEFORE_FALLBACK`, instead of scheduling another restart, transition to fallback mode
- Log: `"Bridge crashed {N} times, switching to fallback mode"`

### 3. Restart from fallback

When `restart()` is called while in fallback state:
- Stop fallback parser (`parser.stop()`)
- Reset `_consecutive_failures` to 0
- Attempt normal bridge startup
- If bridge startup fails, fall back again

### 4. `to_status_dict()` changes

When in fallback state, `to_status_dict()` should include:
- `"status": "fallback"`
- `"mode": "fallback"` (explicit field for frontend consumption — the status string already handles this, but an explicit field is cleaner)
- Continue including `devices` and `players` from the adapter (fallback messages flow through the same adapter)

### 5. Graceful shutdown

`stop()` must stop the fallback parser if it's running. Check whether `_fallback_parser` is not None and call `parser.stop()`.

## FallbackParser Interface (already implemented)

```python
# scue/bridge/fallback.py
class FallbackParser:
    def __init__(self, on_message: Callable[[BridgeMessage], None] | None = None):
        ...

    async def start(self) -> None:
        """Bind UDP sockets and start listening."""
        ...

    def stop(self) -> None:
        """Close all sockets."""
        ...

    # Emits BridgeMessage objects for: DEVICE_FOUND, PLAYER_STATUS, BEAT
    # Does NOT emit: TRACK_METADATA, BEAT_GRID, WAVEFORM_DETAIL, PHRASE_ANALYSIS, CUE_POINTS
```

The `on_message` callback signature matches what the adapter expects. No adapter changes needed.

## Important: Network Interface Passing

`FallbackParser` uses `pioneer_interfaces()` internally to find link-local interfaces. However, the manager already has `_network_interface` configured. You should pass this to the fallback parser so it knows which interface to prefer.

Check how `FallbackParser.__init__()` handles interface configuration. If it doesn't accept an interface parameter, you may need to add one — but check `fallback.py` first. The parser may already filter by interface internally.

## Test Plan

### Existing tests (baseline — must still pass):
Run `tests/test_bridge/` and record the count (expected: 108 passed).

### New tests in `test_manager.py`:

- [ ] `test_no_jre_transitions_to_fallback` — manager starts, no JRE found, state becomes `fallback`
- [ ] `test_no_jar_transitions_to_fallback` — manager starts, no JAR found, state becomes `fallback`
- [ ] `test_crash_threshold_transitions_to_fallback` — after MAX_CRASH_BEFORE_FALLBACK crashes, state becomes `fallback` instead of retrying
- [ ] `test_fallback_messages_flow_through_adapter` — fallback parser emits BridgeMessage, adapter receives it, callbacks fire
- [ ] `test_restart_from_fallback_stops_parser` — calling `restart()` from fallback state stops the parser and attempts bridge
- [ ] `test_status_dict_reflects_fallback` — `to_status_dict()` returns `status: "fallback"` with correct fields
- [ ] `test_stop_from_fallback_stops_parser` — `stop()` cleanly shuts down fallback parser

### New tests in `test_fallback.py` (NEW FILE):

- [ ] `test_fallback_parser_emits_device_found` — given a keepalive packet, parser emits DEVICE_FOUND BridgeMessage
- [ ] `test_fallback_parser_emits_player_status` — given a status packet, parser emits PLAYER_STATUS BridgeMessage
- [ ] `test_fallback_parser_emits_beat` — given a beat change, parser emits BEAT BridgeMessage
- [ ] `test_fallback_parser_start_stop` — parser starts and stops without error
- [ ] `test_fallback_parser_callback_fires` — on_message callback is called with BridgeMessage objects

Note: Fallback parser tests will need to mock UDP socket creation since they can't bind to real Pro DJ Link ports in CI. Mock `asyncio.get_event_loop().create_datagram_endpoint` or the socket creation path.

## Acceptance Criteria

- [ ] All 108 pre-existing bridge tests still pass
- [ ] Manager transitions to `fallback` state on `no_jre` (not dead-end)
- [ ] Manager transitions to `fallback` state on `no_jar` (not dead-end)
- [ ] Manager transitions to `fallback` after N consecutive crashes
- [ ] Fallback messages flow through adapter → callbacks (same path as bridge messages)
- [ ] `restart()` from fallback stops parser and attempts bridge
- [ ] `stop()` from fallback cleans up parser
- [ ] `to_status_dict()` reflects fallback state
- [ ] New tests: ≥7 manager tests + ≥5 fallback tests, all passing
- [ ] No cross-layer imports introduced
- [ ] No changes to adapter.py or messages.py

## Estimated Complexity

**Medium** (~30 min). The fallback parser is already fully implemented. This is primarily wiring work in `manager.py` + tests.

## Session Summary Format

Write to: **`sessions/2026-03-17/bridge-l0-fallback-integration.md`**

```markdown
# Session: Bridge (L0) — Fallback Parser Integration
**Date:** 2026-03-17

## What Changed
| File | Change Type | Description |
|---|---|---|
| [path] | Modified/Created | [One line] |

## Interface Impact
[Any changes to to_status_dict() output shape. Note if frontend types need updating.]

## Tests
| Test | Status |
|---|---|
| Pre-existing bridge tests (108) | ✅ Pass |
| [new test name] | 🆕 ✅ |

## Decisions Made During Implementation
[Judgment calls about fallback behavior, threshold values, etc.]

## Questions for Brach
[Any uncertainties about fallback behavior or edge cases.]

## Remaining Work
[e.g., "FE-State agent should handle fallback status display", "YAML config agent should extract MAX_CRASH_BEFORE_FALLBACK"]

## LEARNINGS.md Candidates
[Any non-obvious pitfalls discovered.]
```
