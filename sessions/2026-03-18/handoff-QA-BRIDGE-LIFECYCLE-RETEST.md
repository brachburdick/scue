You are the QA Tester. Follow your preamble exactly.

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/QA_TESTER.md`

## Context Files
Read these after your preamble:
- `docs/test-scenarios/bridge-lifecycle.md` — scenarios you will execute
- `docs/bugs/layer0-bridge.md` — full BUG-BRIDGE-CYCLE entry; all 6 root causes now fixed
- `docs/qa-verdicts/bridge-lifecycle-2026-03-18.md` — prior verdict; know what failed and why
- `sessions/2026-03-18/summary-FIX-LAST-MESSAGE-TIME.md` — what Fix 1 changed
- `sessions/2026-03-18/developer-fix-sc007-route-api.md` — what Fix 2 changed

## Objective
Re-test the specific scenarios that failed in the previous QA session. Both fixes have
Validator PASS. Confirm they resolve the live failures. Produce a final QA Verdict.

## Step 0 — Sanity Check
Run bridge tests first:

    .venv/bin/python -m pytest tests/test_bridge/ -v

Then full suite:

    .venv/bin/python -m pytest tests/ -v

Known pre-existing failures to ignore (not caused by these fixes):
- Up to 6 failures in `test_analysis_edge_cases.py` — librosa not installed in this env.
  These are pre-existing and unrelated. Do NOT flag them as regressions.

If any OTHER test fails, stop and report.

## Step 1 — API-Only Scenarios (no hardware action needed)

### SC-007 / SC-014: Route fix API friendly error
Start the server:

    .venv/bin/python -m uvicorn scue.main:app --reload

Call the route fix endpoint with a nonexistent interface:

    POST /api/network/route/fix
    Body: {"interface": "en16"}

Expected: HTTP 500 with a user-friendly error message — NOT raw "route: bad address: en16".
The error field should explain the adapter must be connected (e.g. "Network interface 'en16'
is not available...").

Record PASS or FAIL with the exact response body.

## Step 2 — Live Hardware Scenarios (interactive checkpoints)

For each scenario below, issue a checkpoint to the operator, wait for "done", then observe.
Use the checkpoint format from your preamble.

**Precondition for all hardware scenarios:** Server running, Pioneer XDJ-AZ connected and
bridge in `connected` state with devices visible. Verify via `GET /api/bridge/status` before
starting each scenario.

---

### SC-001: USB-ETH adapter unplugged during good connection

[CHECKPOINT] Please unplug the USB-Ethernet adapter. Reply "done" when unplugged.

Then observe within the time windows:
- Pioneer traffic indicator off within 3s (check `GET /api/bridge/status` → `is_receiving`)
- Bridge transitions to `waiting_for_hardware` — NOT crash-restart cycle
- No macOS window focus stealing or menu bar flashes
- Logs show clean disconnect message, not raw exception

---

### SC-002: USB-ETH adapter plugged back in after SC-001

[CHECKPOINT] Please plug the USB-Ethernet adapter back in. Reply "done" when plugged in.

Then observe within 35s (one slow-poll cycle):
- Bridge detects restored interface and transitions to `connected`
- Pioneer traffic resumes (`is_receiving: true`)
- Devices reappear in device list
- No manual intervention required

---

### SC-003: Board powered off during good connection

(Reset to known-good state first: bridge `connected`, devices visible)

[CHECKPOINT] Please power off the XDJ-AZ. Reply "done" when powered off.

Then observe:
- Pioneer traffic stops within 3s
- Bridge transitions to `waiting_for_hardware` — NOT crash-restart cycle
- No macOS focus stealing
- Logs show clean message

---

### SC-004: Board powered back on after SC-003

[CHECKPOINT] Please power the XDJ-AZ back on. Reply "done" when it has fully booted
(wait for the board to finish startup before replying — approximately 20-30 seconds after
the power button).

Then observe within 10s of your "done":
- Bridge detects board and transitions to `connected`
- Device appears in device list
- Player data (BPM, pitch) begins streaming
- No manual intervention required

---

### SC-010: "Apply and Restart Bridge" clicked while board is off

(Reset: board OFF, USB-ETH plugged, server running)

[CHECKPOINT] Please power off the XDJ-AZ if it is on. Reply "done" when board is off.

Then: call `POST /api/bridge/restart`

Observe:
- Bridge restarts, finds no Pioneer devices
- Bridge enters `waiting_for_hardware` — NOT crash-restart cycle
- No oscillation between `waiting_for_hardware` and crash cycles
- `_consecutive_failures` resets on entering `waiting_for_hardware` (check logs)

---

## Step 3 — Produce QA Verdict

Write to: `docs/qa-verdicts/bridge-lifecycle-2026-03-18-retest.md`
Use the template at `templates/qa-verdict.md`.

## Step 4 — Update Test Scenario Matrix

For each scenario that PASSES, update its status in `docs/test-scenarios/bridge-lifecycle.md`:
- Change `**Status:** NOT_TESTED` to `**Status:** PASS`
- Fill in `**Actual:**` with a one-line summary of what was observed

For any that FAIL, leave as NOT_TESTED and document in the verdict.

## Step 5 — Session Summary

Write to: `sessions/2026-03-18/qa-tester-bridge-lifecycle-retest.md`
Use `templates/session-summary.md`.

## Constraints
- Do NOT modify any source code or test files.
- Use `.venv/bin/python` for ALL Python commands.
- A scenario PASS requires ALL "Then" items from the test scenario matrix to pass.
- The 6 librosa failures in test_analysis_edge_cases.py are pre-existing — do not flag them.
- If a scenario FAILs, document precisely: expected vs observed, log excerpts, timestamps.
