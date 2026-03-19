# Task Spec: Traffic Detected but Device Never Discovered (Blocker)

**Source:** Audit 2026-03-17, Domain A (Layer 0) — `docs/bugs/layer0-bridge.md` open issue
**Priority:** Blocker
**Touches:** `scue/bridge/adapter.py`, `scue/api/ws.py`, possibly `lib/beat-link-bridge.jar`
**Layer boundary:** L0 + API — does not cross into L1

## Problem

The bridge reports `is_receiving: true` (Pioneer UDP traffic is arriving) but the `devices` dict stays empty — `device_found` events never fire. This means:

- The frontend shows "Pioneer traffic detected but no devices discovered"
- No `PlayerState` updates flow to Layer 1
- No cursors, no enrichment, no live tracking

The bug manifests when Pioneer hardware (XDJ-AZ confirmed) is connected and actively broadcasting, but beat-link's `DeviceAnnouncement` listener doesn't trigger.

## Investigation Plan

### Hypothesis 1: Traffic receipt ≠ device discovery

The `is_receiving` flag in `ws.py:56` is set based on `_last_message_time` — meaning *any* bridge message updates it. But `device_found` requires beat-link's `DeviceAnnouncementListener` to fire, which requires a full Pro DJ Link handshake (not just UDP keepalives).

**Check:** Does the bridge JAR receive keepalive packets but fail the device announcement handshake? This could happen if:
- The bridge's own "virtual CDJ" can't claim a player number (network conflict)
- The broadcast route is correct but the bridge binds to the wrong interface internally
- beat-link's `DeviceFinder.start()` needs explicit interface configuration that isn't being passed

### Hypothesis 2: Bridge status messages arrive but device messages don't

The bridge sends `bridge_status` messages on its own heartbeat. These update `_last_message_time` and make `is_receiving = true`. But if `DeviceFinder` never starts or silently fails, `device_found` messages never emit.

**Check:** Add logging in the Java bridge's `DeviceAnnouncementListener` to confirm whether announcements are received at the Java layer.

### Hypothesis 3: Adapter drops device_found messages

The adapter's `_handle_device_found()` could be silently failing (e.g., missing payload field, exception swallowed).

**Check:** Review adapter handler for error cases. Check test fixtures against real XDJ-AZ device_found payloads.

## Diagnostic Steps

1. **Bridge-side logging:** Check `lib/beat-link-bridge.jar` logs (stdout/stderr captured by manager) for DeviceFinder status. If no device announcements logged at Java level → problem is in beat-link/network, not Python.

2. **Fallback parser comparison:** Run `FallbackParser` alongside bridge. If fallback sees `DEVICE_FOUND` (via raw keepalive parsing) but bridge doesn't → confirms beat-link handshake issue.

3. **Message trace:** Add temporary debug logging in `adapter.py:handle_message()` to log every message type received. Confirm whether `device_found` messages are absent from the stream or present but failing to parse.

4. **Network interface verification:** Confirm bridge subprocess is using the correct interface. Check `bridge_status` payload's `network_interface` field matches the configured interface in `config/bridge.yaml`.

## Resolution Paths

| Root cause | Fix |
|---|---|
| beat-link DeviceFinder not starting | Fix bridge JAR startup sequence; ensure DeviceFinder.start() called after interface binding |
| Bridge status heartbeat inflates is_receiving | Separate `is_receiving` into two flags: `bridge_connected` (bridge process alive) vs `pioneer_traffic` (device/beat messages received) |
| Adapter drops device_found | Fix payload handling in adapter |
| Interface mismatch at Java level | Pass `--interface` flag correctly; verify bridge_status payload reflects actual bound interface |

## Relationship to Other Issues

- **Frontend flicker bug (open):** The `is_receiving` flicker during playback is likely a *symptom* of this same root cause — if no devices are discovered, the only messages updating `_last_message_time` are bridge heartbeats, which are periodic and create the flicker pattern.
- **Fallback parser integration:** If this bug proves to be a beat-link limitation with certain hardware, the fallback parser becomes the primary path — making the fallback integration spec higher priority.

## Test Plan (post-fix)

- [ ] Integration: Bridge with mock Pioneer device → device_found fires within 5s
- [ ] Unit: `is_receiving` only true when device/player/beat messages received (not just bridge_status)
- [ ] Unit: Adapter correctly handles device_found from real XDJ-AZ payload
- [ ] Regression: Frontend shows device cards when devices are discovered

## Files Likely Involved

| File | Investigation |
|------|------|
| `scue/api/ws.py` | `_build_pioneer_status()` — should `is_receiving` require device messages? |
| `scue/bridge/adapter.py` | `_handle_device_found()` — error handling review |
| `scue/bridge/manager.py` | Bridge subprocess launch — interface flag passing |
| `lib/beat-link-bridge.jar` | Java-side DeviceFinder startup and logging |
| `config/bridge.yaml` | Interface configuration verification |
