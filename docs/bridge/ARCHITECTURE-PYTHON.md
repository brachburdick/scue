# Python Bridge Architecture

The Python side of the bridge consumes WebSocket messages from the Java bridge
JAR, normalizes them into SCUE's internal types, and manages the Java subprocess
lifecycle. It also provides a direct UDP fallback when the bridge is unavailable.

## Module Layout

```
scue/bridge/
  __init__.py       # Public API: BridgeManager, BridgeAdapter, FallbackParser
  messages.py       # Message types, dataclasses, JSON parsing
  client.py         # Async WebSocket client
  adapter.py        # Stateful message normalizer (bridge -> Layer 1 types)
  manager.py        # Subprocess lifecycle, health monitoring, auto-restart
  fallback.py       # Direct UDP Pro DJ Link parser (degraded mode)
```

## Data Flow

```
Java bridge JAR (subprocess)
     │
     │  JSON over WebSocket (ws://localhost:17400)
     ▼
  client.py          BridgeWebSocket.listen() → AsyncIterator[BridgeMessage]
     │
     ▼
  manager.py         Routes messages to adapter + external callbacks
     │
     ▼
  adapter.py         Accumulates per-player state, fires typed callbacks
     │
     ├── on_device_change(DeviceInfo, "found"|"lost")
     ├── on_player_update(PlayerState)
     ├── on_beat(player_number, beat_within_bar, bpm)
     └── on_track_loaded(player_number, title, artist)
           │
           ▼
        Layer 1      Receives callbacks, triggers enrichment
```

## messages.py -- Message Types & Parsing

### BridgeMessage

```python
@dataclass
class BridgeMessage:
    type: str               # One of 10 defined types
    timestamp: float        # Unix epoch seconds
    player_number: int | None
    payload: dict           # Type-specific, raw from JSON
```

### 10 Message Types

**Emitted by bridge JAR (v1.2.0):**
- `bridge_status` -- connection state, interface info, warnings/errors
- `device_found` / `device_lost` -- Pioneer hardware discovery
- `player_status` -- per-player BPM, pitch, beat, play state, on-air, rekordbox_id
- `beat` -- real-time beat events

**Defined but NOT emitted by bridge (resolved by Python side per ADR-012):**
- `track_metadata` -- title, artist, key, duration
- `beat_grid` -- beat timestamps and tempos
- `waveform_detail` -- colored waveform data
- `phrase_analysis` -- song structure segments
- `cue_points` -- hot cues, memory cues

### Typed Payloads

Each message type has a corresponding dataclass (e.g., `PlayerStatusPayload`,
`BeatPayload`, `DevicePayload`). Parse via:

```python
msg = parse_message(json_string)          # → BridgeMessage (raw payload dict)
typed = parse_typed_payload(msg)          # → PlayerStatusPayload | BeatPayload | ...
```

Nested types: `BeatGridEntry`, `PhraseEntry`, `CuePoint`, `HotCue`.

## client.py -- WebSocket Client

```python
class BridgeWebSocket:
    async def connect(url: str = "ws://localhost:17400")
    async def disconnect()
    async def listen() -> AsyncIterator[BridgeMessage]  # Yields until disconnect/error
    async def recv_one() -> BridgeMessage | None         # Single message
```

- Automatic JSON deserialization via `parse_message()`
- Logs malformed messages, sets `_connected = False` on close/error
- The manager handles reconnection logic, not the client

## adapter.py -- Stateful Bridge Adapter

The adapter accumulates state from the raw message stream and provides a
higher-level callback interface for Layer 1.

### State Model

```python
@dataclass
class DeviceInfo:
    device_name: str
    device_number: int
    device_type: str          # "cdj" | "djm" | "rekordbox"
    ip_address: str
    last_seen: float
    uses_dlp: bool            # True for XDJ-AZ, Opus Quad, etc.

@dataclass
class PlayerState:
    # Playback (from player_status messages)
    bpm: float
    pitch: float
    beat_within_bar: int      # 1-4
    beat_number: int
    playback_state: str       # "playing"|"paused"|"cued"|"searching"
    is_on_air: bool

    # Metadata (from USB scan via rbox, NOT from bridge)
    title: str
    artist: str
    album: str
    genre: str
    key: str
    duration: float
    rekordbox_id: int

    # Structure data (from USB ANLZ via pyrekordbox, NOT from bridge)
    beat_grid: list[dict]
    phrases: list[dict]
    cue_points: list[dict]
    memory_points: list[dict]
    hot_cues: list[dict]
```

