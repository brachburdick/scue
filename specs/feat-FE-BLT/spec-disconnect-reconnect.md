# Spec: Bridge Disconnect/Reconnect Lifecycle Fix

## Summary

Fix the interconnected bridge disconnect/reconnect bugs by addressing the root causes across the full data flow: backend adapter state retention, manager crash-loop behavior, frontend query staleness, and UX feedback gaps. Six open/partial bugs trace back to a shared set of 9 gaps in the current implementation.

## User-Facing Behavior

When Pioneer hardware disconnects (board powered off, adapter unplugged), the UI should:
1. Clear device and player data promptly — no stale entries
2. Show a clear status narrative throughout the crash-restart-recovery sequence
3. Settle into a stable "waiting for hardware" state without a crash-restart loop
4. On hardware return: recover automatically, repopulate with fresh data, clear route warnings
5. Console logs persist across reconnects — no disappearing entries

## Technical Requirements

### TR-1: Adapter state cleared on crash/cleanup
- `BridgeAdapter` must expose a `clear()` method that resets `_devices = {}` and `_players = {}`
- `BridgeManager._cleanup()` must call `self._adapter.clear()` before any restart
- `BridgeManager.start()` must call `self._adapter.clear()` before launching subprocess (belt-and-suspenders)
- AC: After crash → restart, `to_status_dict()` returns `devices={}`, `players={}` until fresh `device_found`/`player_status` messages arrive from the new bridge session

### TR-2: Pioneer message timestamp reset on start
- `BridgeManager.start()` must reset `self._last_pioneer_message_time = 0.0` alongside the existing `_last_message_time = 0.0` reset
- AC: After restart, `pioneer_status.is_receiving` is `false` until fresh Pioneer traffic arrives — no false-positive from stale timestamp

### TR-3: Interface pre-check in hardware poll loop
- `_wait_for_hardware_loop()` must check interface availability before calling `start()`
- Check: configured interface exists in system interface list (e.g., via `socket.if_nametoindex()` or equivalent)
- If interface unavailable: log at debug level, skip this poll cycle, continue waiting
- If interface available: proceed with `start()` as currently implemented
- AC: When hardware is off and interface is missing, no crash-restart cycles occur — bridge stays in `waiting_for_hardware` with zero subprocess launches until the interface reappears

### TR-4: Route and interface queries invalidated on bridge reconnect
- When the frontend receives a `bridge_status` message where `status` transitions to `"running"` from any non-running state, invalidate TanStack queries: `["network", "route"]` and `["network", "interfaces"]`
- Implementation location: `frontend/src/api/ws.ts` dispatch function (keeps stores pure)
- AC: After bridge auto-reconnect, route mismatch warning clears without user clicking "Fix Now"

### TR-5: Interface score accounts for active traffic and route state
- Backend interface scoring must factor in: (a) whether Pioneer traffic is currently flowing on the interface, (b) whether the macOS broadcast route points to the interface
- AC: An interface with active traffic and correct route scores higher than one without

### TR-6: Console mapper state reset on WS reconnect
- Call `resetMapperState()` in `ws.ts` `onOpen()` handler before dispatching any messages
- AC: After WS reconnect, the first `bridge_status` message generates appropriate console entries (treated as fresh session start, not diff from pre-disconnect state)
- AC: Existing console entries from before the disconnect are preserved (ring buffer not flushed)

### TR-7: Console logs survive reconnect
- Investigate and fix the root cause of console entries disappearing on bridge reconnect
- The `consoleStore` ring buffer must not be flushed on WS reconnect events
- If the issue is in a React component (unmount/remount clearing state), fix the component
- AC: Console entries from before disconnect remain visible after reconnect

## Interface Definitions

### Proposed change: None to bridge_status payload

No new fields needed. Clearing adapter state at the source (TR-1) eliminates stale data from `to_status_dict()` without requiring a `connection_epoch` or similar marker.

### Internal change: BridgeAdapter.clear()

