# Session Summary: [FILL: TASK_ID]

## Role
[FILL: Which role performed this session]

## Objective
[FILL: Restate from handoff packet]

## Status
[FILL: COMPLETE | PARTIAL | BLOCKED]

## Work Performed
- [FILL: Bullet list of what was actually done]

## Files Changed
- `[FILL: path/to/file]` — [FILL: what changed and why]

<!-- GUIDANCE: Every file modified must be listed here. The Validator checks this -->
<!-- against the handoff packet's Scope Boundary. Omissions will cause a FAIL verdict. -->

## Interfaces Added or Modified
- [FILL: Any new or changed function signatures, API endpoints, type definitions]
- [FILL: Include the exact signature, not prose description]
- [FILL: Or "None" if no interface changes]

<!-- GUIDANCE: If you added or modified types that appear in docs/CONTRACTS.md, -->
<!-- flag them here. The Architect will coordinate the contract update. -->

## Decisions Made
- [FILL: Decision]: [Rationale]. Alternative considered: [what was rejected and why].

<!-- GUIDANCE: Every judgment call must be documented. "I chose X over Y because Z." -->
<!-- This is how the Orchestrator and Validator understand your intent. -->

## Scope Violations
- [FILL: Any moment the agent needed to touch out-of-scope files. "None" is a valid answer.]

## Remaining Work
- [FILL: What's left undone, if status is PARTIAL or BLOCKED]

## Blocked On
- [FILL: If status is BLOCKED — what specific question or dependency is unresolved]
- [FILL: Include a draft Research Request if applicable]

## Missteps
- [FILL: Tool failures, wrong commands, retries, or environment surprises encountered during this session. Be specific: what was tried, what failed, what worked instead. "None" is valid.]
- [FILL: E.g., "Ran `python app.py` — failed, needed `.venv/bin/python`. Ran `pip install` — failed, needed venv activation first."]

<!-- GUIDANCE: This section feeds the Orchestrator's pattern detection. -->
<!-- If the same misstep appears across 2+ sessions, the Orchestrator proposes a fix. -->

## Learnings
- [FILL: Gotchas, surprises, or domain knowledge worth capturing in a skill file]