### Callbacks

Register callbacks on the adapter before starting the manager:

```python
adapter = BridgeAdapter()
adapter.on_device_change = lambda dev, action: ...
adapter.on_player_update = lambda player: ...
adapter.on_beat = lambda pn, beat_in_bar, bpm: ...
adapter.on_track_loaded = lambda pn, title, artist: ...
```

### Track Change Detection (ADR-012)

The adapter detects track changes by monitoring `rekordbox_id` in `player_status`
messages. When the ID changes to a nonzero value different from the current one,
`on_track_loaded` fires. The Python side then resolves metadata via rbox.

**XDJ-AZ caveat:** `rekordbox_id` can differ between paused and playing states
for the same track. The adapter only fires on nonzero changes to avoid false
triggers.

### Message Dispatch

```python
_HANDLERS = {
    "bridge_status":    _handle_bridge_status,
    "device_found":     _handle_device_found,
    "device_lost":      _handle_device_lost,
    "player_status":    _handle_player_status,
    "beat":             _handle_beat,
    "track_metadata":   _handle_track_metadata,    # deprecated (ADR-012)
    "beat_grid":        _handle_beat_grid,          # deprecated (ADR-012)
    "phrase_analysis":  _handle_phrase_analysis,
    "cue_points":       _handle_cue_points,
}
```

### State Access

```python
adapter.devices          # dict[str, DeviceInfo] keyed by IP
adapter.players          # dict[int, PlayerState] keyed by player number
adapter.get_player(1)    # PlayerState | None
adapter.bridge_connected # bool
adapter.bridge_version   # str
```

## manager.py -- Subprocess Lifecycle

### State Machine

```
stopped ──→ starting ──→ running ──→ (monitor loop)
   ▲                         │
   │                         ▼
   └──── crashed ←───── subprocess died
              │
              └──→ restart with exponential backoff
```

Additional terminal states:
- `no_jre` -- Java not found on PATH
- `no_jar` -- JAR missing at expected path (`lib/beat-link-bridge.jar`)
- `fallback` -- (planned) degraded UDP mode

### Initialization

```python
manager = BridgeManager(
    jar_path=Path("lib/beat-link-bridge.jar"),  # default
    port=17400,                                  # default
    network_interface="en16",                    # optional
    on_message=callback,                         # optional external callback
)
await manager.start()
```

### Subprocess Launch

```bash
java -jar lib/beat-link-bridge.jar --port 17400 [--interface en16]
```

The manager:
1. Checks `java` is on PATH (otherwise → `no_jre`)
2. Checks JAR exists (otherwise → `no_jar`)
3. Launches subprocess
4. Waits up to 10 seconds for WebSocket to accept connections
5. Connects WebSocket client
6. Starts listen loop (routes messages to adapter)
7. Starts health check loop

### Health Monitoring

Every `HEALTH_CHECK_INTERVAL` (10 seconds):
- Check subprocess exit code (crash detection)
- Check message freshness (if silent > 2x interval, force restart)

On crash: exponential backoff restart: `min(2^count, 30)` seconds.

### macOS Route Check

On startup, `_check_macos_route()` validates that the OS broadcast route for
`169.254.255.255` points to the configured network interface. Logs a warning with
the fix command if wrong. Does not attempt to fix it (requires sudo).

### Status Reporting

```python
status = manager.to_status_dict()
# {
#   "state": "running",
#   "bridge_connected": True,
#   "bridge_version": "1.2.0",
#   "network_interface": "en16",
#   "devices": [...],
#   "players": {...},
# }
```

## fallback.py -- Direct UDP Fallback

When the bridge JAR is unavailable (no JRE, no JAR, or persistent crashes), the
fallback parser provides degraded mode by directly parsing Pro DJ Link UDP
broadcasts.

### Capabilities (degraded mode)

