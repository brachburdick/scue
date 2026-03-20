# Migration Checklist: SCUE v1.7 Protocol Sync

This checklist tracks the migration from SCUE's legacy workflow docs to the root operator protocol v1.7 structure.

## Completed In This Sync

- [x] Created canonical `preambles/` and moved active role guidance there
- [x] Added `docs/interfaces.md` as the canonical contract document
- [x] Converted `docs/CONTRACTS.md` into a compatibility pointer
- [x] Added `templates/plan.md`
- [x] Upgraded `templates/handoff-packet.md` to the v1.7 schema while preserving SCUE's `## State Behavior` discipline
- [x] Upgraded `templates/session-summary.md` to the v1.7 durable-artifact schema
- [x] Upgraded `templates/validator-verdict.md` to the v1.7 durable-artifact schema
- [x] Upgraded `templates/orchestrator-state.md` to the v1.7 state schema
- [x] Added `docs/agents/startup-prompts/kickstart.md`
- [x] Updated all active startup prompts to use `preambles/` and `docs/interfaces.md`
- [x] Updated `AGENT_BOOTSTRAP.md` to the canonical path layout
- [x] Turned legacy `docs/agents/preambles/*` files into compatibility pointers
- [x] Turned legacy workflow docs in `docs/agents/README.md`, `docs/agents/HANDOFF_CONTRACTS.md`, and `docs/agents/ORCHESTRATOR_PROMPT.md` into compatibility pointers

## Still Recommended

### 1. Directory Canonicalization For Existing Features

- [ ] Create or backfill canonical subdirectories where useful:
  - `specs/feat-[name]/handoffs/`
  - `specs/feat-[name]/design/`
  - `specs/feat-[name]/reviews/`
  - `specs/feat-[name]/sessions/`
- [ ] Decide whether to migrate existing feature-root handoff files into `handoffs/` or leave them in place as legacy artifacts with pointers
- [ ] Decide whether existing UI artifacts such as `specs/feat-FE-BLT/ui-state-behavior-disconnect.md` should be migrated into `design/`

### 2. Legacy Role-Roster Drift

- [ ] Review `docs/agents/AGENT_ROSTER.md` for legacy contract naming and pre-v1.7 workflow assumptions
- [ ] Decide whether to preserve it as a project-specific reference or rewrite it against `docs/interfaces.md` and the current role model

### 3. Live State Snapshot Hygiene

- [ ] Reconcile `docs/agents/orchestrator-state.md` with the latest feature sessions before the next orchestration session if it is stale

### 4. Future Artifact Paths

- [ ] Prefer canonical new outputs on future work:
  - Handoffs: `specs/feat-[name]/handoffs/handoff-[TASK-ID].md`
  - Session summaries: `specs/feat-[name]/sessions/session-[NNN]-[role].md`
  - Designer outputs: `specs/feat-[name]/design/ui-spec.md`
  - Validator verdicts: `specs/feat-[name]/reviews/validator-[TASK-ID].md`
  - QA verdicts: `specs/feat-[name]/reviews/qa-[TASK-ID-or-BUG-ID].md`

## Verification

- [x] `docs/interfaces.md` exists
- [x] `templates/plan.md` exists
- [x] `docs/agents/startup-prompts/kickstart.md` exists
- [x] `preambles/` exists and contains all required role preambles
- [x] Active startup prompts now reference canonical SCUE paths
