# Bug Log — Frontend

Append-only log of bugs found and fixed in the frontend (React/TS/Vite/Tailwind).
Record every fix, no matter how small — patterns emerge over time.

**Format:**
```
### Short title
Date: YYYY-MM-DD
Milestone: FE-X (or N/A)
Symptom: What did the user see or what broke?
Root cause: Why did it happen?
Fix: What was changed and where?
File(s): path/to/file.tsx
```

---

### TopBar StatusDot cycles green/yellow without Pioneer hardware
Date: 2026-03-17
Milestone: FE-BLT
Symptom: The bridge status dot in the TopBar oscillated between green and yellow every ~5s even when the bridge was running normally but no Pioneer devices were connected.
Root cause: `computeDotStatus` required BOTH `status === "running"` AND `isReceiving === true` to return `"connected"`. Without hardware, the bridge sends one startup `bridge_status` message then goes silent. The `pioneer_status` watchdog fires every 2s; after the message age exceeded 5s, `isReceiving` was set to `false`, flipping the dot to `"degraded"` (yellow). On the next WS heartbeat it briefly ticked back then dropped again.
Fix: Removed `isReceiving` from `computeDotStatus`. Dot is now `"connected"` when `status === "running"`, `"degraded"` when `status === "fallback"`, and `"disconnected"` otherwise. Pioneer traffic freshness is retained in the store and shown as a dedicated indicator in the BLT panel.
File(s): frontend/src/stores/bridgeStore.ts

### Route status shows stale data after Apply & Restart Bridge
Date: 2026-03-17
Milestone: FE-BLT
Symptom: After clicking "Apply & Restart Bridge," the RouteStatusBanner continued to show the old route warning even when the route had been fixed during bridge startup.
Root cause: `useRestartBridge` mutation had no `onSuccess` handler, so the `["network", "route"]` TanStack Query cache was never invalidated after the restart. The stale response remained until the next automatic refetch.
Fix: Added `onSuccess: () => queryClient.invalidateQueries({ queryKey: ["network", "route"] })` to `useRestartBridge`.
File(s): frontend/src/api/network.ts

### DeviceList empty-state message flickers between "traffic detected" and "no devices"
Date: 2026-03-17
Milestone: FE-BLT
Symptom: With the bridge running and Pioneer hardware active, the DeviceList cycled between "Pioneer traffic detected, but no devices discovered yet." and "No Pioneer devices found. Check cable, interface selection, and route status above." even when the route was confirmed correct and the interface was active.
Root cause: The branch was gated solely on `isReceiving`, which is set by the `pioneer_status` watchdog. Pioneer CDJs send announcement bursts; `isReceiving` goes `true` during a burst then briefly `false` between them. Each false→true transition flipped the message. Additionally, the fallback "No Pioneer devices found" state always showed "Check cable, interface selection..." regardless of whether the route was known to be correct.
Fix: Introduced `recentTraffic = isReceiving || (lastMessageAgeMs >= 0 && lastMessageAgeMs < 8000)`. The 8-second grace window keeps the "traffic detected" message stable between bursts. Also made the "No Pioneer devices found" sub-text context-aware: shows "Route mismatch detected — fix above..." when `routeCorrect === false`, and "Check cable, interface, route..." only when route state is unknown.
File(s): frontend/src/components/bridge/DeviceList.tsx

