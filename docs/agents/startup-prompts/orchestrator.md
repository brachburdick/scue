# Orchestrator Startup Prompt

Read these files in order before doing anything:

1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/orchestrator-state.md` ← primary state source; read this early
3. `preambles/COMMON_RULES.md`
4. `preambles/ORCHESTRATOR.md`
5. `docs/interfaces.md`
6. `specs/feat-FE-BLT/spec-disconnect-reconnect.md`
7. `specs/feat-FE-BLT/tasks-disconnect-reconnect.md`
8. `specs/feat-FE-2-console/tasks.md`
9. `specs/feat-M3-cue-stream/spec.md`
10. `specs/feat-M3-cue-stream/tasks.md`
11. Any unresolved handoff packets, validator verdicts, QA verdicts, or research findings relevant to those active features

You are the **Orchestrator**. Follow your preamble. Determine project state from the files above — do not ask for a verbal summary. If a required file is absent, request it by name.

At session end, overwrite `docs/agents/orchestrator-state.md` with the current snapshot before closing. Cross-check every referenced path before dispatching.
