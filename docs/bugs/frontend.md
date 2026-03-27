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

### [FIXED] Analysis blocks event loop, UI freezes during track analysis
Date: 2026-03-20
Fixed: 2026-03-20
Milestone: M7
Symptom: Starting track analysis causes the UI to indefinitely load. The server becomes unresponsive — polling requests get no response, making the progress bar appear stuck.
Root cause: `_run_analysis_task` in `tracks.py` was defined as `async def`, which FastAPI runs on the event loop. Since `run_analysis()` is CPU-bound (6-10s per track), it blocks the event loop, preventing all HTTP request handling. The batch path (`_run_batch_analysis`) correctly used `asyncio.to_thread()` but the single-track path did not.
Fix: Changed `_run_analysis_task` from `async def` to `def` so FastAPI runs it in the thread pool. Also added per-step progress reporting (progress_callback) and frontend error handling for lost jobs (404 during polling).
File(s): scue/api/tracks.py, scue/layer1/analysis.py, scue/api/jobs.py, frontend/src/components/tracks/AnalyzePanel.tsx, frontend/src/types/analyze.ts

### [FIXED] EventTimeline renders waveform as stacked layers instead of blended color
Date: 2026-03-20
Fixed: 2026-03-20
Milestone: M7
Symptom: Waveform on the detector tuning page looked wrong compared to Pioneer CDJs — three distinct colored layers stacked instead of a single blended color per column.
Root cause: EventTimeline.tsx drew separate red/green/blue rectangles for bass/mids/highs (the exact anti-pattern documented in ADR-018). WaveformCanvas.tsx had already been fixed but EventTimeline was written from scratch without following the same approach.
Fix: Rewrote waveform rendering in EventTimeline to match Pioneer RGB approach: single blended bar per column where height = amplitude and color = frequency ratio (R=low, G=mid, B=high).
File(s): frontend/src/components/detectors/EventTimeline.tsx

### Live Deck Monitor shows "Unknown track" for analyzed tracks with no retry option
Date: 2026-03-20
Milestone: FE-Live-Deck-Monitor
Symptom: Tracks that have been analyzed via the Tracks page show as "Unknown track" on the Live Deck Monitor with no way to retry or see what data the bridge is reporting.
Root cause: Two issues: (1) Analysis alone doesn't populate the `track_ids` table — only USB scanning creates the `(source_player, source_slot, rekordbox_id) → fingerprint` mapping. (2) The not-found empty state showed minimal info and no retry button.
Fix: Updated DeckEmptyState to show full bridge diagnostic data (all CDJ-reported fields in a labeled table) and added a "Retry resolution" button that invalidates the TanStack Query cache. Updated messaging to point users to USB scanning. Root linking gap (analysis not populating track_ids) deferred — requires design work on matching strategy.
File(s): frontend/src/components/live/DeckEmptyState.tsx, frontend/src/components/live/DeckPanel.tsx

### Ingestion page: local-library/status returns non-result shape before first scan
Date: 2026-03-25
Milestone: FE-Ingestion
Symptom: Switching to the Ingestion page crashes the app with a white screen. React error boundary reports error in `<ScanResultsTable>`.
Root cause: `GET /api/local-library/status` returns `{"status": "no_scan", "message": "..."}` when no scan has been performed — no `.tracks` property. The `useLibraryScanStatus` hook typed this as `LibraryScanResult` and passed it directly to `ScanResultsTable`, which iterated `.tracks` on an object that didn't have it.
Fix: Added null guard: only render `ScanResultsTable` when `result?.tracks` is truthy.
File(s): frontend/src/components/ingestion/LibraryTab.tsx

### Ingestion page: scanner/history returns wrapped object, not flat array
Date: 2026-03-25
Milestone: FE-Ingestion
Symptom: Clicking the Hardware tab crashes the app. React error boundary reports error in `<HardwareTab>`.
Root cause: `GET /api/scanner/history` returns `{"tracks": []}` (wrapped in an object), but `useScanHistory` was typed as returning `ScannedHistoryTrack[]` (flat array). The `useMemo` that built `scannedIds` called `.map()` on the wrapper object, which has no `.map` method.
Fix: Created `ScanHistoryResponse` type with `tracks: ScannedHistoryTrack[]`. Updated hook return type and access pattern to `history?.tracks ?? []`.
File(s): frontend/src/types/ingestion.ts, frontend/src/api/ingestion.ts, frontend/src/components/ingestion/HardwareTab.tsx

**Pattern note:** This is the second time a backend API returning a wrapper object (`{tracks: [...]}`) instead of a flat array has caused a frontend crash. The `/api/scanner/history` and `/api/local-library/status` endpoints both follow this pattern. When writing new API hooks, always check the actual response shape against the type definition — don't assume based on the endpoint name.

### Ingestion: Slot selector missing — USB browser hardcoded to wrong slot
Date: 2026-03-25
Milestone: FE-Ingestion
Symptom: Hardware tab USB Browser shows "Empty" despite USB being inserted. No tracks appear.
Root cause: `HardwareTab.tsx` derived slot from `players[activePlayer]?.track_source_slot` which is `"no_track"` when no track is loaded, falling back to uppercase `"USB"` (API expects lowercase). Also, XDJ-AZ maps physical USB slot 2 to `sd` in Pro DJ Link — there was no way for the user to select the correct slot.
Fix: Added explicit USB/SD slot selector dropdown. Replaced `track_source_slot` derivation with user-controlled `selectedSlot` state. Clears selection when slot changes.
File(s): frontend/src/components/ingestion/HardwareTab.tsx

