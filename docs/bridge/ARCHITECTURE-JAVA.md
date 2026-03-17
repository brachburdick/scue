# Java Bridge Architecture

The beat-link bridge is a Java 11+ subprocess that connects to Pioneer DJ
hardware via the Pro DJ Link protocol and streams typed JSON messages over a
local WebSocket. It is the only Java component in SCUE.

## Why Java

The Pro DJ Link protocol is complex (~30K lines in beat-link). Three approaches
were evaluated (ADR-005):

| Approach | Verdict |
|----------|---------|
| JPype (embed JVM in Python) | Fragile. JVM crash takes down Python. No process isolation. |
| Port beat-link to Python | Years of work. Permanent maintenance fork. |
| **Managed subprocess + WebSocket** | Clean process boundary. Bridge crash doesn't kill SCUE. |

The subprocess approach was chosen. The bridge is a pre-built fat JAR deployed at
`lib/beat-link-bridge.jar`. It is **not** compiled during SCUE's build.

## Source Layout

```
bridge-java/
  build.gradle                  # Gradle + Shadow plugin for fat JAR
  src/main/java/com/scue/bridge/
    BeatLinkBridge.java         # Entry point, lifecycle, network interface selection
    BridgeWebSocketServer.java  # WebSocket server (broadcasts to all clients)
    MessageEmitter.java         # Constructs typed JSON message envelopes
```

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| `org.deepsymmetry:beat-link` | 8.0.0 | Pro DJ Link protocol implementation |
| `org.java-websocket:Java-WebSocket` | 1.5.7 | WebSocket server |
| `com.google.code.gson:gson` | 2.11.0 | JSON serialization |
| `org.slf4j:slf4j-simple` | 2.0.16 | Logging (to stderr) |

Output: single fat JAR (~21 MB) via Gradle Shadow plugin.

## beat-link Classes Used

Per ADR-012, the bridge uses only 6 beat-link classes:

| Class | Purpose |
|-------|---------|
| `DeviceFinder` | Device discovery (CDJs, DJMs appearing/disappearing) |
| `DeviceAnnouncementListener` | Callbacks for device found/lost |
| `VirtualCdj` | Core network connection + CdjStatus updates (~5Hz/player) |
| `CdjStatus` | Per-player playback state (BPM, pitch, beat, play state, on-air) |
| `BeatFinder` | Real-time beat events |
| `Beat` | Beat event data |

**Deliberately NOT used:** `MetadataFinder`, `BeatGridFinder`, `WaveformFinder`,
`CrateDigger`, `AnalysisTagFinder`. These are incompatible with Device Library
Plus hardware (see PITFALLS.md).

## Startup Sequence

```
1. Parse CLI args (--port, --player-number, --interface, --log-level, --retry-interval)
2. Start WebSocket server on configured port
3. Emit bridge_status { connected: false, devices_online: 0 }
4. Select network interface (three-layer strategy, see below)
5. Register JVM shutdown hook
6. Enter main loop:
   a. DeviceFinder.start()
   b. VirtualCdj.setDeviceNumber(playerNumber)
   c. VirtualCdj.start() -- BLOCKS up to ~10s
   d. BeatFinder.start()
   e. Register listeners (device, status, beat)
   f. Emit bridge_status { connected: true, network_interface: ..., interface_candidates: [...] }
   g. Emit device_found for any devices already present
   h. Monitor loop: sleep 1s, check VirtualCdj.isRunning()
      If VirtualCdj dropped: cleanup, retry after retryInterval
```

**Critical ordering:** WebSocket starts BEFORE beat-link (step 2 before step 6).
The Python manager uses WebSocket connectivity as a health check. If it can
connect but receives `connected: false`, the bridge is alive but no hardware is
present.

**Retry behavior:** If `VirtualCdj.start()` fails, the bridge retries every
`retryInterval` seconds (default 10). It does not exit. Hardware may be powered
on after the bridge starts.

## Network Interface Selection (Three-Layer Strategy)

### Layer 1 -- Smart Auto-Detection (default)

1. Enumerate all network interfaces via `NetworkInterface.getNetworkInterfaces()`
2. Filter out: loopback, down, virtual (`veth`, `docker`, `br-`, `vmnet`, `utun`, `awdl`, `llw`, `bridge`)
3. Score remaining interfaces:

| Condition | Score |
|-----------|-------|
| Has link-local address (169.254.x.x) | +10 |
| Name suggests wired Ethernet | +5 |
| Has private IP (10.x or 192.168.x) | +3 |
| Name suggests Wi-Fi | -5 |
| Name suggests VPN/virtual | -10 |

4. Select highest-scoring interface
5. Log decision with all candidates and scores

