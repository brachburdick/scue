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

### [OPEN] Pioneer traffic indicator too slow and flickers during active playback
Date: 2026-03-17
Milestone: FE-BLT
Symptom: The TrafficDot indicator in the TopBar and the "Pioneer traffic detected" state in DeviceList flicker on and off even when a track is actively playing on the board. The indicator is also noticeably slow to light up when traffic begins — there is a visible lag before the dot activates.
Root cause: Not yet investigated. Likely a combination of: (1) the `pioneer_status` watchdog polling interval on the Python side being too coarse for continuous feedback; (2) the `is_receiving` flag being set based on a time-window check that may have a threshold mismatched with the CDJ announcement burst rate; (3) the 8-second `lastMessageAgeMs` grace window in DeviceList partially masks the flicker for the device list message but does not help the TopBar TrafficDot, which reads `isReceiving` directly.
Fix: Not yet investigated. Possible directions: reduce the watchdog polling interval, change `is_receiving` to use a longer decay window on the Python side, or have the frontend compute `isReceiving` from `lastMessageAgeMs` with a smoother threshold rather than relying on the binary flag from the backend.
File(s): scue/bridge/adapter.py (watchdog), frontend/src/components/layout/TopBar.tsx (TrafficDot), frontend/src/components/bridge/BridgeStatusPanel.tsx (TrafficIndicator)

### RouteStatusBanner and ActionBar rendered below interface list instead of above
Date: 2026-03-17
Milestone: FE-BLT
Symptom: In the Hardware Selection panel, the route status banner and Apply & Restart button appeared at the bottom of the panel, below the full interface list, making them hard to find.
Root cause: Component render order in `HardwareSelectionPanel` placed `InterfaceSelector` first, then `RouteStatusBanner` and `ActionBar`. No logic error — just wrong visual priority.
Fix: Reordered so `RouteStatusBanner` and `ActionBar` render before `InterfaceSelector`.
File(s): frontend/src/components/bridge/HardwareSelectionPanel.tsx

---

### HTML entity strings rendered as literal text in sort indicators
Date: 2026-03-16
Milestone: FE-3
Symptom: The "Analyzed" column header displayed the raw string `&#X25BC;` instead of a ▼ symbol. Clicking toggled it to `&#X25B2;` instead of ▲. Other unsorted columns showed `&#x21C5;` as literal text on page reload.
Root cause: The `SortIndicator` component used HTML entity strings (`"&#x25B2;"`) as JSX text content. React renders string literals as-is — it does not interpret HTML entities inside `{}` expressions. Only entities written directly in JSX markup (outside `{}`) are parsed by the JSX compiler.
Fix: Replaced HTML entity strings with actual Unicode characters: `"⇅"`, `"▲"`, `"▼"`.
File(s): frontend/src/components/tracks/TrackTable.tsx
