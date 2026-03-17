# Session: Operator — Role-Specific Preamble Restructure
**Date:** 2026-03-17

## What Changed

| File | Change Type | Description |
|---|---|---|
| `docs/agents/preambles/COMMON_RULES.md` | Created | Shared behavioral contract: ask-don't-assume, decision transparency, concern flagging, on-disk doc refs, confirm-understanding gate, session-to-disk, LEARNINGS-to-disk, iterative improvement |
| `docs/agents/preambles/OPERATOR_PREAMBLE.md` | Created | Operator-specific rules: no code access, decision framework, handoff generation, atomization test, session protocol, project state awareness, agent roster reference |
| `docs/agents/preambles/ARCHITECT_PREAMBLE.md` | Created | Architect-specific rules: read-only code access, interactive workflow, exact type definitions, task assignment, [DECISION NEEDED] protocol, handoff generation, contract awareness |
| `docs/agents/preambles/DEVELOPER_PREAMBLE.md` | Created | Implementation agent rules: scope discipline, contract awareness, full env setup (.venv/bin/python), baseline test protocol, common pitfalls from real sessions, session summary format, LEARNINGS-to-disk |
| `docs/agents/README.md` | Created | Index of all agent workflow docs with quick-start guide |
| `handoffs/README.md` | Created | Explains handoff packet directory structure and generation |
| `docs/agents/archive/AGENT_PREAMBLE_v1.md` | Created (archive) | Archived original single preamble |
| `docs/agents/archive/AGENT_PREAMBLE_ADDENDUM_v1.md` | Created (archive) | Archived first addendum |
| `docs/agents/AGENT_PREAMBLE.md` | Deleted | Replaced by role-specific preambles (archived) |
| `docs/agents/AGENT_PREAMBLE_ADDENDUM.md` | Deleted | Merged into DEVELOPER_PREAMBLE.md (archived) |
| `docs/agents/ORCHESTRATOR_PROMPT.md` | Modified | Added preamble structure section referencing on-disk preamble files; changed "ask Brach to paste" to "read from disk" |
| `CLAUDE.md` | Modified | Updated Agent Workflow section with full preamble path references and date-organized directory conventions |
| `LEARNINGS.md` | Modified | Added "Renaming private attributes can break out-of-scope tests" under new "Cross-Cutting / Workflow" section |
| `sessions/2026-03-17/audit-2026-03-17.md` | Moved | From `sessions/audit-2026-03-17.md` into date subdirectory |
| `sessions/2026-03-17/bridge-l0-restart-logic.md` | Moved | From `sessions/bridge-l0-restart-logic-2026-03-17.md` into date subdirectory (also cleaned filename) |

## Decisions Made

1. **COMMON_RULES content selection:** Extracted only rules that genuinely apply to all three roles. Session-to-disk and LEARNINGS-to-disk are in COMMON_RULES (all roles produce session summaries), but env setup and test commands are Developer-only.

2. **LEARNINGS.md entry placement for "Renaming private attributes":** Added under a new "Cross-Cutting / Workflow" section rather than Layer 0, because the pattern applies to any agent renaming internal attributes in any layer.

3. **First two LEARNINGS entries left in Resolved section:** "Bridge listen loop crash" and "is_receiving inflation" were already in LEARNINGS.md under `## Resolved` (not `## Layer 0`). Since they have `(fixed)` tags and the Resolved section is the correct home for fixed issues, I left them there rather than duplicating.

4. **Root session files moved, not copied:** Moved `sessions/audit-2026-03-17.md` and `sessions/bridge-l0-restart-logic-2026-03-17.md` into `sessions/2026-03-17/` to match the date-organized convention. Cleaned the redundant date suffix from the restart-logic filename.

5. **Old preamble files deleted after archiving:** Copied to `docs/agents/archive/` first, then deleted originals to avoid confusion about which files are authoritative.

## Remaining Work

None — all acceptance criteria met.

## LEARNINGS.md Candidates

None — the missing entry ("Renaming private attributes") was added during this session.

## Preamble Improvement Candidates

- **[Issue]:** The handoff packet for this session referenced `AGENT_PREAMBLE_ADDENDUM.md` as a file to read, but it didn't exist on disk yet at session start (was created by Brach mid-session). Handoff packets should only reference files that exist on disk at session start.
- **[Fix]:** When generating handoff packets, verify all referenced files exist. If a file will be created as part of the session itself, note it as "will be created" rather than "read this."
- **[Scope]:** Operator (handoff generation)
