# UI State Behavior: Bridge Disconnect/Reconnect Lifecycle

> Maps system states to expected component display during the disconnect/reconnect
> lifecycle. This is the source of truth for what each component should show in each
> state. Developers implement against it; Validators and QA Testers verify against it.
>
> Addresses: "[OPEN] Hardware disconnect/reconnect flow is too slow with poor visual feedback"
> Operator feedback: "WAY too slow, needs better visual indication of what's actually happening."

---

## States Reference

These are the 7 system states covered by this artifact:

| # | State Key | Conditions | `dotStatus` |
|---|-----------|-----------|-------------|
| S1 | `running` (healthy) | `status=running`, `devices` non-empty, `isReceiving=true` | `connected` |
| S2 | `running` (no hardware) | `status=running`, `devices` empty, `isReceiving=false` | `connected` |
| S3 | `crashed` | `status=crashed`, `restartAttempt >= 1`, `nextRetryInS` may be set | `disconnected` |
| S4 | `starting` | `status=starting` | `disconnected` |
| S5 | `waiting_for_hardware` | `status=waiting_for_hardware`, `nextRetryInS` set (30s poll) | `degraded` |
| S6 | `running` (recovering) | `status=running`, `devices` empty (fresh start, data arriving) | `connected` |
| S7 | WS disconnected | `wsConnected=false` (backend unreachable) | `disconnected` |

### Distinguishing S2 vs S6

S2 and S6 are both `status=running` with empty devices. The difference is the *preceding* state:

- **S6 (recovering):** The bridge just transitioned to `running` from a non-running state (`crashed`, `starting`, `waiting_for_hardware`). The user needs reassurance that recovery is in progress and data will arrive shortly.
- **S2 (no hardware):** The bridge has been `running` for a sustained period with no devices. No recovery narrative needed.

`[NEW DERIVED STATE]` **`isRecovering`**: A boolean that is `true` for a fixed window after `status` transitions to `running` from any non-running state, then becomes `false`. Computation: set `true` on `running` entry from non-running; set `false` when either (a) `devices` becomes non-empty (hardware discovered), or (b) a 15-second timeout expires, whichever comes first.

**Recovery window: 15 seconds.** `isRecovering` becomes `false` when devices become non-empty OR the 15s timeout expires, whichever comes first. This matches one beat-link discovery cycle. If beat-link hasn't discovered devices within 15s of reaching `running`, it likely won't without intervention.

---

## Design Principle: Visual Feedback for Waits

Any system state where the user is waiting for >1 second MUST have a visual progress indicator. This includes:
- Countdown timers (crashed restart countdown, waiting_for_hardware poll countdown)
- Spinners or pulsing indicators (starting phase, recovery discovery)
- Animated progress (loading bars, pulsing dots)

Static text alone ('Starting...', 'Waiting...') is insufficient for waits >1 second. The user must see continuous motion confirming the system is alive and progressing.

---

## Component: TopBar StatusDot

The StatusDot reflects bridge process health. Color is driven by `dotStatus`.

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Green dot. Tooltip: "Bridge: running" | Current behavior, no change |
| S2: running (no hw) | Green dot. Tooltip: "Bridge: running" | Correct -- bridge process is healthy even without hardware |
| S3: crashed | Red dot. Tooltip: "Bridge: crashed -- restarting in Xs..." (use `nextRetryInS` if available, else "restarting...") | `[CHANGE]` Tooltip currently shows only "Bridge: crashed". Add countdown context. |
| S4: starting | Gray dot (disconnected). Tooltip: "Bridge: starting..." | Current behavior. `isStartingUp` shows StartupIndicator pill. |
| S5: waiting_for_hardware | Yellow dot (degraded). Tooltip: "Bridge: waiting for hardware -- checking in Xs..." (use `nextRetryInS`) | `[CHANGE]` Tooltip currently shows only "Bridge: waiting_for_hardware". Add countdown. |
| S6: running (recovering) | Green dot. Tooltip: "Bridge: running -- discovering devices..." | `[CHANGE]` Differentiate from steady-state S1/S2 tooltip. |
| S7: WS disconnected | Gray dot (disconnected). Tooltip: "Bridge: backend unreachable" | `[CHANGE]` Currently shows "Bridge: stopped". Should say "backend unreachable" when WS is down. |

---

## Component: TopBar TrafficDot

