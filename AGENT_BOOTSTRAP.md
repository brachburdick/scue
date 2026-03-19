# SCUE

Automated lighting/laser/visual cue generation for live DJ sets.

## Quick Reference
- **Stack:** Python 3.11+ / FastAPI / asyncio, React 19 / TypeScript / Vite / Tailwind, Java (beat-link bridge)
- **Current milestone:** See `docs/MILESTONES.md`
- **Active specs:** `specs/`
- **Known pitfalls:** `LEARNINGS.md` — read before starting work

## Your Role Setup
1. Read this file first.
2. Read `docs/agents/preambles/COMMON_RULES.md`.
3. Read your role-specific preamble from `docs/agents/preambles/[ROLE].md`.
   Available roles: ORCHESTRATOR, ARCHITECT, RESEARCHER, DESIGNER, DEVELOPER, VALIDATOR, QA_TESTER
4. Read any skill files referenced in your handoff packet from `skills/`.
5. Read your handoff packet or task-specific context.

## Project Layout
- `docs/` — Architecture, contracts, decisions, milestones, bugs
- `docs/test-scenarios/` — Cross-feature test scenario matrices (bridge lifecycle, network resilience, etc.)
- `specs/feat-[name]/` — Feature specs, plans, tasks, session logs, feature-specific test scenarios
- `templates/` — Artifact schema templates (use for all structured outputs)
- `skills/` — Domain knowledge files
- `research/` — Research findings archive
- `scue/` — Python backend (5-layer architecture)
- `frontend/` — React/TypeScript frontend
- `bridge-java/` — Java beat-link bridge subprocess
- `config/` — YAML configuration (effects, fixtures, routing, palettes)

## Top 3 Things Agents Get Wrong in This Project
1. Using bare `python` instead of `.venv/bin/python` — the system Python has no project deps
2. Modifying files outside their assigned scope without stopping to flag it
3. Overwriting Pioneer-sourced data with SCUE-derived data instead of logging divergence
