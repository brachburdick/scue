# Test Scenario Matrix: [FILL: AREA_NAME]

<!-- GUIDANCE: Store at specs/feat-[name]/test-scenarios.md (feature-specific) -->
<!-- or docs/test-scenarios/[area].md (cross-feature, e.g., bridge-lifecycle). -->
<!-- Written by: Architect (initial). Maintained by: QA Tester (additions from testing). -->

## Hardware/System Preconditions

<!-- Define the variable axes for this scenario area. -->
<!-- Example for bridge lifecycle: -->
- [FILL: Axis 1, e.g., "Board power"]: [FILL: possible states, e.g., "ON | OFF"]
- [FILL: Axis 2, e.g., "USB-ETH adapter"]: [FILL: possible states, e.g., "PLUGGED | UNPLUGGED"]
- [FILL: Axis 3, e.g., "Server"]: [FILL: possible states, e.g., "RUNNING | STOPPED"]
- [FILL: Axis 4, e.g., "Bridge"]: [FILL: possible states, e.g., "CONNECTED | CRASHED | WAITING_FOR_HARDWARE"]

## Scenarios

<!-- Scenarios come in pairs: disruption + recovery. -->
<!-- Every "When [thing breaks]" gets a corresponding "When [thing is restored]." -->
<!-- "Then" items are acceptance criteria with concrete thresholds (e.g., "within 5 seconds"). -->
<!-- Scenarios are cumulative — do not clear after a fix. FAIL→PASS stays as a regression check. -->

### SC-001: [FILL: Short descriptive name]

- **Given:** [FILL: Precondition state — e.g., "Server running, board ON, USB-ETH plugged, bridge connected"]
- **When:** [FILL: User/system action — e.g., "USB-ETH adapter is unplugged"]
- **Then:**
  - [ ] [FILL: Expected outcome 1 — with concrete threshold, e.g., "Hardware status updates within 2 seconds"]
  - [ ] [FILL: Expected outcome 2]
  - [ ] [FILL: Expected outcome 3]
- **Actual:** [Filled by QA Tester during execution]
- **Status:** [NOT_TESTED | PASS | FAIL | REQUIRES_OPERATOR]
- **Notes:** [Edge cases observed, timing details, related scenarios]

### SC-002: [FILL: Recovery from SC-001]

<!-- Every disruption scenario must have a matching recovery scenario. -->
- **Given:** [FILL: State after SC-001 — e.g., "Bridge in waiting_for_hardware, USB-ETH unplugged"]
- **When:** [FILL: Recovery action — e.g., "USB-ETH adapter is plugged back in"]
- **Then:**
  - [ ] [FILL: Expected recovery — e.g., "Bridge reconnects within 10 seconds"]
  - [ ] [FILL: Expected state — e.g., "All devices reappear, player data resumes"]
- **Actual:** [Filled by QA Tester during execution]
- **Status:** [NOT_TESTED | PASS | FAIL | REQUIRES_OPERATOR]
- **Notes:** [...]