### [PRESUMED RESOLVED] Pioneer traffic indicator too slow and flickers during active playback
Date: 2026-03-17
Resolved: 2026-03-18 (presumed — see note)
Milestone: FE-BLT (originally; page/component renamed from BLT → Bridge)
Symptom: The TrafficDot indicator in the TopBar and the "Pioneer traffic detected" state in DeviceList flicker on and off even when a track is actively playing on the board. The indicator is also noticeably slow to light up when traffic begins — there is a visible lag before the dot activates.
Root cause: Not formally investigated. Brach notes this is presumed resolved — likely as a side effect of infrastructure changes made during the BLT→Bridge page rename and related multi-agent architecture work (2026-03-17/18). Possible root causes at the time: (1) watchdog polling interval too coarse; (2) `is_receiving` threshold mismatched with CDJ burst rate; (3) 8-second grace window in DeviceList not propagated to TopBar TrafficDot.
Fix: Not explicitly fixed — presumed resolved by associated refactors. If flicker re-emerges, investigate: watchdog interval in `scue/api/ws.py`, `is_receiving` decay logic in `scue/bridge/adapter.py`, and whether TrafficDot in TopBar reads `isReceiving` directly vs. using the grace-window computed value.
File(s): scue/bridge/adapter.py (watchdog), frontend/src/components/layout/TopBar.tsx (TrafficDot), frontend/src/components/bridge/BridgeStatusPanel.tsx (TrafficIndicator)
Note: Bug log was not updated when resolved — flagged by Orchestrator on 2026-03-18. The [OPEN] status was discovered during first Orchestrator session. Brach attributed the oversight to the BLT→Bridge rename happening concurrently with the fix.

### RouteStatusBanner and ActionBar rendered below interface list instead of above
Date: 2026-03-17
Milestone: FE-BLT
Symptom: In the Hardware Selection panel, the route status banner and Apply & Restart button appeared at the bottom of the panel, below the full interface list, making them hard to find.
Root cause: Component render order in `HardwareSelectionPanel` placed `InterfaceSelector` first, then `RouteStatusBanner` and `ActionBar`. No logic error — just wrong visual priority.
Fix: Reordered so `RouteStatusBanner` and `ActionBar` render before `InterfaceSelector`.
File(s): frontend/src/components/bridge/HardwareSelectionPanel.tsx

---

### [FIXED] Route mismatch warning does not auto-clear on reconnect
Date: 2026-03-18
Fixed: 2026-03-19
Milestone: FE-BLT
Symptom: After USB-Ethernet adapter is unplugged and replugged, or after board power cycle, the RouteStatusBanner continues to show "Route mismatch: 169.254.255.255 → none (should be en7)" even after the bridge successfully reconnects on en7. The warning only clears if the user manually clicks "Fix Now."
Root cause: The `["network", "route"]` and `["network", "interfaces"]` TanStack Query caches were never invalidated on bridge state transitions. They only refetched on window focus, mount, or manual mutation `onSuccess` handlers. When the bridge reconnected via WebSocket, stale query data persisted.
Fix: Added bridge status transition tracking in `ws.ts` using a module-level `prevBridgeStatus` variable. When `bridge_status.status` transitions to `"running"` from any non-running state (including `null` initial), both `["network", "route"]` and `["network", "interfaces"]` queries are invalidated. Also extracted `QueryClient` to a shared module (`api/queryClient.ts`) so `ws.ts` can import it without React context.
File(s): frontend/src/api/ws.ts, frontend/src/api/queryClient.ts, frontend/src/main.tsx

### [FIXED] Interface score stays at 5 for active en7 interface
Date: 2026-03-18
Fixed: 2026-03-19
Milestone: FE-BLT
Symptom: The hardware interface selector shows en7 with a score of 5 regardless of connection state. When the board is connected and traffic is flowing on en7, the score should reflect the healthy state (higher or marked as active). "Fix Now" updates the route status box but the score remains 5.
Root cause: `_score_interface()` in `scue/network/route.py` only considered static interface properties (link-local address, interface type, private IP). It had no awareness of live bridge context -- whether Pioneer traffic was actively flowing on the interface or whether the macOS broadcast route pointed to it.
Fix: Added two optional live-context parameters to `_score_interface()` and `enumerate_interfaces()`: `active_traffic_interface` (+10 when Pioneer traffic is flowing) and `route_correct_interface` (+5 when macOS route is correct). The API endpoint reads bridge state via `init_network_api()` injection and passes context as plain values -- no direct coupling between network and bridge modules.
File(s): scue/network/route.py, scue/api/network.py, scue/bridge/manager.py, scue/main.py