### Ingestion: Menu items not rendering — bridge response shape mismatch
Date: 2026-03-25
Milestone: FE-Ingestion
Symptom: Hardware tab USB Browser shows flat track list but no folder navigation. Root menu items (ARTIST, ALBUM, PLAYLIST, etc.) are invisible.
Root cause: Bridge returns `{item_type, text1, text2, id}` for root menu items and `{item_type, title, artist, rekordbox_id}` for folder items. Frontend expected `{id, name, is_folder}`. The `items.filter(i => i.is_folder)` check dropped everything because `is_folder` was always undefined.
Fix: Added `_normalize_menu_item()` in `scue/api/scanner.py` to normalize both response shapes to `{id, name, is_folder}`. Strips Pioneer `￺/￻` delimiters from root menu names. Determines `is_folder` from `item_type` suffix (`_menu`, `playlist`, `folder`).
File(s): scue/api/scanner.py

### [FIXED] Ingestion: Duplicate React keys in track list
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Ingestion
Symptom: 488 React console errors: "Encountered two children with the same key". Visible when browsing USB with many tracks.
Root cause: `browse_all_tracks` returns tracks with duplicate `rekordbox_id` values (e.g. same track appears under multiple playlists on the USB). `UsbBrowser.tsx` uses `track.rekordbox_id` as the React key, but these are not unique across the full track list.
Fix: Changed key from `track.rekordbox_id` to `${track.rekordbox_id}-${index}` to guarantee uniqueness.
File(s): frontend/src/components/ingestion/UsbBrowser.tsx

### [FIXED] Ingestion: Second scan doesn't start from UI after first completes
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Ingestion
Symptom: After a scan completes, clicking "Scan Selected" again doesn't start a new scan. The progress panel still shows old results.
Root cause: Two compounding issues: (1) The backend only emits `scan_progress` WS messages — it never emits a separate `scan_complete` message. But the frontend WS handler only called `setScanComplete()` (which resets `hardwareScanInProgress = false`) on `scan_complete` messages, not on `scan_progress` messages with terminal statuses. So `hardwareScanInProgress` stayed `true` forever after the first scan. (2) The "Scan Selected" button checked `scanInProgress` in its `disabled` prop, so it was permanently disabled. (3) Additionally, the backend sends `status: "completed"` but the frontend type expected `"complete"`, so status checks in `ScanProgressPanel` never matched.
Fix: (a) Updated `ws.ts` to detect terminal statuses (`"completed"`, `"failed"`) in `scan_progress` messages and route them to `setScanComplete()` + invalidate query caches. (b) Fixed `HardwareScanStatus.status` type to match actual backend enum: `"idle" | "browsing" | "scanning" | "stopping" | "completed" | "failed"`. (c) Updated `ScanProgressPanel.tsx` status checks from `"complete"`→`"completed"`, `"error"`→`"failed"`, removed nonexistent `"stopped"`. (d) Added `onMutate` optimistic update to `useStartHardwareScan` for immediate UI feedback when starting a new scan.
File(s): frontend/src/api/ws.ts, frontend/src/api/ingestion.ts, frontend/src/types/ingestion.ts, frontend/src/components/ingestion/ScanProgressPanel.tsx

### [FIXED] Ingestion: HardwareScanStatus type mismatches backend enum values
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Ingestion
Symptom: "Scan complete." message never appeared in progress panel after scan finished. The scan appeared stuck in scanning state even after all tracks were processed.
Root cause: Backend `ScanStatus` enum values are `"idle" | "browsing" | "scanning" | "stopping" | "completed" | "failed"`. Frontend `HardwareScanStatus.status` was typed as `"idle" | "scanning" | "complete" | "stopped" | "error"`. Three mismatches: `"completed"` vs `"complete"`, `"failed"` vs `"error"`, `"stopped"` (never emitted by backend). Missing values: `"browsing"`, `"stopping"`.
Fix: Updated `HardwareScanStatus.status` union to match backend. Updated all frontend status string comparisons.
File(s): frontend/src/types/ingestion.ts, frontend/src/components/ingestion/ScanProgressPanel.tsx

**Pattern note:** This is a FE/BE contract mismatch. The types in `src/types/` should be verified against the Python dataclasses/enums when writing new scanner features. The backend `ScanStatus` enum in `scue/layer1/scanner.py` is the source of truth.

### [FIXED] Player switch shows empty USB browser (stale navigation state)
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Ingestion
Symptom: Switching from Player 1 to Player 2 in the USB Browser shows "Empty" even though Player 1 had content. Switching back to Player 1 also shows incorrect state.
Root cause: `UsbBrowser` kept stale `folderId`/`folderPath` state across player and slot changes. If the user was browsing a folder on Player 1, the same folder ID was used for the Player 2 query (which either failed or returned different content). Additionally, `HardwareTab` didn't clear `selectedTrackIds` on player change (only on slot change).
Fix: Added `useEffect` in `UsbBrowser` that resets `folderId` and `folderPath` to root when `player` or `slot` props change. Added `setSelectedTrackIds(new Set())` to the player change handler in `HardwareTab`.
File(s): frontend/src/components/ingestion/UsbBrowser.tsx, frontend/src/components/ingestion/HardwareTab.tsx

