# Section: bridge

## Purpose
Manages the beat-link Java subprocess, WebSocket connection to it, and macOS network route configuration. Produces normalized device and player state for downstream consumption.

## Owned Paths
```
scue/bridge/          — adapter, manager, client, fallback, messages, recorder
scue/network/         — route checking/fixing, interface enumeration
tests/test_bridge/    — all bridge + reconnection tests
```

## Incoming Inputs
- **Config:** `BridgeConfig` from `scue/config/loader.py` (JAR path, port, timeouts)
- **Runtime:** Start/stop/restart commands from `main.py` via `BridgeManager` API

## Outgoing Outputs
- **Types:** `DeviceInfo`, `PlayerState`, `BridgeMessage` (defined in `bridge/adapter.py`, `bridge/messages.py`)
- **Callbacks:** `on_player_update(player_number, PlayerState)`, `on_track_loaded(player_number, track_id)`
- **Status:** `BridgeManager.status` property (running/crashed/waiting_for_hardware/etc.)
- **Network:** `RouteCheckResult`, `RouteFixResult` from `network/models.py`

## Invariants
- Bridge never imports from `layer1`, `layer2`, `layer3`, `layer4`, or `api`.
- `BridgeAdapter` accumulates state per-player; `clear()` must be called on every restart.
- `_last_message_time` must be reset to 0.0 in `start()` (prevents crash cycles).
- Health check silence detection uses ALL WebSocket messages, not just Pioneer traffic.
- macOS route fix is idempotent and guarded by interface existence check.

## Allowed Dependencies
- `scue.network` (same section)
- Python stdlib, `websockets`, `asyncio`
- No `layer1`, `layer2`, `layer3`, `layer4`, `api` imports

## How to Verify
```bash
.venv/bin/python -m pytest tests/test_bridge/ -v
```
All 9+ tests must pass. Tests use mocked WebSocket servers — no real hardware required.
