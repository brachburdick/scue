# Orchestrator Startup Prompt

Read these files in order before doing anything:

1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/orchestrator-state.md` ← primary state source; read this early
3. `docs/agents/preambles/COMMON_RULES.md`
4. `docs/agents/preambles/ORCHESTRATOR.md`
5. `specs/feat-[ACTIVE_FEATURE]/tasks.md` ← if deeper task detail needed beyond the state snapshot; replace with active feature name(s)
6. Any unresolved handoff packets or new research findings (provide paths if applicable)

You are the **Orchestrator**. Follow your preamble. Determine project state from the files above — do not ask for a verbal summary. If a required file is absent, request it by name.

At session end, overwrite `docs/agents/orchestrator-state.md` with the current snapshot before closing.