### [FIXED] XDJ-AZ Player 2 USB browsing returns 500 — all-in-one DLP identity
Fixed: 2026-03-26 — see fix entry below.
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: MEDIUM (blocks Player 2 browsing on all-in-one units)
Symptom: Selecting Player 2 in the USB Browser on an XDJ-AZ returns "Empty". Backend returns 500: "Expected to connect to player 2, but welcome response identified itself as player 1".
Root cause: The XDJ-AZ is an all-in-one unit — both decks share one DLP network identity (Player 1). The bridge's `browse_all_tracks` command connects to the target player number, but the device always responds as Player 1. This is a beat-link DLP protocol limitation for all-in-one hardware.
Fix: Two options: (1) Frontend: auto-detect all-in-one units (both CDJ device names are identical or device_number maps to same IP) and hide the player selector for browsing — always browse via Player 1, only use deck selection for scan target. (2) Backend: catch the "wrong player" error in the browse path and retry via Player 1. Option 1 is simpler and avoids unnecessary network round-trips.
File(s): frontend/src/components/ingestion/HardwareTab.tsx (player selector logic), scue/layer1/scanner.py (browse commands)

### [OPEN] USB hot-removal breaks all subsequent DLP browsing until backend restart
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: HIGH (blocks all USB browsing after any media change)
Symptom: After physically removing a USB from the XDJ-AZ during a session, ALL browse requests fail — including for USBs that are still inserted. Player 1 + USB shows "Empty", Player 1 + SD shows "Empty", Player 2 shows "Empty". The only recovery is restarting the backend.
Observed network behavior:
- `GET /api/scanner/browse/1/sd/menu` → 500 with `{"detail": ""}` (empty error message)
- `GET /api/scanner/browse/1/usb/menu` → 500 with `{"detail": ""}` (expected — USB was removed)
- `GET /api/scanner/browse/2/usb/menu` → 500 with `{"detail": "Expected to connect to player 2, but welcome response identified itself as player 1"}` (XDJ-AZ DLP identity issue)
- `GET /api/scanner/status` → 200, status "idle" (scanner itself is fine)
- Bridge WS connection is still alive (bridge status shows "connected" in TopBar)
Root cause (multi-layer):
1. **Java bridge DLP layer**: When a USB is removed, the Java bridge's DLP (DeviceLink Protocol) connection state becomes stale. The DLP protocol maintains per-slot media availability state internally. Removing a USB invalidates this state, but the bridge doesn't re-negotiate or refresh media slot availability. Subsequent browse commands for ANY slot on the same player fail because the DLP session is corrupted.
2. **Backend scanner lifecycle** (`scue/api/scanner.py:39-122`): `_get_or_create_scanner()` creates a new `TrackScanner` on each non-scanning request, capturing `_bridge_manager.ws_client`. The WS connection itself is healthy (bridge subprocess is running), so the 503 "Bridge not connected" guard doesn't trigger. The failure happens deeper — inside the Java bridge's DLP command handling — and surfaces as an empty error message (`resp.ok = False`, `resp.error_message = ""`).
3. **Empty error detail**: The bridge returns a failure response with no error message, so the 500 response has `{"detail": ""}`. Users see "Empty" in the UI with no explanation. The frontend doesn't distinguish "no media in slot" from "DLP connection broken".
Impact: Any USB hot-swap (insert or remove) during a session breaks all hardware browsing. This is a realistic scenario — DJs frequently swap USBs.
Fix options (in order of depth):
1. **Quick FE fix**: Show the actual error from the backend instead of "Empty" when browse returns 500. Currently `useUsbMenu`/`useUsbBrowse` have `retry: false` so errors are swallowed and the empty fallback renders.
2. **Backend fix**: Add a `/api/scanner/reset` endpoint that nullifies `_scanner` and forces `_get_or_create_scanner()` to create a fresh scanner + DLP connection on the next request. Wire a "Refresh" button in the USB Browser header to call it.
3. **Bridge fix**: The Java bridge should detect media slot changes (USB insert/remove events are broadcast on Pro DJ Link) and re-establish its DLP browsing session automatically. This is the proper fix but requires Java-side changes to `BeatLinkBridge.java`.
4. **Bridge + Backend fix**: Bridge emits a `media_change` WS message when slots change. Backend invalidates the scanner. Frontend invalidates TanStack Query cache for browse queries. Full reactive chain.
Workaround: Restart the backend (`uvicorn scue.main:app --reload`).
**Update 2026-03-25:** Moving the USB from slot 2 to slot 1 caused the bridge to restart on its own. This suggests the bridge crash-restart cycle is triggered by media slot changes, and the restart happens to recover the DLP session — but only for slot 1 (`usb`), not slot 2 (`sd`). This needs investigation: does the bridge treat slot 1 as the "primary" media source? Does the XDJ-AZ only broadcast mount events for slot 1? Or does the bridge's health check only monitor slot 1?
File(s): scue/api/scanner.py (_get_or_create_scanner, browse_root_menu), bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java (DLP session management), frontend/src/components/ingestion/UsbBrowser.tsx (error display)
QA gap: The QA plan (phases 1-10) did not include any media hot-swap scenarios. All phases assumed a static hardware configuration throughout testing. Phase 8 (Error States) tested bridge-down and no-CDJ states but not mid-session media changes. Future QA plans for hardware-connected features should include a "Hardware Mutation" phase covering: USB insert, USB remove, USB swap (remove + insert different), slot change while scan in progress, and bridge reconnect after media change.

