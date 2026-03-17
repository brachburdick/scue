# Beat-Link Bridge JAR — Specification

## Overview

SCUE needs access to the Pro DJ Link protocol to receive real-time playback data (BPM, pitch, beat position, play/pause state, on-air status) from Pioneer DJ hardware. The open-source [beat-link](https://github.com/Deep-Symmetry/beat-link) Java library (~30K lines) implements this protocol. Rather than porting it to Python, SCUE runs beat-link as a managed subprocess that streams typed JSON messages over a local WebSocket.

**Per ADR-012 (v1.1.0):** The bridge provides **real-time playback data only**. Track metadata (title, artist, key), beatgrids, waveforms, phrase analysis, and cue points are **not** emitted by the bridge. Metadata resolution is handled by the Python side via `rbox` (for DLP hardware) or future extensions (for legacy hardware). This was driven by the discovery that beat-link's MetadataFinder returns incorrect data on Device Library Plus hardware (XDJ-AZ, Opus Quad, CDJ-3000X) due to DLP vs DeviceSQL ID namespace conflicts.

This document specifies the Java bridge application. The Python consumer side is already built and tested (`scue/bridge/`). The JAR is built and deployed at `lib/beat-link-bridge.jar` (v1.1.0).

## Architecture

```
Pioneer Hardware (CDJ/XDJ/DJM on Pro DJ Link network)
         │
         │  UDP broadcasts (ports 50000, 50001)
         ▼
┌─────────────────────────┐
│  beat-link-bridge.jar   │  ← THIS COMPONENT
│  (Java 11+ subprocess)  │
│                         │
│  WebSocket server on    │
│  ws://localhost:17400   │
└──────────┬──────────────┘
           │  JSON messages
           ▼
┌─────────────────────────┐
│  SCUE Python process    │  ← Already built
│  scue/bridge/client.py  │
│  scue/bridge/adapter.py │
└─────────────────────────┘
```

## What the JAR Must Do

1. Start beat-link's `DeviceAnnouncement` listener and `VirtualCdj` instance
2. Connect to the Pro DJ Link network (auto-discover interface)
3. Start `BeatFinder` for real-time beat events
4. Start a WebSocket server on a configurable port (default: 17400)
5. Translate each beat-link event into a typed JSON message (schemas below)
6. Stream messages to all connected WebSocket clients
7. Accept a `--port <N>` CLI argument for the WebSocket port

**Not started (per ADR-012):** MetadataFinder, BeatGridFinder, WaveformFinder, CrateDigger, AnalysisTagFinder. These are stripped from the JAR.

## beat-link API Entry Points

The bridge uses only these beat-link classes (v1.1.0 lean bridge per ADR-012):

| Class | Purpose |
|-------|---------|
| `org.deepsymmetry.beatlink.DeviceFinder` | Device discovery (CDJs, DJMs appearing/disappearing) |
| `org.deepsymmetry.beatlink.DeviceAnnouncementListener` | Callbacks for device found/lost events |
| `org.deepsymmetry.beatlink.VirtualCdj` | Core connection to the Pro DJ Link network + CdjStatus updates |
| `org.deepsymmetry.beatlink.CdjStatus` | Per-player playback state (BPM, pitch, beat, play/pause, on-air, rekordbox_id) |
| `org.deepsymmetry.beatlink.BeatFinder` | Real-time beat events |
| `org.deepsymmetry.beatlink.Beat` | Beat event data |

**Stripped (per ADR-012):** MetadataFinder, BeatGridFinder, WaveformFinder, CrateDigger, AnalysisTagFinder. These are incompatible with Device Library Plus hardware and cause incorrect metadata on XDJ-AZ, Opus Quad, CDJ-3000X, OMNIS-DUO.

## Message Types and JSON Schemas

**v1.1.0 (ADR-012):** The bridge emits 5 message types. Track metadata, beatgrids, waveforms, phrase analysis, and cue points are resolved by the Python side, not the bridge.

All messages follow this envelope:

```json
{
  "type": "<message_type>",
  "timestamp": 1710600001.5,
  "player_number": 1,
  "payload": { ... }
}
```

- `timestamp`: Unix epoch seconds (float, millisecond precision)
- `player_number`: Integer (1-4 for CDJs, null for non-player messages)
- `payload`: Type-specific object (schemas below)

### bridge_status
Sent once on startup and whenever bridge state changes.

```json
{
  "type": "bridge_status",
  "timestamp": 1710600000.0,
  "player_number": null,
  "payload": {
    "connected": true,
    "devices_online": 3,
    "version": "1.2.0",
    "network_interface": "en5",
    "network_address": "169.254.20.1",
    "interface_candidates": [
      { "name": "en5", "address": "169.254.20.1", "type": "ethernet", "score": 15, "selected": true },
      { "name": "en7", "address": "10.0.0.5", "type": "ethernet", "score": 8, "selected": false },
      { "name": "en0", "address": "192.168.1.100", "type": "wifi", "score": 3, "selected": false }
    ]
  }
}
```

- `network_interface`: Name of the interface the bridge bound to (e.g. `en5`)
- `network_address`: IP address of the bound interface
- `interface_candidates`: All scored candidate interfaces (for UI display). Each entry: `name`, `address`, `type` (ethernet/wifi/virtual), `score`, `selected` (bool).
- `warning`: Optional — set when configured interface was not found or down and auto-detect was used as fallback
- `error`: Optional — set on startup failures (player number conflict, etc.)

### device_found / device_lost
Sent when a Pioneer device appears or disappears on the network.

```json
{
  "type": "device_found",
  "timestamp": 1710600001.0,
  "player_number": 1,
  "payload": {
    "device_name": "XDJ-AZ",
    "device_number": 1,
    "device_type": "cdj",
    "ip_address": "169.254.20.101",
    "uses_dlp": true
  }
}
```

- `device_type`: `"cdj"` | `"djm"` | `"rekordbox"`
- `player_number`: set for CDJs (1-4), null for DJMs
- `uses_dlp`: `true` for Device Library Plus hardware (XDJ-AZ, Opus Quad, CDJ-3000X, OMNIS-DUO). Detected by matching device name against known DLP models. The Python side uses this to choose the metadata resolution path (rbox vs legacy).

### player_status
Sent on every `CdjStatus` update (~5Hz per player).

```json
{
  "type": "player_status",
  "timestamp": 1710600021.0,
  "player_number": 1,
  "payload": {
    "bpm": 128.0,
    "pitch": 2.5,
    "beat_within_bar": 3,
    "beat_number": 42,
    "playback_state": "playing",
    "is_on_air": true,
    "track_source_player": 1,
    "track_source_slot": "usb",
    "track_type": "rekordbox",
    "rekordbox_id": 42001
  }
}
```

- `bpm`: Effective BPM (after pitch adjustment). Returns 0.0 when paused.
- `pitch`: Pitch adjustment as percentage (e.g., 2.5 means +2.5%)
- `beat_within_bar`: 1-4 (cycles correctly during playback; static when paused)
- `playback_state`: `"playing"` | `"paused"` | `"cued"` | `"searching"`
- `is_on_air`: `true` only when BOTH channel fader is up AND master knob is not off
- `track_source_slot`: `"sd"` | `"usb"` | `"cd"` | `"collection"`
- `rekordbox_id`: DLP track ID from CdjStatus. **Warning:** On XDJ-AZ, this value can differ between paused and playing states for the same track. The Python adapter handles this by firing `on_track_loaded` only when the ID changes to a nonzero value different from the current one.

### beat
Real-time beat events (~2Hz at 128 BPM). High frequency — keep payloads small.

```json
{
  "type": "beat",
  "timestamp": 1710600021.469,
  "player_number": 1,
  "payload": {
    "beat_within_bar": 2,
    "bpm": 128.0,
    "pitch": 0.0
  }
}
```

### Messages NOT emitted by the bridge (per ADR-012)

The following message types are defined in the Python adapter (`scue/bridge/messages.py`) for future use but are **not emitted by the v1.1.0 bridge JAR**. They will be populated by the Python side reading directly from USB databases:

- `track_metadata` — resolved via `rbox` (DLP) or future bridge extensions (legacy)
- `beat_grid` — resolved via `rbox` (DLP) or future bridge extensions (legacy)
- `waveform_detail` — resolved via `rbox` (DLP) or future bridge extensions (legacy)
- `phrase_analysis` — resolved via `rbox` (DLP) or future bridge extensions (legacy)
- `cue_points` — resolved via `rbox` (DLP) or future bridge extensions (legacy)

## Message Ordering

The bridge continuously emits:
- `player_status` (~5Hz per player)
- `beat` (on each beat during playback)
- `device_found` / `device_lost` (on device discovery changes)
- `bridge_status` (on state changes)

## Build Requirements

- **Language**: Java 11+
- **Build tool**: Gradle (recommended) or Maven
- **Key dependency**: `org.deepsymmetry:beat-link:0.6.3` (or latest)
- **WebSocket library**: Any Java WebSocket server (e.g., `org.java-websocket:Java-WebSocket`)
- **JSON library**: Gson or Jackson
- **Output**: Single fat JAR (`beat-link-bridge.jar`) with all dependencies bundled
- **CLI**: Accept `--port <N>` argument (default: 17400)

## Deployment

The built JAR goes in `lib/beat-link-bridge.jar` in the SCUE project root. SCUE's Python `BridgeManager` launches it via:

```
java -jar lib/beat-link-bridge.jar --port 17400
```

The manager monitors the subprocess, restarts on crash with exponential backoff, and connects via WebSocket.

## Testing

The Python side has fixture files in `tests/fixtures/bridge/` that define the expected message format. The mock bridge tool (`tools/mock_bridge.py`) replays these fixtures over WebSocket. To verify the Java bridge produces compatible output:

1. Run the Java bridge with Pioneer hardware connected
2. Capture messages using a WebSocket client
3. Validate JSON structure matches the schemas above
4. Compare with fixture files for format compatibility

## Network Notes

- Pioneer hardware uses link-local addresses (169.254.x.x) by default
- beat-link handles network interface discovery automatically
- On macOS, beat-link may need the network interface with Pioneer hardware to be active
- The bridge should log which interface it binds to for debugging

## Appendix: Additional Requirements

Paste this at the end of the existing spec document, before any closing notes.

---

## Startup Sequence

beat-link has a strict initialization order. The bridge must follow this sequence:

```
1. Parse CLI arguments (--port, --player-number, --interface)
2. Start WebSocket server on configured port
3. Emit bridge_status { connected: false, devices_online: 0 }
4. Run network interface selection (see § Network Interface Discovery and Selection)
   └─ If --interface provided: validate the named interface (Layer 2)
   └─ Otherwise: auto-detect with scoring (Layer 1)
   └─ Run startup validation (Layer 3)
5. DeviceFinder.getInstance().start()
6. VirtualCdj.getInstance().setDeviceNumber(playerNumber)
7. VirtualCdj.getInstance().setUseInterface(selectedInterface)
8. VirtualCdj.getInstance().start()
   └─ This BLOCKS until it joins the network or times out (~10s)
   └─ If timeout: log warning, emit bridge_status { connected: false }
      The WebSocket server stays running. Retry on a configurable interval (default 10s).
9. BeatFinder.getInstance().start()
10. Register listeners for DeviceAnnouncement, CdjStatus, Beat
11. Emit bridge_status { connected: true, devices_online: N, network_interface: ..., interface_candidates: [...] }
```

**Per ADR-012:** Steps 7-11 from the original spec (MetadataFinder, BeatGridFinder, WaveformFinder, CrateDigger, AnalysisTagFinder) are removed. Only BeatFinder is started.

**Critical:** The WebSocket server must start BEFORE beat-link initialization (step 2 before step 4). This ensures the Python manager can connect and receive status messages even if beat-link fails to find hardware. The Python side uses the WebSocket connection itself as a health check — if it can't connect, the bridge process is dead. If it connects but receives `connected: false`, the bridge is alive but no hardware is present.

**Retry behavior:** If VirtualCdj fails to join the network at step 6, the bridge should retry periodically (every 10 seconds) rather than exiting. Hardware may be powered on after the bridge starts. On successful join, proceed to steps 7–13 and emit an updated `bridge_status`.

## CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--port <N>` | `17400` | WebSocket server port |
| `--player-number <N>` | `5` | Player number to claim on the Pro DJ Link network. Must not conflict with connected CDJs (typically 1–4). Values 5–6 are conventional for software players. If the number is taken, startup will fail — log the error clearly. |
| `--interface <name>` | (auto-detect) | Network interface name to bind to (e.g., `en5`, `eth0`). If the interface is not found or is down, falls back to auto-detection with a warning. |
| `--log-level <LEVEL>` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `--retry-interval <S>` | `10` | Seconds between network join retries when no hardware is found |

## Graceful Shutdown

When the process receives SIGTERM (or SIGINT):

1. Log "Shutting down beat-link bridge..."
2. `BeatFinder.getInstance().stop()`
3. `VirtualCdj.getInstance().stop()` — this announces departure from the Pro DJ Link network. Without this, Pioneer hardware shows a phantom device for up to 30 seconds.
4. `DeviceFinder.getInstance().stop()`
5. Close all WebSocket connections
6. Stop WebSocket server
7. `System.exit(0)`

Register a JVM shutdown hook to ensure this sequence runs even on unexpected termination:

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    // steps 1-7 above
}));
```

## Logging

**All log output goes to stderr**, not stdout. This allows the Python manager to capture bridge logs separately from any JVM stdout output.

Log format:
```
[2025-03-16T14:30:00.123Z] [INFO] Bridge started on port 17400
[2025-03-16T14:30:00.456Z] [INFO] Claiming player number 5
[2025-03-16T14:30:10.789Z] [WARN] VirtualCdj failed to join network, retrying in 10s
[2025-03-16T14:30:20.123Z] [INFO] Joined Pro DJ Link network on interface en0 (169.254.20.1)
[2025-03-16T14:30:20.456Z] [INFO] Found device: XDJ-AZ (player 1) at 169.254.20.101
```

Include timestamps (ISO 8601 with milliseconds), log level, and human-readable message. Log the network interface name and IP when joining the network — this is critical for debugging connectivity issues.

**What to log at each level:**
- `DEBUG`: Every message sent over WebSocket, raw beat-link event details
- `INFO`: Startup/shutdown, network join/leave, device discovery, track loads
- `WARN`: Network join timeout (retrying), MetadataFinder unable to retrieve data for a track, WebSocket client disconnect
- `ERROR`: Uncaught exceptions, player number conflict, WebSocket server bind failure

## Error Handling

**Player number conflict:** If `VirtualCdj.start()` fails because the claimed player number is already taken, log an ERROR with the conflicting device info and emit a `bridge_status` with `connected: false` and an `error` field:

```json
{
  "type": "bridge_status",
  "timestamp": 1710600000.0,
  "player_number": null,
  "payload": {
    "connected": false,
    "devices_online": 0,
    "version": "1.0.0",
    "error": "Player number 5 is already in use by device at 169.254.20.50"
  }
}
```

**WebSocket client disconnect:** If the Python client disconnects, keep the bridge running. It will reconnect. Log the disconnect at WARN level and the reconnect at INFO.

**Uncaught exceptions in listeners:** Wrap all beat-link listener callbacks in try-catch. An exception in one listener must not crash the bridge or prevent other listeners from firing. Log the exception at ERROR and continue.

## DLP Device Detection

The bridge detects Device Library Plus hardware by matching the device name (lowercased) against known DLP models: `xdj-az`, `opus-quad`, `omnis-duo`, `cdj-3000x`. When a DLP device is found, the `device_found` message includes `"uses_dlp": true`. The Python adapter uses this flag to choose the correct metadata resolution path.

## Known Issues

### macOS link-local broadcast routing
macOS assigns the 169.254.255.255 broadcast route to whichever link-local interface registers first (usually en0/Wi-Fi). When Pioneer hardware is on Ethernet (en16), broadcast packets go out the wrong interface, causing device_found/device_lost cycling. Manual fix: `sudo route delete 169.254.255.255 && sudo route add -host 169.254.255.255 -interface en16`. Needs automation via startup script.

### rekordbox_id instability on XDJ-AZ
`CdjStatus.getRekordboxId()` returns different values for the same track when toggling between paused and playing states. The Python adapter handles this by only firing `on_track_loaded` on nonzero ID changes.

## Network Interface Discovery and Selection

beat-link auto-discovers the network interface to bind to, but frequently picks the wrong one — Wi-Fi instead of Ethernet, a VPN adapter, Docker's virtual bridge, or a Thunderbolt bridge. On macOS there are often 8+ interfaces. Picking the wrong one means the bridge silently connects to nothing.

The bridge implements a three-layer interface selection strategy:

### Layer 1 — Smart Auto-Detection (default)

When no `--interface` argument is provided:

1. Enumerate all network interfaces via `NetworkInterface.getNetworkInterfaces()`
2. Filter out: loopback, down/inactive interfaces, virtual interfaces (names starting with `veth`, `docker`, `br-`, `vmnet`, `utun`, `awdl`, `llw`, `bridge`)
3. Score remaining interfaces:
   - +10 if the interface has a link-local address (169.254.x.x) — this is the Pro DJ Link auto-config range
   - +5 if the interface name suggests wired Ethernet (`en0`–`en9` on macOS, `eth*` on Linux, `Ethernet*` on Windows)
   - +3 if the interface has a 10.x.x.x or 192.168.x.x address (common manual DJ network configs)
   - -5 if the interface name suggests Wi-Fi (`en0` with Wi-Fi type on macOS, `wlan*`, `Wi-Fi`)
   - -10 if the interface name suggests VPN or virtual (`utun*`, `tun*`, `tap*`)
4. Select the highest-scoring interface
5. Log the decision at INFO level: `"Auto-selected interface en5 (169.254.20.1, score=15). Other candidates: en0 (192.168.1.100, score=3, Wi-Fi), en7 (10.0.0.5, score=8)"`
6. Include the full candidate list and scores in the `bridge_status` message payload so the Python side can surface it in the UI

### Layer 2 — User Selection (via CLI argument)

When `--interface <name>` is provided:

1. Look up the named interface via `NetworkInterface.getByName(name)`
2. If found and up: use it. Log at INFO: `"Using configured interface en5 (169.254.20.1)"`
3. If found but down: log at WARN: `"Configured interface en5 exists but is down. Falling back to auto-detection."` → run Layer 1.
4. If not found: log at WARN: `"Configured interface en5 not found. Available interfaces: [en0, en7, lo0]. Falling back to auto-detection."` → run Layer 1.
5. In both fallback cases, include a `"warning"` field in the `bridge_status` payload so the UI can alert the user.

### Layer 3 — Startup Validation

After interface selection (whether auto or manual), before calling `VirtualCdj.getInstance().start()`:

1. Call `VirtualCdj.getInstance().setUseInterface(selectedInterface)` (if beat-link's API supports specifying the interface; otherwise, set the system property or use the approach documented in beat-link's README for interface selection)
2. Verify the interface is active: `selectedInterface.isUp()` and `selectedInterface.getInetAddresses()` returns at least one non-loopback address
3. After `VirtualCdj.start()`, verify that devices are discoverable within 10 seconds. If no devices appear but the interface is up, log at WARN: `"No Pioneer devices found on en5 (169.254.20.1). Check physical connection and that hardware is powered on."`

### Implementation in Java

```java
// Pseudocode for interface selection
NetworkInterface selectedInterface = null;

if (cliInterfaceName != null) {
    // Layer 2: User-specified
    selectedInterface = NetworkInterface.getByName(cliInterfaceName);
    if (selectedInterface == null || !selectedInterface.isUp()) {
        log.warn("Configured interface {} not available, falling back to auto-detection", cliInterfaceName);
        selectedInterface = null; // triggers Layer 1
    }
}

if (selectedInterface == null) {
    // Layer 1: Auto-detection with scoring
    selectedInterface = autoDetectInterface();
}

log.info("Using interface {} ({})", selectedInterface.getName(), getAddress(selectedInterface));
VirtualCdj.getInstance().setUseInterface(selectedInterface);
```