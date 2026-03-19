# Tasks: Bridge Disconnect/Reconnect Lifecycle Fix

## Dependency Graph

```
TASK-001 (adapter clear + timestamp reset)
  ├── TASK-002 (interface pre-check) — depends on TASK-001
  ├── TASK-003 (FE query invalidation + console mapper) — independent of TASK-001
  └── TASK-004 (interface score fix) — independent of TASK-001

TASK-001 and TASK-003 can run in parallel.
TASK-004 can run in parallel with everything.
TASK-002 depends on TASK-001 (same file, same function).
TASK-005 depends on TASK-001 + TASK-002 + TASK-003 (all backend + FE-state fixes landed).
```

## Tasks

### TASK-001: Clear adapter state on crash/restart and reset pioneer timestamp

- **Layer:** Layer 0
- **Agent:** [AGENT: Developer]
- **Estimated effort:** 20 min
- **Depends on:** none
- **Scope:**
  - `scue/bridge/adapter.py` — add `clear()` method
  - `scue/bridge/manager.py` — call `adapter.clear()` in `_cleanup()` and `start()`; reset `_last_pioneer_message_time` in `start()`
- **Inputs:** Current adapter.py and manager.py
- **Outputs:** Adapter clears all device/player state on crash and restart; pioneer timestamp resets on start
- **QA Required:** YES — this is the root fix for stale-data-on-reconnect (bug #1) and false-positive pioneer status (bug #4). Must verify with live hardware: board power-off → crash → restart → no stale data in UI.
- **State Behavior:** N/A (backend only)
- **Acceptance Criteria:**
  - [ ] `BridgeAdapter.clear()` method exists, resets `_devices = {}` and `_players = {}`
  - [ ] `BridgeManager._cleanup()` calls `self._adapter.clear()`
  - [ ] `BridgeManager.start()` calls `self._adapter.clear()` before `self._status = "starting"`
  - [ ] `BridgeManager.start()` sets `self._last_pioneer_message_time = 0.0` (line after existing `_last_message_time = 0.0`)
  - [ ] After crash → restart, `to_status_dict()` returns `devices={}`, `players={}` until fresh bridge data arrives
  - [ ] `pioneer_status.is_receiving` is `false` after restart until fresh Pioneer traffic arrives
  - [ ] All pre-existing tests pass (`python -m pytest tests/test_bridge/`)
  - [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.
- **Context files:**
  - `scue/bridge/adapter.py` — full file, understand `_devices`/`_players` usage
  - `scue/bridge/manager.py` — `_cleanup()` (line 580), `start()` (line 155), `to_status_dict()` (line 614)
  - `scue/api/ws.py` — `_build_pioneer_status()` (line 54) to understand how `_last_pioneer_message_time` is consumed
  - `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-1 and TR-2
  - `specs/feat-FE-BLT/sessions/session-003-qa-tester.md` — QA failure details
- **Status:** [ ] Not started

---

### TASK-002: Interface pre-check in waiting_for_hardware poll loop

- **Layer:** Layer 0
- **Agent:** [AGENT: Developer]
- **Estimated effort:** 15 min
- **Depends on:** TASK-001 (same file; must not conflict with adapter.clear() changes in start())
- **Scope:**
  - `scue/bridge/manager.py` — modify `_wait_for_hardware_loop()`
- **Inputs:** TASK-001 completed (adapter clearing in place)
- **Outputs:** Manager skips restart attempts when the configured interface doesn't exist, eliminating wasted crash cycles
- **QA Required:** YES — must verify with live hardware: adapter unplugged → bridge enters waiting_for_hardware → no crash cycles until adapter re-plugged → bridge recovers.
- **State Behavior:** N/A (backend only)
- **Acceptance Criteria:**
  - [ ] `_wait_for_hardware_loop()` checks interface availability via `socket.if_nametoindex()` (or equivalent) before calling `start()`
  - [ ] When interface is unavailable: logs at debug level, skips this poll cycle, continues waiting
  - [ ] When interface is available: calls `start()` as before
  - [ ] When `_network_interface` is `None`: skips the check (auto-detect mode), calls `start()` as before
  - [ ] No crash-restart cycles occur when hardware is off and interface is missing — bridge stays in `waiting_for_hardware` with zero subprocess launches
  - [ ] When interface reappears (adapter re-plugged), next poll cycle detects it and calls `start()` — bridge recovers
  - [ ] All pre-existing tests pass (`python -m pytest tests/test_bridge/`)
  - [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.
- **Context files:**
  - `scue/bridge/manager.py` — `_wait_for_hardware_loop()` (line 515)
  - `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-3
  - `docs/test-scenarios/bridge-lifecycle.md` — SC-001, SC-002, SC-010 (adapter unplug scenarios)
- **Status:** [ ] Not started

---

### TASK-003: Frontend reconnect-aware query invalidation and console mapper reset

- **Layer:** Frontend-State
- **Agent:** [AGENT: Developer]
- **Estimated effort:** 20 min
- **Depends on:** none (can run in parallel with TASK-001)
- **Scope:**
  - `frontend/src/api/ws.ts` — add query invalidation on bridge reconnect + console mapper reset on WS open
  - `frontend/src/utils/consoleMapper.ts` — `resetMapperState()` already exists (line 23), just needs to be called
- **Inputs:** Current ws.ts and consoleMapper.ts
- **Outputs:** Route/interface queries auto-refresh on bridge reconnect; console mapper starts fresh on WS reconnect
- **QA Required:** YES — must verify: bridge crashes and reconnects → route warning clears automatically; console entries from before disconnect are preserved; new console entries appear correctly after reconnect.
- **State Behavior:** `[INLINE — simple]` — no new visual states; invalidation is invisible to user (queries refetch silently)
- **Acceptance Criteria:**
  - [ ] In `ws.ts`, the `dispatch()` function (or a new helper) tracks the previous bridge status. When `bridge_status.status` transitions to `"running"` from any non-running state, it calls `queryClient.invalidateQueries({ queryKey: ["network", "route"] })` and `queryClient.invalidateQueries({ queryKey: ["network", "interfaces"] })`
  - [ ] `QueryClient` instance is imported from the app's query client module (check where it's instantiated — likely `main.tsx` or a dedicated module). If no shared export exists, create one.
  - [ ] In `ws.ts`, `onOpen()` calls `resetMapperState()` from `consoleMapper.ts` before adding the "Connected to backend" entry
  - [ ] After bridge auto-reconnect, `["network", "route"]` and `["network", "interfaces"]` queries refetch — route mismatch warning clears if route is now correct
  - [ ] Console entries from before disconnect are preserved in the store (ring buffer not flushed)
  - [ ] After WS reconnect, the first `bridge_status` generates appropriate console entries (e.g., "Bridge status: running" appears in console)
  - [ ] `npm run typecheck` passes
  - [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.
- **Context files:**
  - `frontend/src/api/ws.ts` — full file, understand dispatch + onOpen/onClose
  - `frontend/src/utils/consoleMapper.ts` — `resetMapperState()` (line 23), prev state tracking
  - `frontend/src/api/network.ts` — query keys used: `["network", "route"]`, `["network", "interfaces"]`
  - `frontend/src/stores/consoleStore.ts` — confirm no clearEntries() call on reconnect
  - `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-4, TR-6
  - `docs/bugs/frontend.md` — route mismatch bug, console logs bug
- **Status:** [ ] Not started

---

### TASK-004: Interface score accounts for active traffic and route state

- **Layer:** Backend (API/Network)
- **Agent:** [AGENT: Developer]
- **Estimated effort:** 25 min
- **Depends on:** none (can run in parallel with everything)
- **Scope:**
  - `scue/api/network.py` or `scue/network/` module — wherever interface scoring logic lives
  - Investigate first: find the scoring function, understand current factors, add traffic + route factors
- **Inputs:** Current interface scoring logic
- **Outputs:** Interface score reflects active Pioneer traffic and verified route state
- **QA Required:** YES — must verify with live hardware: interface with active traffic and correct route scores higher than one without.
- **State Behavior:** N/A (backend only; frontend already displays the score from the API response)
- **Acceptance Criteria:**
  - [ ] Interface scoring function considers whether Pioneer traffic is currently flowing on the interface (via `_last_pioneer_message_time` or adapter device presence)
  - [ ] Interface scoring function considers whether the macOS broadcast route points to the interface (via `_route_correct`)
  - [ ] An interface with active traffic and correct route scores higher than a baseline interface without
  - [ ] Score updates are reflected in `GET /api/network/interfaces` responses
  - [ ] All pre-existing tests pass
  - [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.
- **Context files:**
  - `scue/api/network.py` — interface list endpoint
  - `scue/network/` — scoring logic (investigate)
  - `scue/bridge/manager.py` — `_last_pioneer_message_time`, `_route_correct` (data sources for score boost)
  - `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — TR-5
  - `docs/bugs/frontend.md` — "Interface score stays at 5" bug entry
- **Status:** [ ] Not started

---

### TASK-005: Investigate and fix console logs disappearing on reconnect

- **Layer:** Frontend-State / Frontend-UI
- **Agent:** [AGENT: Developer]
- **Estimated effort:** 20 min
- **Depends on:** TASK-003 (console mapper reset may partially fix this)
- **Scope:**
  - `frontend/src/stores/consoleStore.ts` — verify no flush on reconnect
  - Console page component(s) — investigate if component remount causes entry loss
  - `frontend/src/api/ws.ts` — verify no clearEntries() call path on reconnect
- **Inputs:** TASK-003 completed (mapper reset in place)
- **Outputs:** Console entries persist across WS reconnect events
- **QA Required:** YES — must verify with live hardware or simulated WS drop: console entries from before disconnect remain visible after reconnect.
- **State Behavior:** `[INLINE — simple]` — console entries are a flat list, no complex state-dependent display
- **Acceptance Criteria:**
  - [ ] Root cause identified and documented in session summary
  - [ ] Console entries from before a bridge disconnect/reconnect remain visible in the console panel
  - [ ] No `clearEntries()` call triggered by WS reconnect, bridge state change, or component remount
  - [ ] If the root cause is a component unmount/remount issue, the fix ensures entries survive remount
  - [ ] `npm run typecheck` passes
  - [ ] Bug entry updated in `docs/bugs/frontend.md`
  - [ ] If this session adds or modifies any interface values or fields, update `docs/CONTRACTS.md` in this session — or flag `[INTERFACE IMPACT]` and stop.
- **Context files:**
  - `frontend/src/stores/consoleStore.ts` — full file
  - `frontend/src/api/ws.ts` — onClose/onOpen handlers
  - `frontend/src/utils/consoleMapper.ts` — resetMapperState() (will be called on reconnect after TASK-003)
  - Console page component (find via `grep consoleStore` in frontend/src/pages/ or components/)
  - `docs/bugs/frontend.md` — "Console logs disappear" bug entry
- **Status:** [ ] Not started

---

### TASK-006: [REQUIRES DESIGNER] Disconnect/reconnect UX narrative

- **Layer:** Frontend-UI
- **Agent:** [AGENT: Designer] → then [AGENT: Developer]
- **Estimated effort:** Designer: 30 min spec. Developer: TBD (depends on Designer output).
- **Depends on:** TASK-001 + TASK-002 + TASK-003 (backend and FE-state fixes must be in place so the Designer works from correct state behavior)
- **Scope:**
  - Designer: produce a UI State Behavior artifact defining what the Bridge page shows during each phase of disconnect → crash → waiting → reconnect
  - Developer: implement the Designer's spec
- **Inputs:** Completed TASK-001/002/003, this spec's state transition table, operator feedback ("WAY too slow, needs better visual indication")
- **Outputs:** UI shows clear narrative during the disconnect/reconnect lifecycle — user always knows what's happening and what to expect
- **QA Required:** YES — must verify with live hardware across all disconnect/reconnect scenarios.
- **State Behavior:** `[REQUIRES DESIGNER]` — 5+ components affected (StatusDot, TrafficDot, BridgeStatusPanel, DeviceList, PlayerList, HardwareSelectionPanel), 6+ distinct system states (running, crashed, starting, waiting_for_hardware, reconnecting, recovering). This exceeds the threshold for inline state behavior.
- **Acceptance Criteria:**
  - [ ] Designer produces UI State Behavior artifact using `templates/ui-state-behavior.md`
  - [ ] Artifact covers all states: running (healthy), running (no hardware), crashed (with countdown), starting, waiting_for_hardware (with poll countdown), running (recovering — fresh data arriving)
  - [ ] Artifact defines behavior for: StatusDot, TrafficDot, BridgeStatusPanel status banner, DeviceList, PlayerList, HardwareSelectionPanel
  - [ ] Developer implements the artifact
  - [ ] User can follow the system state narrative during a full power-off → crash → wait → power-on → recovery cycle
  - [ ] `npm run typecheck` passes
- **Context files:**
  - `specs/feat-FE-BLT/spec-disconnect-reconnect.md` — state transition table
  - `frontend/src/components/bridge/*.tsx` — all bridge components
  - `frontend/src/components/layout/TopBar.tsx` — StatusDot, TrafficDot
  - `frontend/src/stores/bridgeStore.ts` — state shape
  - `docs/bugs/frontend.md` — "disconnect/reconnect flow too slow" bug entry
- **Status:** [ ] Not started

---

## State Transition Table (Reference for all tasks)

### Backend Manager States

| State | `_devices` | `_players` | `is_receiving` | FE `dotStatus` |
|-------|-----------|-----------|---------------|----------------|
| `stopped` | empty (cleared) | empty (cleared) | false | disconnected |
| `starting` | empty (cleared) | empty (cleared) | false | disconnected |
| `running` (no hw) | empty | empty | false | connected |
| `running` (hw present) | live data | live data | true | connected |
| `crashed` | empty (cleared) | empty (cleared) | false | disconnected |
| `waiting_for_hardware` | empty (cleared) | empty (cleared) | false | degraded |
| `no_jre` / `no_jar` | empty | empty | false | disconnected |
| `fallback` | may have data | may have data | varies | degraded |

### Key Transitions

| From | Trigger | To | Adapter action | FE action |
|------|---------|-----|---------------|-----------|
| stopped | `start()` | starting | `clear()` | dotStatus → disconnected |
| starting | subprocess + WS OK | running | — | dotStatus → connected; if transitioning from non-running, invalidate route/interface queries |
| running | subprocess dies | crashed | `clear()` (via `_cleanup()`) | dotStatus → disconnected |
| running | WS silent > 2x interval | crashed | `clear()` (via `_cleanup()`) | dotStatus → disconnected |
| running | `stop()` | stopped | `clear()` (via `_cleanup()`) | dotStatus → disconnected |
| crashed | 1st failure | starting | — (already cleared) | dotStatus stays disconnected |
| crashed | 2nd failure (backoff) | starting | — | dotStatus stays disconnected |
| crashed | 3rd failure | waiting_for_hardware | — | dotStatus → degraded |
| waiting_for_hardware | poll + interface available | starting | `clear()` (via `start()`) | dotStatus stays degraded until running |
| waiting_for_hardware | poll + interface unavailable | waiting_for_hardware (skip) | — | no change |
| waiting_for_hardware | user restart | starting | `clear()` (via `restart()`) | dotStatus → disconnected |
