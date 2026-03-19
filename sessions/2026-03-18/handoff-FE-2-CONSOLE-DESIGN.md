# Handoff Packet: TASK-FE-2-CONSOLE-DESIGN

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DESIGNER.md`

## Objective
Produce a complete UI/UX design spec for the FE-2 Console panel, including layout, component breakdown, interaction model, and log entry format — ready to hand off to FE-State and FE-UI developers.

## Role
Designer

## Scope Boundary
- Files this agent MAY read/modify:
  - `specs/feat-FE-2-console/` — create this directory and write spec here
  - `frontend/src/` — read only (understand existing layout and shell)
  - `docs/MILESTONES.md` — read only (understand FE-2 milestone state)
- Files this agent must NOT touch:
  - Any Python backend files
  - Any `.ts`/`.tsx` source files (design only, no implementation)
  - `docs/CONTRACTS.md`

## Context Files
- `docs/MILESTONES.md` — FE-2 milestone status
- `docs/CONTRACTS.md` — WS message types the console will observe (`bridge_status`, `pioneer_status`)
- `docs/ARCHITECTURE.md` — system layer overview (for understanding what events exist at each layer)
- `LEARNINGS.md` — known pitfalls

## Design Direction (from Operator)

The console panel already exists as a placeholder in the shell layout. The Designer must spec:

### Audience & Mode Toggle
- **Two modes:** Clean (DJ-facing) and Verbose (Dev-facing), toggled by a button in the console header.
- **Clean mode:** Shows only bridge mode changes, connection events, and errors. Human-readable labels.
- **Verbose mode:** Shows every incoming WS message, rendered as structured log entries.

### Log Entry Format
Each entry must show:
- Timestamp (relative: "2s ago" or absolute HH:MM:SS — choose one and justify)
- Source badge (e.g., `bridge`, `pioneer`, `system`)
- Severity indicator (info / warn / error)
- Message string

### Retention & Record Mode
- **Normal operation:** Ring buffer, max 200 entries. Old entries drop off the top.
- **Record mode:** A "Record" button in the console header. When active:
  - Indicator shows recording is in progress (e.g., pulsing red dot)
  - All entries accumulate without limit
  - "Stop & Save" button exports accumulated entries to a `.log` file (plain text, one entry per line)
  - After saving, record buffer clears and normal ring-buffer mode resumes

### Clear Button
A "Clear" button to wipe the visible log. Does not affect record buffer if recording is active.

### v1 Scope Constraint
**No new backend WebSocket message type in v1.** The console sources its entries entirely from messages the frontend already receives (`bridge_status`, `pioneer_status`, others as they are added). Backend Python log streaming is a v2 concern and is explicitly out of scope for this handoff.

## Acceptance Criteria
- [ ] `specs/feat-FE-2-console/spec.md` written with: overview, component breakdown (ConsolePanel, LogEntry, ConsoleHeader controls), state model (what lives in consoleStore), interaction flows (mode toggle, record start/stop/save, clear)
- [ ] `specs/feat-FE-2-console/tasks.md` written: task list for FE-State developer (consoleStore) and FE-UI developer (rendering), each passing the atomization test
- [ ] Log entry format fully specified (fields, timestamp format, source/severity taxonomy)
- [ ] Record mode flow specified (button states, indicator, save output format)
- [ ] Design decisions documented (e.g., relative vs absolute timestamp, ring buffer size, record buffer behavior when switching modes mid-record)
- [ ] **No implementation** — spec and task breakdown only

## Dependencies
- Requires completion of: none
- Blocks: FE-State console task, FE-UI console task

## Open Questions
None — design direction is fully specified above. If you encounter an ambiguity not covered here, flag [DECISION NEEDED — BRACH] and proceed with the rest of the spec.
