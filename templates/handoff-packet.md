# Handoff Packet: [FILL: TASK_ID, e.g., TASK-003]

## Objective
[FILL: One sentence — what must be true when this task is done.]

## Role
[FILL: Which role should execute this: Architect | Researcher | Designer | Developer]

## Scope Boundary
- Files this agent MAY read/modify:
  - [FILL: explicit file paths or glob patterns]
- Files this agent must NOT touch:
  - [FILL: explicit exclusions]

<!-- GUIDANCE: Be specific. "scue/layer1/" is better than "Layer 1 files." -->
<!-- If in doubt, list more exclusions rather than fewer. -->

## Context Files
<!-- GUIDANCE: Paths only — do not paste file contents into the handoff. -->
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/[FILL: ROLE].md`
- [FILL: additional paths the agent should read before starting]

## State Behavior (Required for FE tasks)
<!-- For tasks involving UI components that display differently based on system state: -->
<!-- Fill from existing specs or UI State Behavior artifacts, OR mark [ASK OPERATOR] for unknowns. -->
<!-- If this section has ANY [ASK OPERATOR] entries, resolve them with Brach BEFORE dispatching to a Developer. -->
<!-- For non-FE tasks or FE tasks with no state-dependent display, write "N/A". -->
[FILL: Link to ui-state-behavior artifact, inline table, or "N/A — no state-dependent display"]

## Constraints
- [FILL: Non-negotiable rules for this task]
- [FILL: E.g., "Do not modify any existing API endpoints"]
- [FILL: E.g., "All new functions must have type hints"]
- All pre-existing tests must continue to pass.

## Acceptance Criteria
- [ ] [FILL: Specific, testable condition]
- [ ] [FILL: Specific, testable condition]
- [ ] All pre-existing tests pass

<!-- GUIDANCE: Each criterion must be verifiable by the Validator agent. -->
<!-- Avoid subjective criteria like "code is clean" — use "no type errors reported by mypy." -->

## Dependencies
- Requires completion of: [FILL: TASK_ID(s) or "none"]
- Blocks: [FILL: TASK_ID(s) or "none"]

## Open Questions
<!-- CRITICAL: If this section is non-empty for a Developer handoff, STOP. -->
<!-- Resolve all open questions before dispatching to a Developer. -->
[FILL: Any unresolved items, or "None"]