**Live USB Hot-Swap QA (2026-03-25) — XDJ-AZ, two USBs:**

Hardware: XDJ-AZ (all-in-one). Slot 1 (left) = `usb` in DLP. Slot 2 (right) = `sd` in DLP.

| Scenario | USB slot (`usb`) | SD slot (`sd`) | Bridge | UI |
|---|---|---|---|---|
| Both in (baseline) | ✅ 12 menu items, 2022 tracks | ✅ works | ✅ green | ✅ root menu |
| Slot 1 removed | ❌ 0 items, DLP corrupted | ❌ 500 (DLP corrupted) | Stayed running | **Stale cache shown, no error** |
| Slot 1 re-inserted | ✅ recovered | ✅ recovered | **Crashed → auto-restarted (~10s)** | "Not connected" → recovered |
| Slot 2 removed | ✅ 12 items, 2022 tracks | ✅ 0 items (correct empty) | ✅ stayed healthy | **Stale cache, no error** |

Key findings:
1. **Asymmetric behavior**: Slot 1 (`usb`) removal corrupts DLP for ALL slots. Slot 2 (`sd`) removal is handled gracefully — remaining slot still works.
2. **Recovery via crash**: Re-inserting slot 1 USB triggers a bridge crash → auto-restart → fresh DLP session. This is the only recovery path — there is no graceful DLP session refresh.
3. **Stale FE cache**: In ALL removal scenarios, the frontend shows stale TanStack Query cache with no error indication. The user has no idea media was removed.
4. **CDJ screen vs SCUE**: CDJ's own screen correctly shows media changes in real time. SCUE does not react.
5. **Bridge crash is the recovery mechanism**: The crash is not a bug per se — it's the bridge's only way to get a fresh DLP session after slot 1 changes. But a crash should not be the normal recovery path.

Next step: Bridge resilience task — add `MediaDetailsListener` to the Java bridge, emit `media_change` WS events, gracefully re-establish DLP sessions without crashing. See bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java.

### [FIXED] Per-deck progress status and total never render in ScanProgressPanel
Fixed: 2026-03-26 — see fix entry below.
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: LOW (cosmetic — overall progress works fine)
Symptom: In `ScanProgressPanel`, per-deck status text is always gray (never blue for "scanning"), and per-deck `scanned/total` counter never appears. Only `current_track` name and overall scanned count display correctly.
Root cause: Backend `deck_progress` entries are initialized with `{"scanned": 0, "errors": 0, "current_track": ""}` — missing `status` and `total` fields. Frontend `DeckProgress` type declares `status: string` and `total: number` as required fields and consumes them in the panel.
Fix: Either add `status` and `total` to backend `deck_progress` initialization in `scanner.py:311`, or make frontend handle missing fields gracefully (default `status` to infer from `current_track`, omit `total` display).
File(s): scue/layer1/scanner.py (line 311), frontend/src/types/ingestion.ts (DeckProgress), frontend/src/components/ingestion/ScanProgressPanel.tsx (lines 50-58)

### [OPEN] Mid-scan USB removal causes silent per-track timeouts with no user feedback
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: MEDIUM (UX — not a crash)
Symptom: If a USB is physically removed during a hardware scan, the scan does not abort. Instead, each remaining track times out after 15 seconds with no user-visible explanation. For a large library this can mean minutes of apparent hanging. The progress panel shows an incrementing error count but no explanation of why.
Root cause: Backend `_scan_one_track` catches `TimeoutError` silently (logs warning only). No escalation from repeated timeouts to a top-level scan abort. No user-facing message for per-track failures.
Fix: Backend change needed — detect repeated consecutive timeouts as likely hardware disconnect and transition to `FAILED` status with descriptive error message. Not fixing now per task constraints (no backend modifications unless bug found there).
File(s): scue/layer1/scanner.py (_scan_one_track, _deck_worker)

