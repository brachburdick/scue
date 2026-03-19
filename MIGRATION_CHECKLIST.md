# Migration Checklist: Agent Workflow Infrastructure Upgrade

> Complete these steps to finalize the transition from the legacy workflow to the Operator Protocol-aligned system.

---

## Already Done (by this session)

- [x] Created `templates/` directory with 7 artifact schema templates
- [x] Created `skills/` directory with 5 domain skill file skeletons
- [x] Created `AGENT_BOOTSTRAP.md` at project root
- [x] Renamed preambles: `OPERATOR_PREAMBLE.md` → `ORCHESTRATOR.md`, `ARCHITECT_PREAMBLE.md` → `ARCHITECT.md`, `DEVELOPER_PREAMBLE.md` → `DEVELOPER.md`
- [x] Updated `COMMON_RULES.md` with: Session Setup (Section 0), [BLOCKED] protocol, 2-attempt research escalation, artifact template requirements, updated file references
- [x] Updated `ORCHESTRATOR.md` with: template usage, Designer invocation, Validator awareness, housekeeping/archival
- [x] Updated `ARCHITECT.md` with: template usage, `[REQUIRES DESIGNER REVIEW]` flag, mandatory layer boundaries
- [x] Updated `DEVELOPER.md` with: template usage, `[BLOCKED]` protocol, enhanced scope discipline
- [x] Created new preambles: `RESEARCHER.md`, `VALIDATOR.md`, `DESIGNER.md`
- [x] Updated `CLAUDE.md` agent workflow section
- [x] Updated `docs/agents/README.md` with new roles and file index
- [x] Updated `docs/agents/HANDOFF_CONTRACTS.md` with templates reference

---

## Manual Steps Required

### 1. Session Path Convention (Future-Forward)

New features should use feature-scoped session directories:
```
specs/feat-[name]/sessions/session-001-developer.md
specs/feat-[name]/sessions/session-001-validator.md
```

Existing date-based files in `sessions/YYYY-MM-DD/` and `handoffs/YYYY-MM-DD/` remain as-is. No need to migrate them.

### 2. Update ORCHESTRATOR_PROMPT.md

- [x] Review `docs/agents/ORCHESTRATOR_PROMPT.md` and update it to reference the new preamble file name (`ORCHESTRATOR.md` instead of `OPERATOR_PREAMBLE.md`) — already correct; fixed "Operator" → "Orchestrator" label. Done 2026-03-17.
- [x] Add references to the Validator and Designer roles — already present. Verified 2026-03-17.

### 3. Update AGENT_ROSTER.md

- [x] Review `docs/agents/AGENT_ROSTER.md` and ensure it references the new preamble file names — no old names found. Verified 2026-03-17.
- [x] Add Validator and Designer roles to the roster if not already present — already present as roles #10 and #11. Verified 2026-03-17.

### 4. Populate Skill Files

- [ ] Review `LEARNINGS.md` and extract additional gotchas into the appropriate skill files
- [ ] After each Researcher session, distill findings into skill files (ongoing)
- [ ] Fill `[TODO: Fill from project experience]` placeholders as knowledge accumulates

### 5. Archive Old Preamble References

- [x] Search for any remaining references to `OPERATOR_PREAMBLE.md`, `ARCHITECT_PREAMBLE.md`, or `DEVELOPER_PREAMBLE.md` in docs and update them — only historical references remain (session summaries, this checklist). No active docs reference old names. Verified 2026-03-17.
- [ ] Check `docs/agents/archive/` is up to date with historical preamble versions

### 6. First Validator Session

- [ ] After the next Developer session, run a Validator session to test the new workflow:
  - Provide the handoff packet, session summary, and code diff
  - Verify the Validator produces a verdict using `templates/validator-verdict.md`
  - Confirm the PASS/FAIL cycle works as expected

### 7. First Designer Session (When UI Work Arises)

- [ ] When the next feature includes frontend/UI work, route through Designer before finalizing frontend tasks
- [ ] Verify the Designer produces a UI spec and the Architect incorporates it

---

## Verification

After completing the manual steps:

- [x] All 7 preamble files exist in `docs/agents/preambles/`: COMMON_RULES, ORCHESTRATOR, ARCHITECT, RESEARCHER, DESIGNER, DEVELOPER, VALIDATOR
- [x] All 7 templates exist in `templates/`
- [x] `AGENT_BOOTSTRAP.md` exists at project root and is under 30 lines
- [x] `CLAUDE.md` references the new file locations
- [x] No remaining references to old preamble names (`*_PREAMBLE.md`) in active docs
- [x] Skill files exist in `skills/` for all major domains
