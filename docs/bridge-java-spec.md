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