### Devices and players show stale data after hardware disconnect (fixed)
Date: 2026-03-18
Fixed: 2026-03-19
Milestone: FE-BLT
Symptom: When Pioneer hardware disconnects (adapter unplugged, board powered off), the DeviceList and PlayerList continue to show the last-known device and player data. They do not clear or show a "disconnected" state. Stale BPM and pitch values remain visible.
Root cause: Two issues: (1) The backend bridge adapter (`_devices`/`_players` dicts) is never cleared on disconnect, so `to_status_dict()` continues to include stale device/player data in `bridge_status` payloads even in non-running states. (2) The frontend `bridgeStore.setBridgeState()` blindly accepted devices/players from every `bridge_status` message regardless of bridge status. (3) `setWsConnected(false)` did not clear devices/players, so a WebSocket disconnect left stale data in place. (4) `PlayerList` returned `null` on empty state instead of showing an empty-state message.
Fix: Backend: Added `BridgeAdapter.clear()` method that resets `_devices` and `_players` (preserves callbacks). Called in `BridgeManager._cleanup()` (primary path on every crash/stop) and `BridgeManager.start()` (belt-and-suspenders). Also reset `_last_pioneer_message_time = 0.0` in `start()` so `pioneer_status.is_receiving` is false until fresh traffic arrives. Frontend (prior session): `setBridgeState()` force-clears devices/players when `status !== "running"`. `setWsConnected(false)` clears devices/players. PlayerList renders empty-state message.
File(s): scue/bridge/adapter.py, scue/bridge/manager.py, frontend/src/stores/bridgeStore.ts, frontend/src/components/bridge/PlayerList.tsx

