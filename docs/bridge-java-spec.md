# Beat-Link Bridge JAR — Specification

## Overview

SCUE needs full access to the Pro DJ Link protocol to receive track metadata, beatgrids, waveforms, phrase analysis, cue points, and real-time beat/status events from Pioneer DJ hardware. The open-source [beat-link](https://github.com/Deep-Symmetry/beat-link) Java library (~30K lines) implements this protocol. Rather than porting it to Python, SCUE runs beat-link as a managed subprocess that streams typed JSON messages over a local WebSocket.

This document specifies the Java bridge application. The Python consumer side is already built and tested (`scue/bridge/`).

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
3. Start a `MetadataFinder` to request track metadata from players
4. Subscribe to all available data streams
5. Start a WebSocket server on a configurable port (default: 17400)
6. Translate each beat-link event into a typed JSON message (schemas below)
7. Stream messages to all connected WebSocket clients
8. Accept a `--port <N>` CLI argument for the WebSocket port

## beat-link API Entry Points

The bridge should use these beat-link classes:

| Class | Purpose |
|-------|---------|
| `org.deepsymmetry.beatlink.DeviceAnnouncementListener` | Device discovery (CDJs, DJMs appearing/disappearing) |
| `org.deepsymmetry.beatlink.VirtualCdj` | Core connection to the Pro DJ Link network |
| `org.deepsymmetry.beatlink.CdjStatus` | Per-player playback state (BPM, pitch, beat, play/pause, on-air) |
| `org.deepsymmetry.beatlink.Beat` | Real-time beat events |
| `org.deepsymmetry.beatlink.data.MetadataFinder` | Track metadata requests (title, artist, key, etc.) |
| `org.deepsymmetry.beatlink.data.BeatGridFinder` | Beat grid data |
| `org.deepsymmetry.beatlink.data.WaveformFinder` | Waveform detail data |
| `org.deepsymmetry.beatlink.data.CrateDigger` | Cue points, memory points, hot cues |
| `org.deepsymmetry.beatlink.data.AnalysisTagFinder` | Phrase analysis (rekordbox 6+ KUVO data) |

## Message Types and JSON Schemas

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
    "version": "1.0.0"
  }
}
```

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
    "ip_address": "169.254.20.101"
  }
}
```