The TrafficDot reflects Pioneer hardware traffic. Currently hidden when `dotStatus === "disconnected"`.

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Cyan dot with `animate-ping` ripple. Tooltip: "Pioneer traffic: active -- Xms ago" | Current behavior, no change |
| S2: running (no hw) | Static gray dot (no ripple). Tooltip: "Pioneer traffic: none" | Current behavior, no change |
| S3: crashed | **Hidden** (dotStatus is `disconnected`) | Current behavior, no change |
| S4: starting | **Hidden** (dotStatus is `disconnected`) | Current behavior, no change |
| S5: waiting_for_hardware | Static gray dot (dotStatus is `degraded`, so TrafficDot is shown). Tooltip: "Pioneer traffic: none -- waiting for hardware" | `[CHANGE]` Currently shows "Pioneer traffic: none". Add "waiting for hardware" context. |
| S6: running (recovering) | Static gray dot with pulsing opacity animation initially, transitions to cyan with ripple when `isReceiving` becomes true. Tooltip: "Pioneer traffic: waiting for data..." while not receiving, then normal active tooltip. | `[CHANGE]` Differentiate from S2 while in recovery window. Pulsing animation confirms system is alive per design principle. |
| S7: WS disconnected | **Hidden** (dotStatus is `disconnected`) | Current behavior, no change |

---

## Component: TopBar StartupIndicator

The spinning pill shown during initial startup. Driven by `isStartingUp`.

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | **Hidden** | Current behavior |
| S2: running (no hw) | **Hidden** | Current behavior |
| S3: crashed | **Hidden** (`isStartingUp` is false once WS connected and bridge has left `starting`) | See note below |
| S4: starting | Shown: spinner + "Bridge starting..." | Current behavior |
| S5: waiting_for_hardware | **Hidden** | Current behavior |
| S6: running (recovering) | **Hidden** | Current behavior |
| S7: WS disconnected | Shown: spinner + "Connecting..." | Current behavior |

**Note on S3/S4 transitions:** When the bridge crashes and restarts, the sequence is `crashed` -> `starting` -> `running`. StartupIndicator shows during the `starting` phase of crash-restart cycles. Brief flicker is acceptable -- StatusBanner carries the continuous narrative. `isStartingUp` is computed as `!wsConnected || status === "starting"`, so it activates during each `starting` phase including crash-restart cycles. This provides visual confirmation that a restart attempt is in progress.

---

## Component: BridgeStatusPanel > StatusBanner

The StatusBanner is the primary narrative element. It must tell the user exactly what is happening and what to expect. Currently shows a single-line label per state (e.g., "Bridge: Connected", "Bridge: Crashed").

### Proposed StatusBanner Structure

