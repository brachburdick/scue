You are the QA Tester. Follow your preamble exactly.

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/QA_TESTER.md`

## Context Files
Read these after your preamble:
- `docs/test-scenarios/bridge-lifecycle.md` — the 12 test scenarios you will execute
- `docs/bugs/layer0-bridge.md` — the bug entry with 5 root causes and fixes
- `scue/bridge/manager.py` — the fixed file (read for understanding, do NOT modify)
- `tests/test_bridge/test_manager.py` — existing unit tests (read for understanding)
- `tools/mock_bridge.py` — the mock bridge tool you will use

## Objective
Execute all testable bridge lifecycle scenarios from `docs/test-scenarios/bridge-lifecycle.md`
against the running server with mock tools, and produce a QA Verdict.

## Step 0 — Sanity Check (mandatory)
Run the bridge unit tests first:

    .venv/bin/python -m pytest tests/test_bridge/ -v

If any test FAILS, stop and report. Do not proceed to live testing with broken unit tests.

## Step 1 — Executable Scenarios
Execute these scenarios using `mock_bridge.py` and the dev server:

| Scenario | How to Test |
|----------|-------------|
| SC-005 | Start server (`uvicorn`) WITHOUT running mock_bridge.py. Check bridge status via `GET /api/bridge/status`. Bridge should be in `waiting_for_hardware` state. No crash-restart cycling in logs. |
| SC-007 | Start server WITHOUT mock_bridge.py. Check `GET /api/bridge/status` — should show `waiting_for_hardware`. Hit `POST /api/network/route/fix` — error response should be user-friendly (not raw "route: bad address"). Check server logs for clean messages. |
| SC-009 | Start server, then start mock_bridge (`.venv/bin/python tools/mock_bridge.py`). Wait for bridge to reach `connected` state. Then hit `POST /api/bridge/restart`. Bridge should stop, restart, reconnect within 10 seconds. No crash-restart cycle. `_consecutive_failures` should not increment (check via status API or logs). |
| SC-010 | Start server + mock_bridge. Confirm connected. Stop mock_bridge (Ctrl+C). Hit `POST /api/bridge/restart`. Bridge should restart, find no devices, enter `waiting_for_hardware`. No crash-restart cycle. |
| SC-011 | Start server. Start and rapidly kill mock_bridge 3+ times in quick succession (each run < 30 seconds). Monitor bridge status — after `max_crash_before_fallback` (3) consecutive short-lived crashes, bridge should enter `waiting_for_hardware` with slow-poll loop. Confirm `_consecutive_failures` did NOT reset on the brief runs (check logs). |
| SC-012 | After SC-011 (bridge in `waiting_for_hardware`), start mock_bridge and leave it running. Within 30 seconds (one slow-poll cycle), bridge should transition to `connected`. Devices and players should appear. System fully operational. |

## Step 2 — REQUIRES_OPERATOR Scenarios
Mark these as REQUIRES_OPERATOR in the verdict — they require physical Pioneer hardware:
- SC-001, SC-002, SC-003, SC-004, SC-006, SC-008

Document what the operator would need to do for each (USB-ETH yank/replug, board power
on/off) under Mock Tool Gaps in the verdict.

## Step 3 — Produce QA Verdict
Create the output directory and write the verdict:

    mkdir -p docs/qa-verdicts

Write to: `docs/qa-verdicts/bridge-lifecycle-2026-03-18.md`
Use the template at `templates/qa-verdict.md`.

## Step 4 — Session Summary
Write session summary to: `sessions/2026-03-18/qa-tester-bridge-lifecycle.md`
Use the template at `templates/session-summary.md`.
Create the directory if it does not exist.

## Constraints
- Do NOT modify any source code. You are testing, not fixing.
- Do NOT modify test files. You are running them, not editing them.
- Use `.venv/bin/python` for ALL Python commands (never bare `python`).
- If a scenario FAILs, document precisely: expected vs observed, with log excerpts and timestamps.
- A scenario PASS requires ALL "Then" items to pass. One failure = scenario FAIL.
- If you discover failure modes not covered by existing scenarios, add them to
  `docs/test-scenarios/bridge-lifecycle.md` as new scenarios with status `NOT_TESTED`.