- `device_type`: `"cdj"` | `"djm"` | `"rekordbox"`
- `player_number`: set for CDJs (1-4), null for DJMs

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
    "track_type": "rekordbox"
  }
}
```

- `bpm`: Effective BPM (after pitch adjustment)
- `pitch`: Pitch adjustment as percentage (e.g., 2.5 means +2.5%)
- `beat_within_bar`: 1-4
- `playback_state`: `"playing"` | `"paused"` | `"cued"` | `"searching"`
- `track_source_slot`: `"sd"` | `"usb"` | `"cd"` | `"collection"`

### track_metadata
Sent when a new track is loaded on a player (via `MetadataFinder`).

```json
{
  "type": "track_metadata",
  "timestamp": 1710600010.0,
  "player_number": 1,
  "payload": {
    "title": "Strobe",
    "artist": "deadmau5",
    "album": "For Lack of a Better Name",
    "genre": "Progressive House",
    "key": "Fm",
    "bpm": 128.0,
    "duration": 637.0,
    "color": null,
    "rating": 5,
    "comment": "",
    "rekordbox_id": 42001
  }
}
```

- `bpm`: rekordbox-analyzed BPM (original, not pitch-adjusted)
- `duration`: seconds
- `color`: rekordbox track color hex string or null
- `key`: musical key as detected by rekordbox (e.g., "Fm", "Ab", "G#m")

### beat_grid
Sent after track_metadata, contains the full rekordbox beat grid.

```json
{
  "type": "beat_grid",
  "timestamp": 1710600010.1,
  "player_number": 1,
  "payload": {
    "beats": [
      { "beat_number": 1, "time_ms": 250.0, "bpm": 128.0 },
      { "beat_number": 2, "time_ms": 718.75, "bpm": 128.0 }
    ]
  }
}
```

### waveform_detail
Sent after track_metadata. Base64-encoded waveform data.

```json
{
  "type": "waveform_detail",
  "timestamp": 1710600010.2,
  "player_number": 1,
  "payload": {
    "data": "<base64-encoded>",
    "total_beats": 1358
  }
}
```

### phrase_analysis
Sent if the track has rekordbox 6+ phrase analysis (KUVO data).

```json
{
  "type": "phrase_analysis",
  "timestamp": 1710600010.3,
  "player_number": 1,
  "payload": {
    "phrases": [
      { "start_beat": 1, "end_beat": 128, "kind": "intro", "mood": 1 },
      { "start_beat": 129, "end_beat": 384, "kind": "verse", "mood": 1 }
    ]
  }
}
```

- `kind`: rekordbox phrase type string
- `mood`: rekordbox mood integer

### cue_points
Sent after track_metadata.

```json
{
  "type": "cue_points",
  "timestamp": 1710600010.4,
  "player_number": 1,
  "payload": {
    "cue_points": [
      { "time_ms": 250.0, "name": "", "color": "" }
    ],
    "memory_points": [
      { "time_ms": 250.0, "name": "Start", "color": "#00FF00" }
    ],
    "hot_cues": [
      { "slot": 1, "time_ms": 250.0, "name": "Start", "color": "#00FF00" }
    ]
  }
}
```

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

## Message Ordering

When a track loads on a player, send messages in this order:
1. `track_metadata`
2. `beat_grid`
3. `waveform_detail`
4. `phrase_analysis` (if available)
5. `cue_points`

Then continuously:
- `player_status` (~5Hz)
- `beat` (on each beat)

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
1. Parse CLI arguments (--port, --player-number)
2. Start WebSocket server on configured port
3. Emit bridge_status { connected: false, devices_online: 0 }
4. DeviceFinder.getInstance().start()
5. VirtualCdj.getInstance().setDeviceNumber(playerNumber)
6. VirtualCdj.getInstance().start()
   └─ This BLOCKS until it joins the network or times out (~10s)
   └─ If timeout: log warning, emit bridge_status { connected: false }
      The WebSocket server stays running. Retry on a configurable interval (default 10s).
7. MetadataFinder.getInstance().start()
8. BeatGridFinder.getInstance().start()
9. WaveformFinder.getInstance().start()
10. CrateDigger.getInstance().start()
11. AnalysisTagFinder.getInstance().start()  (if available in the beat-link version)
12. Register listeners for DeviceAnnouncement, CdjStatus, Beat, etc.
13. Emit bridge_status { connected: true, devices_online: N }
```

**Critical:** The WebSocket server must start BEFORE beat-link initialization (step 2 before step 4). This ensures the Python manager can connect and receive status messages even if beat-link fails to find hardware. The Python side uses the WebSocket connection itself as a health check — if it can't connect, the bridge process is dead. If it connects but receives `connected: false`, the bridge is alive but no hardware is present.

**Retry behavior:** If VirtualCdj fails to join the network at step 6, the bridge should retry periodically (every 10 seconds) rather than exiting. Hardware may be powered on after the bridge starts. On successful join, proceed to steps 7–13 and emit an updated `bridge_status`.

## CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--port <N>` | `17400` | WebSocket server port |
| `--player-number <N>` | `5` | Player number to claim on the Pro DJ Link network. Must not conflict with connected CDJs (typically 1–4). Values 5–6 are conventional for software players. If the number is taken, startup will fail — log the error clearly. |
| `--log-level <LEVEL>` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `--retry-interval <S>` | `10` | Seconds between network join retries when no hardware is found |

## Graceful Shutdown

When the process receives SIGTERM (or SIGINT):

1. Log "Shutting down beat-link bridge..."
2. Stop all finders in reverse order: AnalysisTagFinder → CrateDigger → WaveformFinder → BeatGridFinder → MetadataFinder
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

**MetadataFinder failures:** Some tracks (from older CDJs, CDs, or non-rekordbox USBs) may not have metadata available. If MetadataFinder can't retrieve metadata for a loaded track, send a `track_metadata` message with null/empty fields and log a WARN. Do not skip the message — the Python side needs to know a track loaded even without metadata.

**WebSocket client disconnect:** If the Python client disconnects, keep the bridge running. It will reconnect. Log the disconnect at WARN level and the reconnect at INFO.

**Uncaught exceptions in listeners:** Wrap all beat-link listener callbacks in try-catch. An exception in one listener (e.g., WaveformFinder can't decode waveform data) must not crash the bridge or prevent other listeners from firing. Log the exception at ERROR and continue.