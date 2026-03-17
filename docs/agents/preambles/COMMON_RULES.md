# SCUE Agent Common Rules — Shared Behavioral Contract

> Every agent reads this file at the start of every session, regardless of role.
> These rules apply to all agents: Operator, Architect, and Developer alike.

---

## 1. Ask, Don't Assume

If the spec, plan, or constraints are ambiguous on any point, **ask Brach before proceeding.**

Frame your question as:
> "The spec says [X], but it's unclear whether [Y or Z]. My assumption would be [Y] because [reason]. Should I proceed with that, or do you want something different?"

It is ALWAYS better to ask one question and wait than to implement the wrong thing and need to redo it.

---

## 2. Decision Transparency

Document every judgment call you make during your session. If you chose between two valid approaches, interpreted an edge case, or selected a default value — write it down.

**Format:** "I chose [X] over [Y] because [reason]. If this is wrong, [describe what would need to change]."

Include these in your session summary under "Decisions Made."

---

## 3. Proactive Concern Flagging

Use these tags to surface issues:

- **[CONCERN]** — Something that seems wrong, risky, or inconsistent with the architecture, even if it's outside your current task.
- **[DECISION NEEDED]** — A design or infrastructure choice that could go multiple ways and Brach should weigh in. Present options, tradeoffs, and your recommendation.
- **[DECISION OPPORTUNITY]** — A non-blocking choice where Brach might want input but you can proceed with a reasonable default.

---

## 4. On-Disk Document References

Agents read docs from disk using exact file paths. **Never ask Brach to paste or upload project documents.** All project knowledge lives at known paths:

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
- `docs/agents/ORCHESTRATOR_PROMPT.md` — Orchestrator system prompt

### Artifacts
- `specs/` — Feature specs, audit specs, task breakdowns
- `sessions/YYYY-MM-DD/` — Prior session summaries, organized by date
- `handoffs/YYYY-MM-DD/` — Handoff packets, organized by date

---

## 5. Confirm Understanding Gate

Every agent confirms understanding before starting work. After reading your handoff packet and preamble files:

1. Summarize what you understand the objective to be
2. List the files you will read/modify
3. State any questions or ambiguities
4. **Do NOT proceed until Brach confirms your understanding is correct**

---

## 6. Session Summary — Write to Disk (Non-Negotiable)

Session summaries are the ONLY communication channel between agents. If it's not written to a file, it doesn't exist for the next agent.

- **Path:** `sessions/YYYY-MM-DD/[agent]-[task-slug].md`
- **Create the date directory** if it doesn't exist: `mkdir -p sessions/$(date +%Y-%m-%d)`
- **Write AFTER** all acceptance criteria are met
- **Tell Brach:** "Session summary written to `sessions/YYYY-MM-DD/[filename].md`"
- All date-named files should be organized into date subdirectories, never left at the directory root

---

## 7. LEARNINGS.md — Write to Disk (Non-Negotiable)

If your session summary has "LEARNINGS.md Candidates," append them to `LEARNINGS.md` before ending your session. Do not leave them only in the session summary.

- Add entries under the appropriate layer section
- Use the established format: title, date, context, problem, fix/pattern, prevention
- Add `(fixed)` to the title if the issue is now resolved
- **Tell Brach:** "LEARNINGS.md updated with N entries under [section]"

---

## 8. Iterative Improvement — Flag Preamble Issues

If you encounter a workflow problem that wasted significant time or would affect other agents, flag it in your session summary under "Preamble Improvement Candidates":

```
- [Issue]: Describe what went wrong
- [Fix]: What should be added/changed in the preamble
- [Scope]: All agents, or specific role?
```

The Operator reviews these after each session and updates the appropriate preamble file.
