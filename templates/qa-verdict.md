# QA Verdict: [FILL: TASK_ID or BUG_ID]

<!-- Written by: QA Tester agent -->
<!-- Consumed by: Orchestrator (to decide proceed vs. rework) -->
<!-- A bug fix is not COMPLETE until this verdict is PASS. -->

## Verdict: [FILL: PASS | FAIL]

## Environment

- Server: [FILL: how started, any flags — e.g., "uvicorn scue.main:app --reload"]
- Hardware: [FILL: board model, connection method, power state — or "mock_bridge.py" if simulated]
- Browser: [FILL: if FE tested — e.g., "Chrome 123, localhost:5173" — or "N/A"]

## Scenarios Executed

| Scenario | Status | Notes |
|----------|--------|-------|
| SC-001   | [FILL: PASS \| FAIL \| REQUIRES_OPERATOR] | [brief] |
| SC-002   | [FILL: PASS \| FAIL \| REQUIRES_OPERATOR] | [brief] |

<!-- Add rows for all executed scenarios. -->
<!-- REQUIRES_OPERATOR = no mock available; operator must perform physical action. -->

## Failures

<!-- Repeat this block for each FAIL scenario. Delete section if no failures. -->

### [FILL: SC-XXX]: [FILL: Scenario name]

- **Expected:** [FILL: from test scenario matrix "Then" items]
- **Observed:** [FILL: what actually happened, with timestamps if relevant]
- **Logs:** [FILL: relevant log excerpts — minimum needed to diagnose]
- **Severity:** [FILL: BLOCKING | DEGRADED | COSMETIC]

## Regression Check

- Previously passing scenarios still pass: [FILL: YES | NO — list regressions if NO]

## Mock Tool Gaps

<!-- List scenarios that could not be executed due to missing mock tooling. -->
<!-- "None" if all executed scenarios had available tooling. -->
- [FILL: SC-XXX] requires: [FILL: capability not yet available — e.g., "simulate USB-ETH disconnect without physical hardware"]

## Recommendation

[FILL: If PASS — "Proceed to next task." or note any observations worth tracking.]
[FILL: If FAIL — specific guidance for the next Developer handoff. Reference scenario IDs, not vague descriptions.]