### [OPEN] Hardware disconnect/reconnect flow is too slow with poor visual feedback
Date: 2026-03-19
Milestone: FE-BLT
Symptom: When Pioneer hardware is powered off, the UI takes too long to reflect the change and provides poor visual indication of what's actually happening. The full sequence (traffic lost → device lost → traffic briefly resumes → traffic lost again → bridge crashes → restarts → reconnects) takes ~45 seconds with no clear user-facing narrative. After the bridge reconnects, stale devices/players reappear. A crash-restart loop repeats every ~2 minutes while hardware remains off. The user has no clear indication of system state during this process.
Root cause: Multiple interacting issues across backend and frontend: (1) backend adapter never clears device/player state on crash/disconnect; (2) bridge crash detection is slow (~20s before crash is declared); (3) bridge enters a crash-restart loop every ~2 min when hardware is off rather than settling into a stable "no hardware" state; (4) frontend has no transitional states or progress indication during the crash-restart sequence; (5) related open bugs (route mismatch not clearing, interface score not updating, false-positive connected state during restart) compound the confusion.
Fix: None yet. Needs holistic assessment — likely requires Architect audit of the disconnect/reconnect data flow (what the backend sends, when, and what states it transitions through) plus Designer work on what the UX should look like across all these transitional states.
File(s): TBD — cross-cutting: scue/bridge/adapter.py, scue/bridge/manager.py, frontend/src/stores/bridgeStore.ts, frontend/src/components/bridge/*

### [OPEN] Route status and bridge connection show false-positive during restart
Date: 2026-03-18
Milestone: FE-BLT
Symptom: During a crash-restart cycle, the route status banner and bridge connection status briefly show a valid/connected state for a moment during the restart sequence, then flicker back to the correct state. Observed in console: "Route warning: route: bad address: en7" appears after "Bridge crashed → starting", suggesting the UI momentarily registers the new subprocess attempt as a healthy state before it fails.
Root cause: Not yet investigated. Bridge state transitions during restart may emit intermediate events that the FE interprets as connected.
Fix: None yet. Non-blocker.
File(s): TBD

### [FIXED] Console logs disappear when bridge connection is reestablished
Date: 2026-03-18
Fixed: 2026-03-19
Milestone: FE-2
Symptom: When the bridge reconnects after a disconnect, previously displayed console log entries disappear from the console panel. The console effectively clears on reconnect.
Root cause: No explicit clearing of entries was found in any reconnect path. The most likely cause was the module-level mapper state in `consoleMapper.ts` — on WS reconnect, stale `prev*` variables caused incorrect diff detection, producing malformed or missing console entries that could make the console appear to have lost its history. Resolved by TASK-003 (TR-6), which added `resetMapperState()` in `ws.ts` `onOpen()` handler. Investigation confirmed: (1) no `clearEntries()` call in any reconnect/WS lifecycle path, (2) Console component is unconditionally mounted in Shell.tsx — no unmount/remount on bridge state change, (3) Zustand store entries persist across ConsolePanel collapse/expand. A secondary contributing factor is ring buffer capacity (200 entries) — during crash-restart loops, rapid `bridge_status` messages can push older entries out, but this is a capacity concern, not a disappearance bug.
Fix: Resolved by TASK-003 (`resetMapperState()` in WS `onOpen()`). No additional code changes needed.
File(s): frontend/src/api/ws.ts, frontend/src/utils/consoleMapper.ts, frontend/src/stores/consoleStore.ts

---

### Frontend disconnect preserves stale bridge status
Date: 2026-03-20
Milestone: FE-BLT
Severity: LOW (misleading, not broken)
Symptom: On WS disconnect, the `status` field in bridgeStore is NOT cleared, so `dotStatus` (derived from `status`) stays green even though the connection is lost. Users see a green status dot despite being disconnected.
Root cause: `bridgeStore.ts:136-157` on WS disconnect clears devices, players, isRecovering, and countdownSecondsRemaining, and recomputes isStartingUp — but does NOT clear `status`. So `status` can remain `"running"` after disconnect. The TopBar does show a startup indicator when `isStartingUp` is true (partially mitigating), but the dot color is misleading.
Fix: Clear `status` on WS disconnect (set to `null` or a distinguished `"disconnected"` value), or derive `dotStatus` to account for WS connection state.
File(s): frontend/src/stores/bridgeStore.ts (~line 136-157)
Source: External code review 2026-03-20

### WebSocket URL hardcoded to port 8000
Date: 2026-03-20
Milestone: FE-BLT
Severity: MEDIUM (blocks any non-default deployment)
Symptom: WebSocket connection fails if backend runs on any port other than 8000. REST API works fine (uses Vite's same-origin proxy), but WS bypasses the proxy.
Root cause: `ws.ts:14` hardcodes `ws://${window.location.hostname}:8000/ws`. REST uses Vite's proxy (same-origin `/api`), but WS bypasses the proxy with an explicit port. This breaks on any deployment where the backend isn't on port 8000.
Fix: Derive WS URL from `window.location` for both host and port, or configure via environment variable, or route through the Vite proxy if possible.
File(s): frontend/src/api/ws.ts (~line 14)
Source: External code review 2026-03-20

### HTML entity strings rendered as literal text in sort indicators
Date: 2026-03-16
Milestone: FE-3
Symptom: The "Analyzed" column header displayed the raw string `&#X25BC;` instead of a ▼ symbol. Clicking toggled it to `&#X25B2;` instead of ▲. Other unsorted columns showed `&#x21C5;` as literal text on page reload.
Root cause: The `SortIndicator` component used HTML entity strings (`"&#x25B2;"`) as JSX text content. React renders string literals as-is — it does not interpret HTML entities inside `{}` expressions. Only entities written directly in JSX markup (outside `{}`) are parsed by the JSX compiler.
Fix: Replaced HTML entity strings with actual Unicode characters: `"⇅"`, `"▲"`, `"▼"`.
File(s): frontend/src/components/tracks/TrackTable.tsx