| Feature | Available |
|---------|-----------|
| Device discovery | Yes |
| BPM | Yes |
| Pitch | Yes |
| Beat position (within bar) | Yes |
| Play/pause state | Yes |
| On-air flag | Yes |
| Track metadata | **No** |
| Beatgrid | **No** |
| Cue points | **No** |
| Phrase analysis | **No** |
| Waveform | **No** |

### Protocol Details

- Announce port: 50001 (keepalive packets for device discovery)
- Status port: 50000 (CDJ status packets with playback data)
- Magic bytes: `0x51 0x73 0x70 0x74 0x4e 0x1e` ("QsptN\x1e")
- Keepalive packet type: `0x06` at offset `0x0A`
- Status packet type: `0x0A` at offset `0x0A`

### Platform-Specific Socket Binding

**macOS:** Must use `IP_BOUND_IF` (constant 25) to receive broadcasts on a
specific interface. Binding to a unicast IP silently drops broadcast packets.

```python
IP_BOUND_IF = 25
sock.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, socket.if_nametoindex(iface_name))
sock.bind(("", port))  # Bind to INADDR_ANY, not unicast IP
```

**Linux:** Use `SO_BINDTODEVICE`:
```python
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, (iface_name + "\x00").encode())
```

See PITFALLS.md for the full explanation of this macOS quirk.

### Interface

Emits the same `BridgeMessage` objects as the full bridge, so the manager can
swap transparently:

```python
parser = FallbackParser(on_message=callback)
await parser.start()   # Bind UDP sockets, start listening
parser.stop()          # Close sockets
parser.packet_count    # Diagnostic counter
parser.last_packet_time # For staleness detection
```

## USB Metadata Resolution

Per ADR-012 and ADR-013, track metadata and ANLZ data are resolved by the Python
side, not the bridge. The flow is:

```
USB plugged in
     │
     ▼
  usb_scanner.py        read_usb_library() via rbox OneLibrary
     │                    → list[UsbTrack] with title, artist, BPM, key
     │
     ▼
  usb_scanner.py        _read_anlz_data() for each track
     │                    Tier 1: pyrekordbox AnlzFile.parse_file()
     │                    Tier 2: custom anlz_parser.py (PQTZ + PCOB only)
     │                    → beatgrid, hot_cues, memory_points
     │
     ▼
  usb_scanner.py        match_usb_tracks() links rekordbox_id → fingerprint
     │
     ▼
  storage.py            Cache Pioneer metadata for enrichment during live set
```

During the live set, when the bridge reports a new `rekordbox_id` via
`player_status`, the Python side looks up the cached metadata by rekordbox ID
and triggers the enrichment pass.

### Library Responsibilities

| Library | Used For | Failure Mode |
|---------|----------|--------------|
| rbox OneLibrary | `exportLibrary.db` reading (DLP format) | ImportError if not installed |
| pyrekordbox AnlzFile | ANLZ parsing (Tier 1, full support) | Exception on ~0.2% of files |
| custom anlz_parser | ANLZ parsing (Tier 2, PQTZ + PCOB only) | AnlzParseError |
| librosa | Offline beat tracking (fallback when no Pioneer data) | Always available |

See PITFALLS.md for detailed API gotchas with each library.

## Testing

```bash
python -m pytest tests/test_bridge/ -v
```

### Test Modules

| Module | Tests | Covers |
|--------|-------|--------|
| `test_messages.py` | Message parsing, all 10 types, fixture loading | messages.py |
| `test_adapter.py` | State accumulation, callbacks, track change detection | adapter.py |
| `test_manager.py` | State machine, subprocess launch, status dict | manager.py |
| `test_network_interface.py` | Interface config, CLI args, bridge_status fields | manager.py |

### Test Fixtures

`tests/fixtures/bridge/` contains JSON message sequences:
- `device_discovery.json` -- device found/lost cycle
- `playback_session.json` -- full play session with beats
- `track_metadata.json` -- metadata messages (deprecated path)
- `transition.json` -- two-deck transition with on-air changes

### Mock Bridge

`tools/mock_bridge.py` replays fixture files over WebSocket for integration
testing without Pioneer hardware.
