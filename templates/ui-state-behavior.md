# UI State Behavior: [FILL: Component or View Name]

> Maps system states to expected component display. This is the source of truth for what
> a component should show in each state. Developers implement against it; Validators and
> QA Testers verify against it.

## Component: [FILL: Component Name]

| System State | Expected Display | Notes |
|---|---|---|
| [FILL: e.g., bridge connected, hardware present] | [FILL: what this component shows] | |
| [FILL: e.g., bridge connected, hardware absent] | [FILL] | |
| [FILL: e.g., bridge disconnected] | [FILL] | |
| [FILL: e.g., bridge reconnecting] | [FILL] | |

<!-- Repeat table for each component in scope. -->
<!-- Only include states relevant to each component. Not all states apply to all components. -->
<!-- If a state's expected display is unknown, write [ASK OPERATOR] — do not leave it blank or guess. -->

## States Reference (delete irrelevant rows)

These are common SCUE system states. Include only those relevant to the component(s) above.

| Dimension | Possible Values |
|---|---|
| Bridge process | `connected`, `disconnected`, `reconnecting` |
| Pioneer hardware | `present` (traffic flowing), `absent` (no traffic), `unknown` |
| Route state | `active`, `inactive`, `mismatch`, `unknown` |
| Playback | `playing`, `stopped`, `loading` |
| Data freshness | `live`, `stale` (no update within expected interval) |