### Layer 2 -- User Selection (--interface CLI arg)

If the named interface exists and is up, use it directly. If not found or down,
log a warning and fall back to Layer 1 auto-detection.

### Layer 3 -- Startup Validation

After `VirtualCdj.start()`, verify that beat-link bound to the expected
interface by checking `VirtualCdj.getInstance().getMatchingInterfaces()`. If it
chose a different interface, emit a warning in `bridge_status`.

On macOS, also check the `169.254.255.255` broadcast route via
`route get 169.254.255.255`. If it points to the wrong interface, emit a warning
with the `sudo route` fix command (see PITFALLS.md).

## Message Protocol

All messages use this envelope:
```json
{
  "type": "<message_type>",
  "timestamp": 1710600001.5,
  "player_number": 1,
  "payload": { ... }
}
```

- `timestamp`: Unix epoch seconds (float, ms precision) via `System.currentTimeMillis() / 1000.0`
- `player_number`: 1-4 for CDJ messages, `null` for bridge/device messages
- JSON serialized with Gson (`serializeNulls()` enabled)

### Message Types Emitted

| Type | Frequency | Trigger |
|------|-----------|---------|
| `bridge_status` | On state change | Startup, device discovery, error |
| `device_found` | On discovery | New Pioneer device appears on network |
| `device_lost` | On departure | Pioneer device disappears |
| `player_status` | ~5Hz per player | Every `CdjStatus` update from VirtualCdj |
| `beat` | ~2Hz at 128 BPM | Every beat event from BeatFinder |

### Message Types NOT Emitted (per ADR-012)

`track_metadata`, `beat_grid`, `waveform_detail`, `phrase_analysis`, `cue_points`
-- all resolved by the Python side via rbox/pyrekordbox reading USB data directly.

### DLP Detection in device_found

```json
{
  "type": "device_found",
  "payload": {
    "device_name": "XDJ-AZ",
    "uses_dlp": true
  }
}
```

Detection: `deviceName.toLowerCase().replaceAll("[\\s_]", "-")` matched against
`xdj-az`, `opus-quad`, `omnis-duo`, `cdj-3000x`. The Python adapter uses this
flag to choose the metadata resolution path.

## CdjStatus Field Extraction

```java
boolean noTrack = status.getTrackType() == CdjStatus.TrackType.NO_TRACK;
double bpm       = noTrack ? 0.0 : status.getEffectiveTempo();
double pitchPct  = noTrack ? 0.0 : ((status.getPitch() / 1048576.0) - 1.0) * 100.0;
int beatInBar    = status.getBeatWithinBar();       // 1-4
int beatNum      = status.getBeatNumber();           // absolute from track start
String playState = getPlaybackState(status);         // playing|paused|cued|searching
boolean onAir    = status.isOnAir();                 // fader up AND master not off
int rekordboxId  = status.getRekordboxId();          // DLP track ID
```

**Guard all derived values with noTrack check.** `getPitch()` and
`getEffectiveTempo()` return garbage when no track is loaded.

## Shutdown Sequence

Registered as a JVM shutdown hook (fires on SIGTERM, SIGINT, or normal exit):

```
1. BeatFinder.stop()
2. VirtualCdj.stop()     -- announces departure from Pro DJ Link network
3. DeviceFinder.stop()
4. Close all WebSocket connections
5. Stop WebSocket server
```

Step 2 is critical: without it, Pioneer hardware displays a phantom device for
up to 30 seconds.

## CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--port` | 17400 | WebSocket server port |
| `--player-number` | 5 | Player number on DJ Link (5-6 = software players, avoid 1-4) |
| `--interface` | (auto) | Network interface name (e.g., `en16`) |
| `--retry-interval` | 10 | Seconds between network join retries |
| `--log-level` | INFO | DEBUG, INFO, WARN, ERROR |

## Building

```bash
cd bridge-java
./gradlew shadowJar
cp build/libs/beat-link-bridge.jar ../lib/
```

The fat JAR includes all dependencies. Requires Java 11+ to run.

## Logging

All output to stderr (not stdout). Format:
```
[2026-03-17T14:30:00.123Z] [INFO] Bridge started on port 17400
[2026-03-17T14:30:00.456Z] [INFO] Auto-selected interface en16 (169.254.20.47, score=15)
```

Key events to watch for:
- `"VirtualCdj failed to join"` -- hardware not found, will retry
- `"macOS routes 169.254.255.255 via"` -- broadcast route wrong, needs fix
- `"Requested interface X but beat-link bound to Y"` -- interface mismatch
- `"Track change on player"` -- rekordbox ID changed (track loaded)