```python
# In scue/bridge/adapter.py
class BridgeAdapter:
    def clear(self) -> None:
        """Clear all accumulated device and player state.

        Called by BridgeManager on crash/cleanup/restart so that
        to_status_dict() never includes stale data from a dead session.
        """
        self._devices.clear()
        self._players.clear()
```

### Internal change: BridgeManager.start() additions

```python
# In scue/bridge/manager.py, inside start()
async def start(self) -> None:
    if self._status == "running":
        return
    self._last_message_time = 0.0          # existing
    self._last_pioneer_message_time = 0.0   # NEW — prevents false-positive is_receiving
    self._adapter.clear()                   # NEW — prevents stale data in to_status_dict()
    self._status = "starting"
    ...
```

### Internal change: _wait_for_hardware_loop pre-check

```python
# In scue/bridge/manager.py, inside _wait_for_hardware_loop()
import socket

async def _wait_for_hardware_loop(self) -> None:
    while self._status == "waiting_for_hardware":
        ...
        await asyncio.sleep(_HARDWARE_POLL_INTERVAL_S)
        ...
        # Pre-check: skip restart if interface doesn't exist
        if self._network_interface:
            try:
                socket.if_nametoindex(self._network_interface)
            except OSError:
                logger.debug(
                    "Interface %s not available — skipping restart attempt",
                    self._network_interface,
                )
                continue
        await self.start()
```

## Layer Boundaries

- **Layer 0 (Backend — bridge):** adapter.py, manager.py — state clearing, timestamp reset, interface pre-check
- **API layer:** ws.py — pioneer_status correctness (inherits from manager timestamp fix)
- **Frontend-State:** ws.ts, bridgeStore.ts — query invalidation, console mapper reset
- **Frontend-UI:** bridge components — UX narrative during disconnect/reconnect sequence
- **Backend — network:** scoring logic in network API — interface score calculation

Interface between Layer 0 and Frontend: `bridge_status` WebSocket message (payload shape unchanged).
Interface between API and Frontend: `pioneer_status` WebSocket message (payload shape unchanged).

## Constraints

- `bridge_status` payload shape must NOT change — no new fields, no removed fields
- `pioneer_status` payload shape must NOT change
- Zustand stores must remain independent silos — no store imports another store
- Frontend query invalidation must live in `ws.ts`, not in stores
- Backend adapter clearing must happen in `_cleanup()` AND `start()` for defense-in-depth

## Out of Scope

- Bridge Java subprocess stability (beat-link crash behavior is upstream)
- `mock_bridge.py` enhancements for simulating hardware-absent scenarios
- Orphaned Java process cleanup (SC-013) — tracked separately
- `fix_route_endpoint()` bypassing manager's error wrapping (SC-014) — tracked separately
- Full Designer-driven UX redesign of the Bridge page layout

## Open Questions

All [DECISION NEEDED] items resolved by operator:
1. Crash-restart loop: Option A (interface pre-check before restart) — APPROVED
2. connection_epoch: Option A (don't add, clearing is sufficient) — APPROVED
3. Interface score: Option A (include in this task breakdown) — APPROVED

## Edge Cases

- **Interface name changes on re-plug:** USB-Ethernet adapter may get a different interface name (e.g., en7 → en16) when plugged into a different USB port. The interface pre-check uses the configured name, so a name change requires the user to update the interface selection. This is existing behavior and out of scope.
- **Multiple boards, one powered off:** `device_lost` fires for the powered-off board only. The adapter `clear()` is only called on full crash/restart, not on individual device loss. Individual device loss is handled correctly by `_handle_device_lost()`.
- **WS reconnect without bridge restart:** If only the frontend WS drops and reconnects (backend stays up), the initial `bridge_status` from the server contains current (non-stale) data. The query invalidation still fires, which is harmless (re-fetches current data).
- **Rapid crash-restart with brief "running" windows:** After adapter clearing fix, the brief "running" state will show empty devices/players (correct). The StatusDot will flash green briefly. This is acceptable — a full UX fix for the flash is [REQUIRES DESIGNER] work.
