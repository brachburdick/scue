---
name: Hardware QA
description: Interactive QA process for features that depend on live Pioneer hardware. Covers the operator-agent protocol, hardware mutation testing, and the note-then-fix discipline.
trigger: QA testing any feature that involves the bridge, scanner, USB browsing, or live playback tracking
---

# Hardware QA

QA for hardware-connected features requires a different process than pure software QA.
The agent cannot observe hardware state directly — it depends on the operator for physical
actions and subjective observations. Hardware state is expensive to reproduce, bugs share
root causes more often than they appear to, and mid-QA fixes contaminate the test environment.

## Core Principle: Note First, Fix Later

**Default:** Record every bug during QA. Do not fix anything until the full QA pass is complete.

**Why:**
- Bugs cluster around shared root causes. Fixing symptom A before discovering symptoms B and C
  leads to three separate fixes instead of one root-cause fix. (Example: the scan_complete WS
  message was never emitted by the backend. This one root cause produced three symptoms:
  scan buttons permanently disabled, status strings not matching, progress panel showing stale
  data. Discovered together, one fix addressed all three.)
- Fixing mid-QA changes the code under test. Subsequent phases are testing different code
  than earlier phases. Results are not comparable.
- Context-switching between QA mode (observing, recording) and debug mode (diagnosing, fixing)
  degrades both. QA requires breadth; debugging requires depth.

**Exception — blocking bugs:** If a bug prevents subsequent phases from being testable
(e.g., scans never complete, so "scan again" phase is impossible), apply a *minimum unblock fix*:
the smallest change that lets QA continue. Note it as a provisional fix, not a final one.
Revisit after the full pass.

## The Operator-Agent QA Protocol

Hardware QA is a conversation. The agent proposes actions, the operator performs physical
steps and reports observations, the agent verifies system state via tools.

### Phase Structure

Every hardware QA plan should have these phase types:

1. **Baseline phases** — Test features with hardware in its initial state.
   Agent-driven. Operator confirms hardware setup once, then agent runs checks.

2. **Hardware mutation phase** (REQUIRED) — Test system response to physical changes.
   Operator-driven. Agent tells the operator what to change, operator does it and reports
   what they see. Agent checks system state after each change.

   Minimum mutation scenarios:
   - Device/media remove while idle
   - Device/media remove during active operation (scan, playback)
   - Device/media insert after session start
   - Device/media swap (remove one, insert different)
   - Recovery verification after each change (can the system resume without restart?)

3. **Error visibility phase** — Verify that every failure state has a user-visible message.
   For each mutation scenario, check: does the UI explain what happened? Silent "Empty"
   states or frozen progress bars are bugs, even if the backend handled the error correctly.

### Agent Behavior During QA

- **Capture everything at discovery time.** For each bug found:
  - Network requests (URL, status code, response body — especially error details)
  - Console errors (exact messages, not just counts)
  - UI state (what the user sees — screenshot or snapshot)
  - Exact steps to reproduce (including hardware state)
  - Timestamp relative to session start
  Hardware state is hard to reproduce later. Rich notes now save hours later.

- **Do not fix.** Record the bug in `docs/bugs/` with status `[OPEN]` and move on.
  The exception is blocking bugs (see above).

- **Ask the operator, don't assume.** When hardware state is ambiguous:
  - "What do you see on the CDJ screen?"
  - "Is the USB LED still lit?"
  - "Did the bridge status dot change color?"
  The agent sees system state; the operator sees physical state. Both are needed.

- **Verify after each operator action.** After the operator performs a physical change,
  the agent should immediately check: network requests, console errors, bridge status,
  and relevant UI components. Don't wait for the operator to report a problem.

### After QA: The Fix Pass

Once all phases are complete and bugs are recorded:

1. **Cluster by root cause.** Group bugs that might share an underlying issue.
   Look for: same endpoint failing, same store not updating, same WS message missing.

2. **Prioritize.** Blockers > data loss > wrong behavior > cosmetic.
   Within each tier, fix shared root causes before isolated symptoms.

3. **Fix in a separate pass.** The agent switches from QA mode to debug mode.
   For each cluster: diagnose root cause, implement fix, run typecheck.

4. **Verification pass.** After all fixes, re-run the affected QA phases (not all of them —
   just the ones that found bugs). If hardware is still connected, ask the operator to
   re-test the mutation scenarios.

## QA Plan Template Addition

When writing a QA plan for any feature that touches bridge/scanner/hardware, append:

```
Phase N: Hardware Mutation
Prerequisites: Operator has physical access to hardware
* Remove [media/device] while system is idle
  - Verify: error message shown (not silent empty state)
  - Verify: other slots/devices still functional
  - Verify: can recover without backend restart
* Remove [media/device] during active [scan/playback]
  - Verify: operation fails gracefully with user-visible message
  - Verify: partial results preserved
  - Verify: can start new operation after failure
* Insert [media/device] after session start
  - Verify: new media discoverable without restart
* Swap [media/device] (remove + insert different)
  - Verify: fresh browse shows new media contents

Phase N+1: Error Visibility
* For each error state discovered above:
  - Is there a user-visible message? (not just console error)
  - Does the message explain what happened and what to do?
  - Does the UI recover to a usable state?
```

## Why This Exists

This skill was created after the Ingestion Page QA (2026-03-25) passed all 10 phases,
then immediately broke when the operator removed a USB. The root cause — stale DLP
connection state after media hot-swap — had been causing intermittent failures across
multiple prior sessions but was never identified because QA never tested hardware mutation.

Static hardware assumptions in QA plans create a systematic blind spot. Features that
work perfectly in testing break in real use because real users change hardware constantly.