### [FIXED] Playlist sub-navigation loops instead of opening playlist contents
Date: 2026-03-25 (fixed 2026-03-26)
Milestone: FE-Ingestion
Severity: HIGH (blocks playlist-based track selection)
Symptom: Clicking a playlist folder in UsbBrowser adds it to the breadcrumb path but does not show the tracks inside. Instead, the same folder list re-renders, and clicking again adds another level (screenshot shows: Root / PLAYLIST / post-hibernation / post-hibernation / post-hibernation / post-hibernation). The folder appears to re-list its own children recursively.
Root cause: **Confirmed via live QA (2026-03-25).** The Java bridge called the wrong beat-link API: `MenuLoader.requestPlaylistMenuFrom(slotRef, folderId)` — the second parameter is `sortOrder`, NOT `folderId`. This method always returns the root playlist listing. The correct API is `MetadataFinder.requestPlaylistItemsFrom(player, slot, sortOrder, folderId, isFolder)`, which takes a boolean `isFolder` flag: `true` returns sub-folders/playlists, `false` returns tracks within a leaf playlist.
Fix: Full-stack fix (2026-03-26). See `docs/bugs/layer0-bridge.md` entry "Playlist sub-navigation returns root listing" for complete details. Key changes: Java handler now calls `MetadataFinder.requestPlaylistItemsFrom`, Python command/scanner/API pass `is_folder` boolean, frontend UsbBrowser tracks `isFolder` state and passes it through the API call.
Verified: API tested against live XDJ-AZ — playlist navigation returns correct sub-items and tracks. Full UI flow QA pending.
File(s): bridge-java/src/main/java/com/scue/bridge/CommandHandler.java, scue/bridge/commands.py, scue/layer1/scanner.py, scue/api/scanner.py, frontend/src/api/ingestion.ts, frontend/src/components/ingestion/UsbBrowser.tsx

