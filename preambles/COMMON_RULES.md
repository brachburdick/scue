# SCUE Agent Common Rules

Read `AGENT_BOOTSTRAP.md` before this file.

## Session Setup
Every session starts the same way:
1. Read `AGENT_BOOTSTRAP.md`.
2. Read `preambles/COMMON_RULES.md`.
3. Read your role-specific preamble from `preambles/[ROLE].md`.
4. Read any skill files referenced in your handoff packet.
5. Read your handoff packet or task-specific context.

## Ask, Don't Assume
If the spec, plan, constraints, or handoff leave a meaningful ambiguity, stop and surface it instead of guessing.

Frontend state behavior is operator-owned. If a UI should display differently based on bridge status, hardware presence, route state, Pioneer traffic, or similar state and the expected display is not defined in a spec or UI State Behavior artifact, ask Brach before implementation.

## Decision Transparency
Document every judgment call in the session summary under `## Decisions Made`, including rationale and the rejected alternative.

## Concern Tags
Use these tags to surface issues:
- `[CONCERN]` — something risky or inconsistent
- `[DECISION NEEDED]` — a blocking design or product choice
- `[DECISION OPPORTUNITY]` — a non-blocking choice Brach may want to influence

## [BLOCKED] Protocol
If you hit a genuine ambiguity or missing dependency:
1. Do not infer.
2. Record `[BLOCKED: description]` in the session summary.
3. Complete any unblocked portion of the task.
4. Set status to `BLOCKED` or `PARTIAL`.

## Research Escalation (2-Attempt Rule)
If two genuine attempts do not resolve a technical problem:
1. Stop.
2. Write a Research Request using `templates/research-request.md`.
3. Set status to `BLOCKED`.

## Artifact Templates
All structured outputs must use the schemas in `templates/`. Missing required fields means the artifact is incomplete.

## Project Doc Index
Use exact on-disk paths. Do not ask Brach to paste project docs.

- `AGENT_BOOTSTRAP.md` — project entry point
- `docs/ARCHITECTURE.md` — system architecture
- `docs/interfaces.md` — canonical cross-layer and frontend/backend contracts
- `docs/DECISIONS.md` — ADRs
- `docs/MILESTONES.md` — milestone tracker
- `LEARNINGS.md` — known pitfalls and workflow learnings
- `docs/bugs/*.md` — bug logs
- `docs/agents/orchestrator-state.md` — orchestrator state snapshot
- `docs/agents/startup-prompts/` — copy-paste startup prompts
- `templates/` — artifact templates
- `skills/` — domain skill files
- `specs/feat-[name]/` — feature artifacts

## Confirm Understanding Gate
Before starting implementation or artifact production:
1. Summarize the objective.
2. List the files you will read or modify.
3. Surface any questions or ambiguities.
4. Wait for Brach's confirmation when the task depends on an unresolved decision.

## Read Before Edit
Read every file before editing it.

## Misstep Reporting
Record all tool failures, wrong commands, retries, and environment surprises in `## Missteps` of the session summary.

## Inline-Fix Accountability
Any agent resolving a bug inline without delegation must:
1. Write a session summary with role `[ROLE]-inline`.
2. Update the relevant bug log entry.
3. Update `docs/MILESTONES.md` if a blocker was closed.

## Milestone Maintenance
Any session that closes a blocker must update `docs/MILESTONES.md` before ending.

## Universal Exit Sequence
Every session ends with all of the following:
1. Artifact checklist: confirm required outputs were written to the exact path named in the handoff.
2. Chain-status declaration: set artifact status fields honestly and identify the next routing step.
3. Session retro: record missteps, learnings, and follow-up items.
4. Self-assessment: state confidence and the biggest remaining risk.

## Session Summary
Every session ends with a session summary written to disk using `templates/session-summary.md`.

## LEARNINGS.md
If the session summary contains durable learnings, append them to `LEARNINGS.md` before ending the session.
