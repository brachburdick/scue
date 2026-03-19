# Skill: Beat-Link Bridge / Pro DJ Link Protocol

> **When to use:** Any task involving Layer 0 (bridge), Pioneer hardware communication, or the Java bridge subprocess.

---

## Stack & Environment

- Java bridge subprocess (`bridge-java/`) wraps the beat-link library
- Communicates with Python via WebSocket (JSON messages)
- Python adapter in `scue/bridge/adapter.py` translates bridge events
- Bridge lifecycle managed by `scue/bridge/manager.py`
- Fallback mode in `scue/bridge/fallback.py` for direct UDP parsing

## Architecture

```
Pioneer CDJs/XDJs → Pro DJ Link (UDP) → beat-link (Java) → WebSocket → Python adapter → Layer 1
```

## Common Patterns

### Bridge Process Management
- Bridge is a managed subprocess — Python starts/stops the Java process
- `BridgeManager` handles lifecycle, restarts, and health checks
- `BridgeAdapter` translates raw bridge events into Python dataclasses

### Message Types
- Defined in `scue/bridge/messages.py`
- All messages are JSON over WebSocket
- Key message types: beat, status, track_change, device_found

## Known Gotchas

- **`is_receiving` vs `bridge_connected`:** `is_receiving` means Pioneer hardware traffic is flowing, NOT that the bridge process is alive. Use `bridge_connected` for process liveness. Fixed 2026-03-17: `_last_pioneer_message_time` is now separate from `_last_message_time`.
- **macOS network binding:** beat-link may bind to the wrong interface on macOS. Route must be fixed before starting. See `scue/network/route.py`.
- **MetadataFinder fails on XDJ-AZ:** Device Library Plus format not supported by beat-link's MetadataFinder. Use rbox/pyrekordbox instead (ADR-012).
- **XDJ-AZ track change detection:** `trackType` doesn't transition through `NO_TRACK` on XDJ-AZ. Must use multiple signals for detection.
- **UDP broadcast reception on macOS:** Requires `IP_BOUND_IF` socket option.

## Anti-Patterns

- Using bare `python` to run bridge-related code (use `.venv/bin/python`)
- Assuming bridge is always connected — handle degraded/fallback mode
- Directly parsing UDP in Python when the Java bridge is available
- [TODO: Fill from project experience]