### [FIXED] TRACK root menu navigates to playlist content instead of track list
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: HIGH (wrong content shown for TRACK menu)
Symptom: Clicking the TRACK item in the root menu shows the playlist directory contents, not a flat list of tracks. Screenshot shows folders like "New THE GOOD STUFF", "NewOldDump1", etc. which are playlist names, not the expected alphabetical/sorted track listing.
Root cause: **Confirmed via live QA (2026-03-25).** All root menu items (TRACK, ARTIST, PLAYLIST, KEY, etc.) are treated the same way — clicking any of them calls `browse_folder` which calls `browse_playlist` on the Java bridge. The backend has only one DLP browse command (`requestPlaylistMenuFrom`). DLP has *different* browse commands for different menu types (tracks, artists, playlists, etc.), but the bridge only implements the playlist one. The TRACK menu needs a flat track listing (e.g. beat-link's `requestTrackMenuFrom` or equivalent), not `requestPlaylistMenuFrom`.
Expected behavior: TRACK shows a flat alphabetical list of all tracks. ARTIST shows artist folders → tracks. PLAYLIST shows playlist hierarchy → tracks.
Fix: Java bridge needs additional DLP browse commands for non-playlist menu types. Short-term: for TRACK specifically, use the existing `browse_all_tracks` command (which uses `requestAllTracksFrom`) instead of `browse_folder`. Medium-term: add menu-type-aware browse routing.
File(s): bridge-java/src/main/java/com/scue/bridge/CommandHandler.java, scue/api/scanner.py (browse_folder — needs menu_type param), frontend/src/components/ingestion/UsbBrowser.tsx (pass menu_type when navigating from root)

### [FIXED] XDJ-AZ appears as three devices in player dropdown (Player 1, Player 2, XDJ-AZ)
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Ingestion
Severity: MEDIUM (confusing UI, XDJ-AZ option defaults to Player 1 anyway)
Symptom: The player dropdown in USB Browser shows three options instead of two. "XDJ-AZ" appears as a third entry alongside "Player 1" and "Player 2". Selecting XDJ-AZ defaults to Player 1 behavior. Same issue visible in Bridge page device list.
Root cause: The XDJ-AZ announces itself on Pro DJ Link as both individual player devices (device_number 1 and 2) AND as a mixer/controller device with its own device_name "XDJ-AZ". The `cdjDevices` filter (`device_type === "cdj"`) may be catching all three, or the mixer device is being misclassified as a CDJ.
Fix: Deduplicated `cdjDevices` by `device_number` in HardwareTab. The first device with each number is kept; duplicates (mixer/controller sharing a player's number) are filtered out. Verified live: dropdown shows 2 players, deck checkboxes show 2 decks.
File(s): frontend/src/components/ingestion/HardwareTab.tsx (cdjDevices filter)

### [FIXED] Duplicate "Deck 1" in scan target checkboxes
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Ingestion
Severity: MEDIUM (confusing — shows Deck 2, Deck 1, Deck 1)
Symptom: Scan Controls shows three deck checkboxes: "Deck 2", "Deck 1", "Deck 1". Should only show two (Deck 1, Deck 2).
Root cause: Same as the XDJ-AZ three-device bug above — the mixer/controller device has a device_number that duplicates one of the players. The `availableDecks` array includes all CDJ device numbers, and two of them are "1".
Fix: Same dedup fix as above — `cdjDevices` deduplication by device_number eliminates the duplicate.
File(s): frontend/src/components/ingestion/HardwareTab.tsx (cdjDevices, availableDecks)

### [FIXED] Single-track scan progress doesn't update — appears to hang
Fixed: 2026-03-26 — per-deck progress fields + current track display fix resolves this.
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: HIGH (user thinks scan is broken)
Symptom: Selecting one track and clicking "Scan Selected" shows the progress panel but it appears to hang — no real-time progress visible. The scan eventually completes (shows "Scan complete") but the user gets no feedback during processing.
Root cause: For a single track, the scan is very fast (seconds). The progress bar jumps from 0% to 100% without visible intermediate states. The per-deck status lines ("Deck 1:", "Deck 2:") show nothing to the right because `deck_progress` entries from the backend don't include `status` or `total` fields (see existing bug: "Per-deck progress status and total never render"). Combined with no current-track display, it looks frozen.
Fix: (1) Fix the per-deck progress fields (backend needs to populate `status` and `total`). (2) Show the current track name being scanned in the overall progress area, not just per-deck. (3) For single-track scans, consider showing a simpler "Scanning: [track name]..." message instead of the full progress panel.
File(s): frontend/src/components/ingestion/ScanProgressPanel.tsx, scue/layer1/scanner.py (deck_progress)

### [FIXED] Selected tracks not cleared after scan completes
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: LOW (confusing but not broken)
Symptom: After scanning selected tracks, the checkbox selection persists. Tracks that were just scanned remain checked.
Expected behavior: Deselect all tracks after scan completes. The "scanned" indicator badge in the track list should be the visual cue that tracks were processed.
Fix: Clear `selectedTrackIds` in the `scan_complete` handler (in `ws.ts` where terminal status is detected, or in `useStartHardwareScan` `onSuccess`).
File(s): frontend/src/components/ingestion/HardwareTab.tsx

### [FIXED] Shift-click range selection not implemented in UsbBrowser track list
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: MEDIUM (standard UX expectation for multi-select lists)
Symptom: Clicking one track, then shift-clicking another, does not select all tracks between them. Only the clicked track toggles. Users expect shift-click range selection in any multi-select list.
Fix: Added `lastClickedIndex` ref. `toggleTrack` now accepts `(id, index, shiftKey)`. On shift-click, selects all tracks between last-clicked index and current. Checkbox `onChange` passes `e.nativeEvent.shiftKey` and `stopPropagation()` prevents double-toggle from the row click.
File(s): frontend/src/components/ingestion/UsbBrowser.tsx (toggleTrack handler)

### [OPEN] Multi-deck scanning only uses Deck 1 — Deck 2 never loads tracks
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: HIGH (multi-deck parallel scanning is a key feature)
Symptom: When scanning multiple tracks with both Deck 1 and Deck 2 checked, only Deck 1 processes tracks. Deck 2 shows in the progress panel but never picks up work.
Root cause: Needs investigation. Check: (1) Is the backend `_deck_worker` for player 2 actually dequeuing tracks? (2) Does the `load_track` command work for player 2 on XDJ-AZ? (3) Is this the same DLP identity issue where player 2 commands go to player 1? Prior session notes say multi-deck scanning was "confirmed working (Deck 1: 5 tracks, Deck 2: 1 track)" — may be a regression or XDJ-AZ-specific issue after USB slot change.
File(s): scue/layer1/scanner.py (_deck_worker, _scan_one_track)

### [FIXED] Live tier columns (L, L-O) not lit in Track Library after hardware scan
Fixed: 2026-03-26 — strata cache invalidation + tooltips. See fix entry below.
Date: 2026-03-25
Milestone: FE-Ingestion / Strata
Severity: MEDIUM (misleading — data exists but UI doesn't reflect it)
Symptom: After scanning tracks via hardware, the L and L-O columns in the Track Library table are not marked as available, even though live tier analysis data was generated during the scan.
Column definitions (per Brach): **L = Live tier data exists**, **L-O = Live Offline tier data exists**. These are NOT about active playback status.
Root cause: Needs investigation. The track table may not query strata tier availability, or the scan doesn't trigger strata analysis automatically — it only captures Pioneer metadata.
Expected behavior: L column should be lit when live tier strata data exists for a track (from any source — hardware scan, active playback, etc.). L-O should be lit when live-offline analysis has been run. Column headers need tooltips explaining these abbreviations.
Fix: (1) Wire track table to check strata tier availability. (2) Add tooltips to L and L-O column headers.
File(s): frontend/src/components/ingestion/TrackLibraryTable.tsx, frontend/src/components/tracks/TrackTable.tsx

### [OPEN → CLARIFIED] Live offline tier not available for scanned tracks in Strata page
Date: 2026-03-25
Milestone: Strata
Severity: LOW (by design — not a bug, but UX could be clearer)
Symptom: On the Strata page, tracks that have been scanned show "Live" as an option when selected, but "Live Offline" is not available.
Confirmed behavior (2026-03-25 live QA): Live Offline is a separate analysis tier that must be explicitly triggered via the "Analyze Live Offline" button on the Strata page. It is NOT auto-generated from hardware scanning. The UI already shows "No data for Live Offline tier yet. Saved Pioneer data (no hardware or audio needed)" with an action button. This is correct behavior — not a bug.
Fix: No code fix needed. Consider making the distinction between Live (real-time bridge) and Live Offline (saved Pioneer data analysis) clearer in the tier button tooltips.
File(s): frontend/src/pages/StrataPage.tsx

### [FIXED] Strata page zoom/scroll affects the webpage instead of just the waveform
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: Strata
Severity: HIGH (makes zoom/scroll unusable)
Symptom: Using scroll wheel on the Strata page waveform/arrangement map area scrolls the entire webpage in addition to zooming/scrolling the canvas.
Root cause: React's `onWheel` handler is passive by default in Chrome, so `e.preventDefault()` was silently ignored. The existing code called `preventDefault()` but it had no effect because React registers wheel listeners as `{ passive: true }`.
Fix: Replaced React `onWheel` props with native `addEventListener("wheel", handler, { passive: false })` via `useEffect` in all three canvas components: WaveformCanvas, ArrangementMap, and AnnotationTimeline. Used refs to avoid stale closures in the native handler.
File(s): frontend/src/components/shared/WaveformCanvas.tsx, frontend/src/components/strata/ArrangementMap.tsx, frontend/src/components/annotations/AnnotationTimeline.tsx

### [FIXED] "Other" track field in live analysis is unexplained
Date: 2026-03-25
Milestone: Strata
Severity: LOW (confusing label)
Symptom: When viewing live tier analysis on the Strata page, there is a field labeled "other" that the user doesn't understand. No tooltip or explanation.
Root cause: **Corrected (2026-03-25).** Initial investigation incorrectly attributed this to demucs stem separation. Demucs only runs on Standard/Deep tiers (audio-file analysis). The "other" label in the **Live tier** comes from `live_analyzer.py:271-272` — it creates a `StemAnalysis(stem_type="other")` with the comment: `"other" maps to the "mix" lane in ArrangementMap`. This is NOT a separated stem — it's the **full mix / master waveform** derived from Pioneer CDJ waveform data. It represents overall track energy from the hardware, not a stem-separated component.
Note: In Standard/Deep tiers, "other" IS the demucs stem (synths/keys/fx). The label means different things depending on the tier — a naming collision.
Expected behavior: In Live tier, rename "other" to "Mix" or "Full Mix". In Standard/Deep tiers, rename to "Synths / FX". Add tooltips to both.
Fix: ArrangementMap should display a different label based on the current tier. When tier is "live", show "Mix". When tier is "quick"/"standard"/"deep", show "Synths / FX".
File(s): frontend/src/components/strata/ArrangementMap.tsx, frontend/src/pages/StrataPage.tsx

### [NOTE → LIKELY CORRECT] Can view live analysis for tracks without loading them on decks
Date: 2026-03-25
Milestone: Strata
Symptom: Clicking different tracks in the Strata page while the board is connected shows live tier analysis for each of them, even without loading the track on a CDJ deck first.
QA update (2026-03-25): Brach confirms the data does not appear stale — each track shows different analysis. Most likely explanation: these tracks were previously scanned via hardware, and live tier data was persisted during scanning. The Live tier on the Strata page reads from persisted strata files, not just real-time bridge data. This is **correct behavior** — not a bug. The initial confusion arose because scanning was done in an earlier session.
Status: Not a bug. No fix needed.
File(s): scue/layer1/strata/live_analyzer.py, scue/layer1/tracking.py

### [FIXED] Scan progress panel has no dismiss button after scan completes
Fixed: 2026-03-25 (prior session) — already implemented but bug entry not updated.
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: MEDIUM (scan progress panel persists indefinitely after scan)
Symptom: After a scan completes, the Scan Progress panel stays visible showing "Scan complete. 1/1 tracks scanned" with no way to dismiss it. The panel persists across player switches and slot changes. Confirmed via live QA (2026-03-25).
Expected behavior: After scan completes, the progress panel should transition to a summary state ("Done: 1 track scanned") with a dismiss X button. Clicking X collapses the panel. The panel should NOT block scan controls or USB browser interaction.
Fix: Add a dismiss X button to the ScanProgressPanel header when status is terminal ("completed" or "failed"). On dismiss, reset the scan progress state.
File(s): frontend/src/components/ingestion/ScanProgressPanel.tsx
Pipeline note: Brach reports this UX requirement was communicated to the prior agent but was not implemented or tested. Pipeline improvement needed — ensure UX specs from operator are tracked as explicit requirements, not just conversation context.

### [FIXED] Re-scanning already-scanned tracks needs confirmation dialog
Fixed: 2026-03-26 — see fix entry below.
Date: 2026-03-25
Milestone: FE-Ingestion
Severity: LOW (UX improvement)
Symptom: Selecting tracks that have already been scanned and clicking "Scan Selected" starts scanning without any warning. User may waste time re-scanning tracks unnecessarily.
Expected behavior: When starting a scan where some/all selected tracks have already been scanned, show a confirmation dialog: "N of M selected tracks have already been scanned. Skip these, or scan again?" Options: "Skip Already Scanned" (removes them from the scan list), "Scan All Again" (proceeds as-is), "Cancel".
Fix: Check `selectedTrackIds` against the scan history (`useScanHistory`) before starting scan. If overlap exists, show confirmation dialog.
File(s): frontend/src/components/ingestion/HardwareTab.tsx, frontend/src/api/ingestion.ts (useScanHistory)
Pipeline note: Same as above — Brach communicated this requirement to the prior agent.

### [FIXED] Strata page — Live tier rendering gate ignores persisted data
Date: 2026-03-25
Fixed: 2026-03-25
Milestone: FE-Strata
Severity: HIGH (regression — previously working)
Symptom: Selecting a track in the Strata page with Live tier selected showed "Waiting for Pioneer phrase analysis data..." even when persisted live strata data existed for the track.
Root cause: StrataPage.tsx line 447 gated Live tier content on `!liveFormula` (real-time WS data only). A prior fix on line 143-144 correctly added `persistedLiveFormula` as a fallback to `formula`, but the rendering gate was never updated to match. So persisted data was fetched and resolved into `formula`, but the gate blocked rendering before it could be used.
Fix: Changed line 447 from `isLiveTier && !liveFormula` to `isLiveTier && !formula`. Now the gate accounts for both real-time and persisted live data.
File(s): frontend/src/pages/StrataPage.tsx (line 447)
Pipeline note: Not caught by QA because (1) the QA agent ran without a live frontend, and (2) code-only review didn't trace the rendering conditional against the formula resolution logic. If non-live tiers (quick/standard) are also broken, the cause is runtime — needs server-up testing.

### [FIXED] Strata page — clicking tracks no longer shows Live tier analysis
Date: 2026-03-25
Fixed: 2026-03-26
Milestone: FE-Strata
Symptom: Selecting a track in the Strata page with the Live tier selected showed nothing. Previously worked during QA when hardware was connected.
Root cause: When `isLiveTier`, the code forced `tierSources = undefined` (line 137) and `formula` only used real-time live data from `/strata/live` endpoint. Persisted live strata data from `data.tiers.live` (saved during hardware scans) was completely ignored. Without hardware connected, the real-time endpoint returns empty, so nothing displayed. Not a true regression — masked by hardware being connected during QA.
Fix: Added `persistedLiveFormula` fallback: `formula = liveFormula ?? persistedLiveFormula`. Updated `tierHasData("live")` to also check `availableTiers.includes("live")`. Updated `availableSourcesForTier` to use `persistedLiveSources` when live tier is selected.
File(s): frontend/src/pages/StrataPage.tsx

### [FIXED] Per-deck progress status and total never render in ScanProgressPanel
Date: 2026-03-25
Fixed: 2026-03-26
Milestone: FE-Ingestion
Symptom: Per-deck status text always gray, never "scanning". Per-deck scanned/total counter never appeared.
Root cause: Backend `deck_progress` initialized with only `scanned`, `errors`, `current_track` — missing `status` and `total`. Frontend required both fields.
Fix: Added `status: "idle"` and `total: 0` to backend deck_progress initialization. Set `status` to `"scanning"` when deck starts processing. Updated ScanProgressPanel to show scanned count instead of requiring total (shared queue model means per-deck totals aren't meaningful). Added `current_track` to `HardwareScanStatus` type and display in progress panel.
File(s): scue/layer1/scanner.py, frontend/src/types/ingestion.ts, frontend/src/components/ingestion/ScanProgressPanel.tsx, frontend/src/api/ingestion.ts

### [FIXED] XDJ-AZ Player 2 USB browsing returns 500
Date: 2026-03-25
Fixed: 2026-03-26
Milestone: FE-Ingestion
Symptom: Selecting Player 2 in USB Browser on XDJ-AZ returns 500 error.
Root cause: XDJ-AZ is all-in-one — both decks share Player 1 DLP identity.
Fix: Auto-detect all-in-one units (all CDJs have `uses_dlp` + same device name). Hide player selector for USB browsing on all-in-one, always browse via Player 1. Scan deck selector still shows both decks.
File(s): frontend/src/components/ingestion/HardwareTab.tsx

### [FIXED] Re-scanning already-scanned tracks needs confirmation dialog
Date: 2026-03-25
Fixed: 2026-03-26
Milestone: FE-Ingestion
Symptom: Scanning already-scanned tracks starts without warning.
Root cause: No check against scan history before starting.
Fix: Added overlap check between `selectedTrackIds` and `scannedIds`. When overlap found and `forceRescan` is off, shows confirmation dialog with "Skip Already Scanned", "Scan All Again", and "Cancel" options.
File(s): frontend/src/components/ingestion/HardwareTab.tsx

### [FIXED] Strata tier columns (L, L-O, Q, S, D) stale after analysis
Date: 2026-03-26
Milestone: FE-Tracks / Strata
Symptom: After running strata analysis, the tier availability dots in the Track Library table didn't update until backend restart.
Root cause: `_strata_cache` in `tracks.py` was populated once on first request and never invalidated. Strata API endpoints (analyze, save, delete, batch, reanalyze) all create/modify strata files but never called `invalidate_strata_cache()`.
Fix: Added `invalidate_strata_cache()` calls after all strata mutation operations: synchronous analysis, background analysis completion, batch completion, save, and delete. Also added tooltips to L and L-O column headers.
File(s): scue/api/strata.py, frontend/src/components/tracks/TrackTable.tsx

### HTML entity strings rendered as literal text in sort indicators
Date: 2026-03-16
Milestone: FE-3
Symptom: The "Analyzed" column header displayed the raw string `&#X25BC;` instead of a ▼ symbol. Clicking toggled it to `&#X25B2;` instead of ▲. Other unsorted columns showed `&#x21C5;` as literal text on page reload.
Root cause: The `SortIndicator` component used HTML entity strings (`"&#x25B2;"`) as JSX text content. React renders string literals as-is — it does not interpret HTML entities inside `{}` expressions. Only entities written directly in JSX markup (outside `{}`) are parsed by the JSX compiler.
Fix: Replaced HTML entity strings with actual Unicode characters: `"⇅"`, `"▲"`, `"▼"`.
File(s): frontend/src/components/tracks/TrackTable.tsx
