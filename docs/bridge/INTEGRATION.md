# Bridge Integration -- Combined System Behavior

How the Java bridge, Python adapter, USB scanner, and ANLZ parsers work together
as a complete system. Read this document to understand the end-to-end data flow
from Pioneer hardware to SCUE's cue engine.

## The Two Data Paths

SCUE receives Pioneer data through two independent paths that serve different
purposes:

```
                    ┌─────────────────────────────────────┐
                    │         PIONEER HARDWARE             │
                    │  (XDJ-AZ / CDJ / DJM on DJ Link)    │
                    └──────┬──────────────────┬────────────┘
                           │                  │
              UDP broadcasts            USB drive
              (real-time, live)         (pre-set, offline)
                           │                  │
                           ▼                  ▼
                  ┌────────────────┐  ┌───────────────────┐
        PATH A:   │  Java bridge   │  │  USB scanner      │  :PATH B
        Real-time │  (beat-link)   │  │  (rbox + pyrkb)   │  Metadata
                  └───────┬────────┘  └──────┬────────────┘
                          │                  │
                   WebSocket JSON     Python direct read
                          │                  │
                          ▼                  ▼
                  ┌────────────────┐  ┌───────────────────┐
                  │  BridgeAdapter │  │  TrackCache        │
                  │  (live state)  │  │  (Pioneer metadata)│
                  └───────┬────────┘  └──────┬────────────┘
                          │                  │
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌────────────────┐
                          │  Enrichment    │
                          │  (Layer 1)     │
                          └────────────────┘
```

### Path A: Real-Time Playback Data (Bridge)

**When:** During the live DJ set, continuously.

**What flows:** BPM, pitch, beat position (1-4), beat number, play/pause state,
on-air status, rekordbox_id. Updated at ~5Hz per player.

**How:** Java bridge subprocess reads Pro DJ Link UDP broadcasts via beat-link,
emits typed JSON over WebSocket. Python adapter normalizes into `PlayerState`.

**Does NOT provide:** Track titles, artist names, beatgrids, cue points, phrase
analysis, waveforms. (ADR-012: beat-link's metadata system is incompatible with
DLP hardware.)

### Path B: Track Metadata & Analysis (USB Scanner)

**When:** Before the set, while the USB is plugged into the SCUE computer.

**What flows:** Track title, artist, BPM, key (from `exportLibrary.db`).
Beatgrid, hot cues, memory cues (from ANLZ files).

**How:** rbox reads the DLP database. pyrekordbox + custom parser read ANLZ
binary files. Results cached in SQLite keyed by rekordbox_id.

**Does NOT provide:** Real-time playback state, which track is currently playing,
beat sync timing.

## How the Paths Connect

The `rekordbox_id` field is the link between the two paths.

1. **Pre-set:** USB scanner reads `exportLibrary.db`, extracts rekordbox IDs for
   all 2,022 tracks. Reads ANLZ data. Caches `rekordbox_id → metadata` mapping.

2. **Live set:** Bridge reports `player_status` with `rekordbox_id: 42001`.
   Python adapter fires `on_track_loaded(player_number=1, ...)`.

3. **Enrichment:** Layer 1 looks up `rekordbox_id=42001` in the Pioneer metadata
   cache. Finds the Pioneer-verified beatgrid, hot cues, key. Runs the
   enrichment pass to replace librosa's estimated data with Pioneer's verified data.

```
Bridge says: "Player 1 is playing rekordbox_id 42001 at 128.0 BPM, beat 3 of 4"
Cache says:  "rekordbox_id 42001 = 'Strobe' by deadmau5, 762 beats, 3 hot cues"
Enrichment:  Replaces librosa beatgrid with Pioneer's 762-beat grid
```

## Startup Sequence (Full System)

### Phase 1: Pre-Set Preparation

```
1. User plugs USB into SCUE computer
2. User triggers USB scan (via UI or API: POST /api/usb/scan)
3. usb_scanner reads exportLibrary.db via rbox OneLibrary
   → 2,022 UsbTrack objects with title, artist, BPM, key, anlz_path
4. For each track, _read_anlz_data() runs the two-tier ANLZ strategy:
   a. Tier 1: pyrekordbox.anlz.AnlzFile.parse_file(dat_path)
      → Success: beatgrid, hot cues, memory cues extracted
      → Failure (~0.2% of files): fall through to Tier 2
   b. Tier 2: anlz_parser.parse_anlz_beatgrid(dat_path)
      → Success: beatgrid + cues from custom parser
      → Failure: track has no Pioneer analysis data (use librosa)
5. match_usb_tracks() links rekordbox_id → SCUE fingerprint
6. apply_scan_results() caches Pioneer metadata in SQLite
7. USB can be unplugged from SCUE computer, moved to DJ hardware
```

### Phase 2: Live Set

```
1. BridgeManager.start()
   a. Checks for Java, JAR
   b. Launches: java -jar lib/beat-link-bridge.jar --port 17400 --interface en16
   c. Connects WebSocket to ws://localhost:17400
   d. Starts listen loop + health check loop
2. Bridge discovers Pioneer hardware on the network
   → device_found messages flow to adapter
3. DJ loads a track on Player 1
   → player_status messages start flowing (~5Hz)
   → adapter detects rekordbox_id change, fires on_track_loaded
4. Layer 1 receives on_track_loaded:
   a. Looks up rekordbox_id in Pioneer metadata cache
   b. If found: runs enrichment pass (Pioneer beatgrid replaces librosa)
   c. If not found: continues with librosa-only analysis
5. Beat events flow continuously during playback
   → adapter fires on_beat for each beat
   → Layer 2 cue engine uses beats for effect sync
```

## Failure Modes & Graceful Degradation

