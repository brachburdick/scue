# SCUE Agent Workflow Documentation

## Quick Start

Starting a new agent session? Here's the protocol:

1. Determine the agent role (Orchestrator, Architect, Researcher, Designer, Developer, or Validator)
2. Start a new conversation (never reuse existing ones)
3. Tell the agent to read files in this order:
   - `AGENT_BOOTSTRAP.md` (project root — always first)
   - `docs/agents/preambles/COMMON_RULES.md` (always)
   - `docs/agents/preambles/[ROLE].md` (role-specific)
   - Any skill files from `skills/` referenced in the handoff
4. Provide the handoff packet
5. Wait for the agent to confirm understanding before proceeding

## File Index

| File | Purpose |
|------|---------|
| `AGENT_BOOTSTRAP.md` (project root) | Entry point for every agent session |
| `preambles/COMMON_RULES.md` | Behavioral contract shared by all roles |
| `preambles/ORCHESTRATOR.md` | Orchestrator-specific rules |
| `preambles/ARCHITECT.md` | Architect-specific rules |
| `preambles/RESEARCHER.md` | Researcher-specific rules |
| `preambles/DESIGNER.md` | Designer-specific rules (UI/UX) |
| `preambles/DEVELOPER.md` | Implementation agent rules |
| `preambles/VALIDATOR.md` | Validation agent rules (pass/fail verdicts) |
| `AGENT_ROSTER.md` | Role definitions, scope boundaries, context injection guide |
| `HANDOFF_CONTRACTS.md` | Format specs for all inter-agent artifacts |
| `ORCHESTRATOR_PROMPT.md` | Full system prompt for Orchestrator sessions |
| `TRANSITION_PLAN.md` | Original transition guide (historical reference) |

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `templates/` (project root) | Artifact schema templates — use for all structured outputs |
| `skills/` (project root) | Domain knowledge skill files |
| `specs/feat-[name]/` | Feature specs, plans, tasks |
| `specs/feat-[name]/sessions/` | Session summaries and validator verdicts for a feature |
| `research/` | Technology investigation findings (archive) |
| `sessions/YYYY-MM-DD/` | Non-feature session summaries (legacy + ad-hoc) |

## Roles

| Role | Reads Code? | Writes Code? | Primary Output |
|------|-------------|--------------|----------------|
| Orchestrator | No | No | Handoff packets, priority ordering |
| Architect | Yes (read-only) | No | Specs, plans, tasks, ADRs |
| Researcher | No | No | Research findings |
| Designer | No | No | UI specs, component hierarchies |
| Developer | Yes (scoped) | Yes (scoped) | Code changes, session summaries |
| Validator | Yes (read-only) | No | Pass/fail verdicts |

## Workflow Cycle

```
Orchestrator → [Handoff Packet] → Architect/Researcher/Designer/Developer
                                         │
                                    Developer (per task)
                                         │
                                    Validator (mandatory)
                                         │
                                   PASS → next task
                                   FAIL → Developer retry
```

## Archive

`archive/` contains previous versions of workflow documents kept for historical reference:
- `AGENT_PREAMBLE_v1.md` — Original single preamble (replaced by role-specific preambles)
- `AGENT_PREAMBLE_ADDENDUM_v1.md` — First addendum (merged into Developer preamble)

## Updating the Preambles

Preambles are living documents. After each session, the Operator reviews learnings from the agent's session summary and updates the appropriate preamble file. Protocol-level issues go to `PROTOCOL_IMPROVEMENTS.md` for batch review.
