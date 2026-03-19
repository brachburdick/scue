# SCUE Agent Common Rules — Shared Behavioral Contract

> Every agent reads this file at the start of every session, regardless of role.
> These rules apply to all agents: Orchestrator, Architect, Researcher, Designer, Developer, and Validator alike.

---

## 0. Session Setup

Every session starts the same way:

1. Read `AGENT_BOOTSTRAP.md` (project root)
2. Read this file (`docs/agents/preambles/COMMON_RULES.md`)
3. Read your role-specific preamble from `docs/agents/preambles/[ROLE].md`
4. Read any skill files referenced in your handoff packet
5. Read your handoff packet or task-specific context

---

## 1. Ask, Don't Assume

If the spec, plan, or constraints are ambiguous on any point, **ask Brach before proceeding.**

Frame your question as:
> "The spec says [X], but it's unclear whether [Y or Z]. My assumption would be [Y] because [reason]. Should I proceed with that, or do you want something different?"

It is ALWAYS better to ask one question and wait than to implement the wrong thing and need to redo it.

**FE state behavior is always a product decision.** When a bug report or feature task describes UI behavior and the *correct* display for a given system state is not defined in a spec or UI State Behavior artifact, ask Brach before implementing. Do not infer correct FE display behavior from a bug description alone — the operator is the authority on what the UI should show in each state.

---

## 2. Decision Transparency

Document every judgment call you make during your session. If you chose between two valid approaches, interpreted an edge case, or selected a default value — write it down.

**Format:** "I chose [X] over [Y] because [reason]. Alternative considered: [what was rejected and why]."

Include these in your session summary under "Decisions Made."

---

## 3. Proactive Concern Flagging

Use these tags to surface issues:

- **[CONCERN]** — Something that seems wrong, risky, or inconsistent with the architecture, even if it's outside your current task.
- **[DECISION NEEDED]** — A design or infrastructure choice that could go multiple ways and Brach should weigh in. Present options, tradeoffs, and your recommendation.
- **[DECISION OPPORTUNITY]** — A non-blocking choice where Brach might want input but you can proceed with a reasonable default.

### [BLOCKED] Protocol

If you encounter a genuine ambiguity not covered by the spec or handoff packet:

1. Do NOT infer. Do NOT guess.
2. Write a `[BLOCKED: description]` entry in your session summary.
3. Complete as much of the task as possible without the blocked decision.
4. Set status to BLOCKED or PARTIAL.

---

## 4. Research Escalation — The 2-Attempt Rule

If you are stuck on a technical question:

1. **Attempt 1:** Try to solve it using available project documentation and your knowledge.
2. **Attempt 2:** Try an alternative approach or search more broadly.
3. **If still stuck:** Generate a Research Request using `templates/research-request.md` and include it in your session summary. Set status to BLOCKED.

Do NOT spend more than two genuine attempts before escalating. The Researcher role exists for this purpose.

---

## 5. Artifact Templates

All structured outputs must use the schemas in `templates/`. Copy the relevant template and fill in every field.

| Output Type | Template |
|---|---|
| Handoff packet | `templates/handoff-packet.md` |
| Session summary | `templates/session-summary.md` |
| Research request | `templates/research-request.md` |
| Research findings | `templates/research-findings.md` |
| Feature spec | `templates/spec.md` |
| Task breakdown | `templates/tasks.md` |
| Validator verdict | `templates/validator-verdict.md` |

If a required field is missing from your output, the artifact is incomplete. The Operator will send it back.

---

## 6. On-Disk Document References

Agents read docs from disk using exact file paths. **Never ask Brach to paste or upload project documents.** All project knowledge lives at known paths:

### Project entry point
- `AGENT_BOOTSTRAP.md` — Read this first, every session

### Project docs
- `docs/ARCHITECTURE.md` — System architecture and layer descriptions
- `docs/CONTRACTS.md` — Interface contracts between layers
- `docs/DECISIONS.md` — Architecture Decision Records (ADRs)
- `docs/MILESTONES.md` — Milestone tracker and current state

### Project root
- `CLAUDE.md` — Project conventions, commands, critical rules
- `LEARNINGS.md` — Known pitfalls and non-obvious behaviors (read before starting work)

### Bug tracking
- `docs/bugs/*.md` — Per-layer bug logs

### Agent workflow
- `docs/agents/preambles/` — Role-specific preambles (you're reading one now)
- `docs/agents/AGENT_ROSTER.md` — Agent role definitions and scope boundaries
- `docs/agents/HANDOFF_CONTRACTS.md` — Artifact format specifications

### Templates and knowledge
- `templates/` — Artifact schema templates (use these for all outputs)
- `skills/` — Domain skill files (accumulated project knowledge)

### Artifacts
- `specs/feat-[name]/` — Feature specs, plans, tasks, and session logs
- `specs/feat-[name]/sessions/` — Session summaries and validator verdicts for a feature
- `research/` — Research findings (archive)

---

## 7. Confirm Understanding Gate

Every agent confirms understanding before starting work. After reading your handoff packet and preamble files:

1. Summarize what you understand the objective to be
2. List the files you will read/modify
3. State any questions or ambiguities
4. **Do NOT proceed until Brach confirms your understanding is correct**

---

## 8. Session Summary — Write to Disk (Non-Negotiable)

Session summaries are the ONLY communication channel between agents. If it's not written to a file, it doesn't exist for the next agent.

- **Template:** Use `templates/session-summary.md` — every field is required
- **Path for feature work:** `specs/feat-[name]/sessions/session-NNN-[role].md`
- **Path for non-feature work:** `sessions/YYYY-MM-DD/[role]-[task-slug].md`
- **Create the directory** if it doesn't exist
- **Write AFTER** all acceptance criteria are met (or when stopping if PARTIAL/BLOCKED)
- **Tell Brach:** "Session summary written to `[path]`"

---

## 9. LEARNINGS.md — Write to Disk (Non-Negotiable)

If your session summary has learnings entries, append them to `LEARNINGS.md` before ending your session. Do not leave them only in the session summary.

- Add entries under the appropriate layer section
- Use the established format: title, date, context, problem, fix/pattern, prevention
- Add `(fixed)` to the title if the issue is now resolved
- **Tell Brach:** "LEARNINGS.md updated with N entries under [section]"

---

## 10. Iterative Improvement — Flag Protocol Issues

If you encounter a workflow problem that wasted significant time or would affect other agents, flag it in your session summary under "Learnings." The Operator reviews these periodically and updates the appropriate preamble or protocol file.

---

## 11. Inline-Fix Role Accountability

Any agent that resolves a bug directly (without delegating to a Developer agent) must:

1. Write a session summary using `templates/session-summary.md`. Set the Role field to `[ROLE]-inline` (e.g., `Orchestrator-inline`).
2. Update the relevant bug log entry (`docs/bugs/[layer].md`) with `[ROLE: [ROLE]-inline]`.
3. If the fix closes a `[BLOCKER]` item, update the milestone tracker before ending the session.

Do not end the session until all three are complete.

---

## 12. Milestone Maintenance

Any session that closes a `[BLOCKER]` item must update `docs/MILESTONES.md` before ending. This applies regardless of role.

---

## 13. Read Before Edit

Read every file before editing it. The Edit tool enforces this — it will reject any edit to a file not read in the current session. When in doubt, read first.

---

## 14. Misstep Reporting

Record all tool failures, wrong commands, retries, and environment surprises in the `## Missteps` section of your session summary. Be specific: what was tried, what failed, what worked instead. This data feeds the Orchestrator's pattern detection and hook proposals.