| Failure | Consequence | Recovery |
|---------|-------------|----------|
| No Java installed | Manager state: `no_jre`. No bridge. | Fallback UDP parser (BPM/beat only) |
| JAR missing | Manager state: `no_jar`. No bridge. | Fallback UDP parser |
| Bridge crashes | Manager state: `crashed`. | Auto-restart with exponential backoff |
| Wrong network interface | Devices cycle on/off. | Warning in bridge_status with fix command |
| USB not scanned | No Pioneer metadata cached. | Enrichment uses librosa data (degraded accuracy) |
| rbox not installed | USB scan fails with ImportError. | Cannot scan USB |
| pyrekordbox parse error | Tier 1 fails on ~4/2022 files. | Tier 2 custom parser catches them |
| Both ANLZ tiers fail | Track has no Pioneer beatgrid. | Enrichment uses librosa beatgrid |
| Bridge + fallback both down | No real-time data at all. | SCUE operates on offline analysis only |

## Concurrency Model

- **Bridge subprocess:** Independent Java process. Communicates only via WebSocket.
  Crash does not affect Python process.
- **Manager listen loop:** `asyncio` task reading WebSocket messages. Runs on
  SCUE's main event loop.
- **Health check:** Separate `asyncio` task polling subprocess status every 10s.
- **USB scan:** Synchronous (runs via `asyncio.to_thread` to avoid blocking the
  event loop). Not concurrent with the bridge -- it's a pre-set preparation step.
- **ANLZ parsing:** Per-track, sequential. pyrekordbox and custom parser are both
  pure Python with no threading concerns.

## Message Frequency & Performance

| Message | Frequency | Payload Size |
|---------|-----------|-------------|
| `player_status` | ~5Hz per active player | ~200 bytes |
| `beat` | ~2Hz at 128 BPM per player | ~80 bytes |
| `device_found/lost` | Rare (hardware events) | ~150 bytes |
| `bridge_status` | On state change only | ~500 bytes |

With 2 active players: ~14 messages/second, ~4 KB/second. WebSocket overhead is
negligible for local communication.

## Testing the Full System

### Unit Tests (no hardware needed)

```bash
python -m pytest tests/test_bridge/ -v     # Bridge adapter, manager, messages
python -m pytest tests/test_layer1/ -v     # USB scanner, ANLZ parser, enrichment
```

### Integration Test with Mock Bridge

```bash
python tools/mock_bridge.py                 # Replays fixture data over WebSocket
uvicorn scue.main:app --reload              # Start SCUE backend
# Open browser: http://localhost:8000 → Bridge status should show mock data
```

### Integration Test with Real Hardware

```bash
# 1. Fix macOS route (if needed)
sudo ./tools/fix-djlink-route.sh en16

# 2. Scan USB (while plugged in)
curl -X POST http://localhost:8000/api/usb/scan \
  -H 'Content-Type: application/json' \
  -d '{"usb_path": "/Volumes/PIONEER"}'

# 3. Start SCUE with bridge
uvicorn scue.main:app --reload
# Bridge will auto-connect to Pioneer hardware

# 4. Load a track on the CDJ → check enrichment fires
```

### Verifying ANLZ Data Against Real USB

```python
from scue.layer1.usb_scanner import read_usb_library
from pathlib import Path

usb = Path.home() / "Documents/skald usb backup 3.16.26"
db = usb / "PIONEER/rekordbox/exportLibrary.db"
anlz = usb / "PIONEER/USBANLZ"

tracks = read_usb_library(db, anlz)
with_bg = sum(1 for t in tracks if t.beatgrid)
with_hot = sum(1 for t in tracks if t.hot_cues)
print(f"{len(tracks)} tracks, {with_bg} with beatgrid, {with_hot} with hot cues")
# Expected: ~2017/2022 with beatgrid, ~658 with hot cues
```

## Key Design Principles

1. **Bridge is replaceable.** Layer 1 talks to the adapter, not the bridge
   directly. If beat-link is replaced, only the bridge JAR and adapter change.

2. **Crash isolation.** The Java bridge runs in a separate process. A JVM crash
   (or beat-link bug) cannot kill the Python process. The manager detects crashes
   and auto-restarts.

3. **Pure Python for untrusted data.** ANLZ parsing uses pure Python exclusively
   (no Rust, no C). A parsing failure raises a Python exception, never a process
   abort. (Learned the hard way with rbox -- see PITFALLS.md.)

4. **Two independent data paths.** Real-time data (bridge) and metadata (USB scan)
   are completely independent. Either can fail without affecting the other. The
   rekordbox_id links them at enrichment time.

5. **Graceful degradation everywhere.** No single failure stops the system.
   Bridge down → fallback UDP. pyrekordbox fails → custom parser. Custom parser
   fails → librosa. USB not scanned → no enrichment, but live data still works.

## Related Documents

- [ARCHITECTURE-JAVA.md](ARCHITECTURE-JAVA.md) -- Java bridge internals
- [ARCHITECTURE-PYTHON.md](ARCHITECTURE-PYTHON.md) -- Python bridge internals
- [PITFALLS.md](PITFALLS.md) -- Library-specific gotchas
- [../bridge-java-spec.md](../bridge-java-spec.md) -- Bridge JAR specification
- [../CONTRACTS.md](../CONTRACTS.md) -- Layer 0 → Layer 1 interface contract
- [../DECISIONS.md](../DECISIONS.md) -- ADR-005 (subprocess), ADR-012 (DLP), ADR-013 (ANLZ)
- [../bugs/layer0-bridge.md](../bugs/layer0-bridge.md) -- Bug log
- [../../LEARNINGS.md](../../LEARNINGS.md) -- Append-only discovery log