Each state gets:
- **Status dot** (colored circle -- same as current)
- **Primary label** (bold, e.g., "Bridge: Connected")
- **Narrative text** (secondary line below the label -- explains what's happening and what comes next)
- **Countdown** (when applicable -- inline with narrative, live-updating from `nextRetryInS`)

**Transition animation:** 300ms fade transition between states using Tailwind `transition-opacity duration-300`. Softens rapid state transitions without adding complexity.

| System State | Dot Color | Primary Label | Narrative Text | Notes |
|---|---|---|---|---|
| S1: running (healthy) | Green | Bridge: Connected | `{deviceCount} device(s) on {networkInterface}` | `[CHANGE]` Add device count and interface name. Shows at a glance that hardware is working. |
| S2: running (no hw) | Green | Bridge: Connected | `No Pioneer devices on {networkInterface}. Waiting for hardware announcements.` | `[CHANGE]` Currently just "Connected". Add context about what's expected. |
| S3: crashed | Red | Bridge: Crashed | `Restart attempt {restartAttempt} of 3. Retrying in {nextRetryInS}s...` (countdown ticks every 1s) | `[CHANGE]` Currently just "Crashed". Add restart countdown and attempt number. If `nextRetryInS` is null, show "Restarting..." without countdown. Ticking countdown satisfies >1s visual feedback principle. |
| S4: starting | Yellow | Bridge: Starting | `Launching bridge subprocess...` with spinner/pulsing indicator | `[CHANGE]` Add spinner or pulsing indicator alongside text. Static "Launching..." alone is insufficient per design principle -- starting phase can exceed 1 second. |
| S5: waiting_for_hardware | Blue | Bridge: Waiting for Hardware | `Crash threshold reached. Checking for hardware in {nextRetryInS}s...` (countdown ticks every 1s) | `[CHANGE]` Currently just "Waiting for hardware...". Add countdown and explanation. Single message regardless of interface state. Interface-aware messaging deferred to follow-up (would require new bridge_status field). |
| S6: running (recovering) | Green | Bridge: Connected | `Bridge reconnected. Discovering devices on {networkInterface}...` with pulsing indicator | `[CHANGE]` Temporary message during recovery window. Pulsing indicator confirms discovery is active (satisfies >1s feedback principle). Transitions to S1 or S2 text when recovery window ends. |
| S7: WS disconnected | Gray | Backend Unreachable | `WebSocket connection lost. Reconnecting...` with spinner | `[CHANGE]` Currently shows "Stopped" or "Not Initialized" depending on last known state. Should clearly indicate WS disconnect regardless of last bridge status. Spinner confirms reconnection attempts are ongoing. |

### Crash Countdown Behavior (S3)

The `nextRetryInS` field in bridgeStore is updated by `bridge_status` WS messages. Between messages, the countdown should tick down visually (client-side decrement every 1 second) to give the user continuous feedback. When `nextRetryInS` reaches 0 or the status changes to `starting`, the narrative transitions.

`[NEW DERIVED STATE]` **`countdownSecondsRemaining`**: A client-side countdown that initializes from `nextRetryInS` on each `bridge_status` message and decrements every 1 second via `setInterval`. Resets when `status` changes or a new `nextRetryInS` arrives. Used in both S3 (crashed) and S5 (waiting_for_hardware) narratives.

### Waiting-for-Hardware Countdown Behavior (S5)

Same countdown mechanism as S3. The 30-second poll interval means the user sees "Checking for hardware in 28s... 27s... 26s..." ticking down. When it reaches 0, the manager either detects hardware and transitions to S4/S1, or the interface is absent and the countdown resets to ~30s.

---

## Component: BridgeStatusPanel > TrafficIndicator

The inline traffic indicator in the Bridge page (distinct from TopBar TrafficDot). Currently only shown when `status === "running" || status === "fallback"`.

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Green pulsing dot + "Pioneer traffic: active -- Xms ago" | Current behavior, no change |
| S2: running (no hw) | Gray dot + "Pioneer traffic: none" | Current behavior, no change |
| S3: crashed | **Hidden** | Current behavior (status is not running/fallback) |
| S4: starting | **Hidden** | Current behavior |
| S5: waiting_for_hardware | **Hidden** | Current behavior (status is not running/fallback). Acceptable -- the StatusBanner carries the narrative in this state. |
| S6: running (recovering) | Gray dot with pulsing animation + "Pioneer traffic: waiting for data..." initially, then transitions to green pulsing when `isReceiving` becomes true | `[CHANGE]` Minor: differentiate "waiting for data post-reconnect" from "no traffic at all". Pulsing animation confirms system is alive per design principle. |
| S7: WS disconnected | **Hidden** | Should hide when WS is down. `[CHANGE]` Currently the component checks `status` but not `wsConnected`. If WS drops while status was `running`, the component still renders with stale data. Add `wsConnected` guard. |

---

## Component: DeviceList

Shows device cards or an empty state. Currently has two empty states: "traffic detected but no devices" and "no devices found."

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Device cards showing all discovered devices. Header: "Devices ({count})" | Current behavior, no change |
| S2: running (no hw) | Empty state: "No Pioneer devices found on {interface}." Sub-text context-aware based on `routeCorrect`. | Current behavior, no change |
| S3: crashed | Empty state: "Bridge crashed. Devices will reappear after restart." | `[CHANGE]` Currently shows generic "No Pioneer devices found" because devices are cleared. Should reference the crash state so user knows why the list is empty. |
| S4: starting | Empty state: "Bridge starting. Waiting for device discovery..." with spinner | `[CHANGE]` Same rationale. Reference the starting state. Spinner satisfies >1s visual feedback principle. |
| S5: waiting_for_hardware | Empty state: "Waiting for hardware. Connect Pioneer equipment and adapter." | `[CHANGE]` Reference the waiting state and tell the user what action to take. |
| S6: running (recovering) | Empty state: "Bridge reconnected. Discovering devices on {interface}..." with a pulsing indicator. Transitions to S1 display when devices arrive. | `[CHANGE]` Recovery-specific empty state. Pulsing indicator satisfies >1s feedback principle. |
| S7: WS disconnected | Empty state: "Backend unreachable. Device information unavailable." | `[CHANGE]` Currently shows stale device list or "no devices" without explaining why. |

### DeviceList State-Aware Empty State

The DeviceList currently determines its empty-state message based on `isReceiving` and `routeCorrect`. For the disconnect/reconnect lifecycle, it also needs to consider `status` and `wsConnected` to show contextually appropriate messages.

`[NEW DERIVED STATE]` **Not needed.** All required data (`status`, `wsConnected`, `isReceiving`, `lastMessageAgeMs`, `routeCorrect`, `networkInterface`) already exists in `bridgeStore`. The DeviceList component needs to subscribe to `status` and `wsConnected` in addition to its current subscriptions, then branch its empty-state rendering accordingly.

**Priority order for empty-state messages (highest to lowest):**
1. `wsConnected === false` -> "Backend unreachable" message
2. `status === "crashed"` -> "Bridge crashed" message with restart context
3. `status === "starting"` -> "Bridge starting" message (with spinner)
4. `status === "waiting_for_hardware"` -> "Waiting for hardware" message
5. `isRecovering === true` (S6) -> "Discovering devices" message (with pulsing indicator)
6. `recentTraffic === true` -> "Traffic detected, no devices yet" (existing)
7. Default -> "No Pioneer devices found" (existing)

---

## Component: PlayerList

Shows player cards or an empty state. Simpler than DeviceList since it has a single empty-state message currently.

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Player cards showing all active players. Header: "Players ({count})" | Current behavior, no change |
| S2: running (no hw) | Empty state: "No active players." | Current behavior, no change |
| S3: crashed | Empty state: "Bridge crashed. Player data will resume after restart." | `[CHANGE]` Currently just "No active players." Should mirror DeviceList's crash-aware messaging. |
| S4: starting | Empty state: "Bridge starting..." with spinner | `[CHANGE]` Spinner satisfies >1s feedback principle. |
| S5: waiting_for_hardware | Empty state: "Waiting for hardware." | `[CHANGE]` |
| S6: running (recovering) | Empty state: "Waiting for player data..." with pulsing indicator | `[CHANGE]` Recovery-specific message. Pulsing indicator satisfies >1s feedback principle. |
| S7: WS disconnected | Empty state: "Backend unreachable." | `[CHANGE]` |

### PlayerList State-Awareness

Same approach as DeviceList: subscribe to `status` and `wsConnected`, branch empty-state text by priority.

**Priority order:**
1. `wsConnected === false` -> "Backend unreachable."
2. `status === "crashed"` -> "Bridge crashed. Player data will resume after restart."
3. `status === "starting"` -> "Bridge starting..." (with spinner)
4. `status === "waiting_for_hardware"` -> "Waiting for hardware."
5. `isRecovering === true` -> "Waiting for player data..." (with pulsing indicator)
6. Default -> "No active players."

---

## Component: HardwareSelectionPanel (RouteStatusBanner + ActionBar + InterfaceSelector)

The right-column panel with route status, restart button, and interface list. Each sub-component is addressed below.

### RouteStatusBanner

Dimmed with explanation text in non-running states. Layout stability is critical in a DJ performance environment -- elements must not jump around.

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Green banner: "Route OK: 169.254.255.255 -> {interface}" (if route correct). Yellow banner with "Fix Now" if mismatch. | Current behavior, no change |
| S2: running (no hw) | Same as S1 -- route state is independent of hardware presence | Current behavior, no change |
| S3: crashed | Dimmed banner (reduced opacity): last known route state. No "Fix Now" button active. Text: "Route status paused -- bridge restarting..." | `[CHANGE]` Currently shows stale route data or startup placeholder. During crash, route queries are stale and a fix attempt would fail. Dim the banner and explain. |
| S4: starting | Startup placeholder: "Route status -- waiting for startup..." (existing) | Current behavior. `isStartingUp` is true when `status === "starting"`. |
| S5: waiting_for_hardware | Dimmed banner: "Route status unavailable -- waiting for hardware" | `[CHANGE]` Currently shows startup placeholder (if `isStartingUp` is true) or stale data. Route queries may fail when interface is absent. Show a clear "unavailable" state. |
| S6: running (recovering) | Normal route banner. Queries auto-invalidated on `running` transition (TASK-003). Shows fresh route state. | Current behavior after TASK-003 fix. No change needed. |
| S7: WS disconnected | Startup placeholder: "Route status -- backend unreachable" | `[CHANGE]` Currently shows "waiting for startup..." which is misleading when WS is down. |

### ActionBar

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | "Bridge configuration is current." / "Interface changed. Restart to apply." + "Apply & Restart Bridge" button (enabled) | Current behavior, no change |
| S2: running (no hw) | Same as S1 | Current behavior, no change |
| S3: crashed | "Bridge crashed. Automatic restart in progress." + "Apply & Restart Bridge" button **disabled** with tooltip: "Wait for automatic restart to complete" | `[CHANGE]` Button should be disabled during crash-restart to prevent user from interfering with the automatic recovery sequence. |
| S4: starting | "Bridge starting..." + button **disabled** | `[CHANGE]` Prevent double-start. |
| S5: waiting_for_hardware | "Waiting for hardware." + **"Force Restart"** button (enabled). Triggers immediate `restart()` call bypassing the poll timer. Different label from "Apply & Restart Bridge" to signal different intent. | `[CHANGE]` In a live performance context, the DJ wants to force recovery NOW, not wait 30 seconds. |
| S6: running (recovering) | "Bridge reconnected. Refreshing data..." + button **disabled** briefly, then enabled | `[CHANGE]` Brief disable during recovery to prevent premature restart. |
| S7: WS disconnected | "Backend unreachable." + button **disabled** | `[CHANGE]` Cannot restart bridge when backend is down. |

### InterfaceSelector

| System State | Expected Display | Notes |
|---|---|---|
| S1: running (healthy) | Interface list with scores, current selection highlighted. Refresh button. | Current behavior, no change |
| S2: running (no hw) | Same as S1 | Current behavior, no change |
| S3: crashed | Interface list still visible but **selection disabled** (no clicking to change interface during crash-restart). Refresh button enabled (user may want to check if interfaces changed). Subtle overlay or reduced opacity. | `[CHANGE]` Prevent interface changes during automatic recovery. |
| S4: starting | Startup placeholder: "Waiting for application startup..." | Current behavior (`isStartingUp` gate) |
| S5: waiting_for_hardware | Interface list visible, **selection enabled**. User can change interface while waiting -- useful if they want to switch to a different adapter. | No change from current behavior (when not gated by `isStartingUp`). `[CONCERN]` Currently, `isStartingUp` may be false in `waiting_for_hardware` state (WS is connected, status is not `starting`), so the interface list loads. Need to verify this works correctly. |
| S6: running (recovering) | Normal interface list. Queries auto-invalidated, scores update. | Current behavior after TASK-003. |
| S7: WS disconnected | Startup placeholder: "Waiting for application startup..." | Current behavior (`isStartingUp` is true when WS disconnected). Text could be more specific but low priority. |

---

## Compound States

These combinations produce display behavior that differs from what individual states would suggest.

### crashed + restartAttempt approaching threshold

When `restartAttempt === 2` (one more crash will trigger `waiting_for_hardware`), the StatusBanner narrative should warn: "Restart attempt 2 of 3. If next attempt fails, bridge will enter slow-poll mode."

This gives the user advance notice that the system is about to change behavior, rather than the `waiting_for_hardware` state appearing without explanation.

### waiting_for_hardware + wsConnected=false

If the WebSocket disconnects while in `waiting_for_hardware`, the S7 (WS disconnected) display takes priority across all components. The `waiting_for_hardware` countdown is irrelevant when the backend is unreachable.

### running (recovering) + isReceiving=true

When `isReceiving` becomes true during the recovery window, the TrafficDot and TrafficIndicator should transition immediately to their active states. The StatusBanner narrative should update to "Bridge reconnected. {deviceCount} device(s) discovered." as soon as devices appear, then drop the recovery narrative entirely (transition from S6 to S1).

---

## Transition Narrative: Full Crash-Restart Lifecycle

This section describes the user-visible sequence during a complete hardware disconnect and reconnect. This is the "story" the UI tells.

### Phase 1: Hardware Disconnects (S1 -> crash detection ~20s)

1. Pioneer traffic stops. TrafficDot stops pinging within 3s. TrafficIndicator shows "Pioneer traffic: none."
2. Devices clear from DeviceList within 5s (adapter cleared on crash, frontend gates on `status=running`).
3. Players clear from PlayerList within 5s.
4. Bridge has not yet crashed -- it's still `running` with no traffic. This is S2.
5. After ~20s of silence, bridge health check fires. Status transitions to `crashed`.

### Phase 2: Crash-Restart Cycle (S3 -> S4 -> S3, up to 3 attempts)

6. **S3:** StatusBanner: red dot, "Bridge: Crashed -- Restart attempt 1 of 3. Retrying in Xs..." (countdown ticking)
7. Countdown ticks down. StatusDot: red. DeviceList: "Bridge crashed. Devices will reappear after restart."
8. Countdown reaches 0. Status transitions to `starting`.
9. **S4:** StatusBanner: yellow dot, "Bridge: Starting -- Launching bridge subprocess..." with spinner/pulsing indicator.
10. StartupIndicator pill appears briefly in TopBar (shows during starting phase of crash-restart).
11. If restart succeeds: -> S6 (recovering). If restart fails: -> S3 with `restartAttempt` incremented.
12. On attempt 2, StatusBanner: "Restart attempt 2 of 3. If next attempt fails, bridge will enter slow-poll mode."
13. On attempt 3 failure: -> S5.

### Phase 3: Waiting for Hardware (S5)

14. **S5:** StatusBanner: blue dot, "Bridge: Waiting for Hardware -- Crash threshold reached. Checking for hardware in 28s..." (countdown ticking)
15. Countdown ticks from 30 to 0 every second.
16. StatusDot: yellow (degraded). TrafficDot: gray.
17. DeviceList: "Waiting for hardware. Connect Pioneer equipment and adapter."
18. ActionBar: "Force Restart" button enabled for immediate restart if user plugs in hardware.
19. At countdown 0: manager checks interface. If absent: countdown resets to 30. If present: -> S4.

### Phase 4: Hardware Reconnects (S5 -> S4 -> S6 -> S1)

20. User plugs in hardware / powers on board. Either waits for poll or clicks "Force Restart".
21. Next poll (or forced restart) detects interface. Status -> `starting` -> `running`.
22. **S6:** StatusBanner: green dot, "Bridge: Connected -- Bridge reconnected. Discovering devices on {interface}..." with pulsing indicator.
23. TrafficDot transitions from gray (pulsing) to cyan with ripple as traffic arrives.
24. Devices populate in DeviceList. Players populate in PlayerList.
25. Route queries auto-invalidate. RouteStatusBanner updates.
26. Recovery window ends (devices found or 15s timeout). Transition to S1 (or S2 if no devices after 15s).

---

## Summary of New Derived State

| Name | Type | Computation | Used By |
|---|---|---|---|
| `isRecovering` | `boolean` | `true` when `status` transitions to `running` from non-running. `false` when devices become non-empty OR 15-second timeout expires, whichever comes first. | StatusBanner, TrafficDot, TrafficIndicator, DeviceList, PlayerList |
| `countdownSecondsRemaining` | `number \| null` | Initialized from `nextRetryInS` on each `bridge_status` message. Decremented every 1s via `setInterval`. Reset on `status` change or new `nextRetryInS`. | StatusBanner (narrative text), TopBar tooltips |

---

## Follow-Up Items (Out of Scope)

1. **Faster interface detection in waiting_for_hardware**: Currently polls every 30s. The interface-availability check (`socket.if_nametoindex()`) is cheap -- reduce poll interval to 5s when watching for interface appearance. One-line change in `manager.py`. Would make auto-detection of plugged-in hardware feel nearly instant.

2. **Beat-link discovery cycle optimization**: Investigate whether the 15s recovery window can be shortened by tuning beat-link's device discovery parameters. Current CDJ announcement interval is ~1-2s; devices typically appear within 3-5s. The 15s fallback is conservative.

3. **Interface-aware waiting_for_hardware messaging**: Add `interface_available: boolean` field to `bridge_status` so the frontend can distinguish "interface present but no traffic" from "interface absent." Would enable two-message differentiation in the StatusBanner (e.g., "Connect adapter" vs. "Checking for Pioneer devices"). Requires a contract change in `bridge_status`.
