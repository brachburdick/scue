# SCUE Bridge Contract v1.0

> **Single source of truth** for all message shapes, API response shapes, state machines,
> and lifecycle contracts across the bridge stack (Java → Python → REST/WS → Frontend).
>
> Last updated: 2026-03-25

---

## 1. Bridge State Machine

### States

| State | Description | FE `dotStatus` | FE `isStartingUp` |
|-------|-------------|----------------|-------------------|
| `stopped` | Not running, no subprocess | `"disconnected"` | depends on WS |
| `starting` | Subprocess launching / WS connecting | `"disconnected"` | `true` |
| `running` | Subprocess + WS connected, receiving messages | `"connected"` | `false` |
| `crashed` | Subprocess died, will restart with backoff | `"disconnected"` | `false` |
| `no_jre` | Java not found on system | `"disconnected"` | `false` |
| `no_jar` | Bridge JAR not found | `"disconnected"` | `false` |
| `fallback` | Running UDP fallback parser (degraded) | `"degraded"` | `false` |
| `waiting_for_hardware` | Crash threshold reached, polling for hardware | `"degraded"` | `false` |

### Transitions

```
stopped ──start()──→ starting ──success──→ running
                         │                     │
                         │ fail             crash/disconnect
                         ▼                     ▼
                      crashed ◄─────────── crashed
                         │                     │
                         │ backoff timer       │ 3 consecutive
                         ▼                     ▼
                      starting         waiting_for_hardware
                                               │
                                               │ 30s poll
                                               ▼
                                            starting

stopped ──no JRE──→ no_jre ──→ fallback
stopped ──no JAR──→ no_jar ──→ fallback
```

### Key Lifecycle Invariants

- `_last_message_time` is reset to `0.0` in `start()` before subprocess launch
- `adapter.clear()` is called in `start()` to reset device/player state
- Consecutive failures only reset after `_MIN_STABLE_UPTIME_S` (30s) of stable running
- After `max_crash_before_fallback` (3) crashes → `waiting_for_hardware` (not fallback)
- Fallback is reserved for JRE/JAR absent only

---

## 2. Java Bridge → Python (WS port 17400)

### Message Envelope

Every message from the Java bridge follows this envelope:

```json
{
  "type": "<message_type>",
  "timestamp": 1711382400.123,
  "player_number": 1,
  "payload": { }
}
```

- `type`: one of the constants below
- `timestamp`: Unix epoch seconds (float)
- `player_number`: integer (1-4) or `null` for bridge-level messages
- `payload`: type-specific data

### Message Types

#### `device_found` / `device_lost`
```json
{
  "device_name": "XDJ-AZ",
  "device_number": 3,
  "device_type": "cdj",
  "ip_address": "169.254.1.3",
  "uses_dlp": true
}
```

#### `bridge_status`
```json
{
  "connected": true,
  "devices_online": 2,
  "version": "1.3.0",
  "network_interface": "en16",
  "network_address": "169.254.1.1",
  "interface_candidates": [
    { "name": "en16", "address": "169.254.1.5", "type": "ethernet", "score": 15, "selected": true }
  ],
  "warning": null,
  "error": null
}
```

#### `player_status`
```json
{
  "bpm": 128.0,
  "pitch": 0.0,
  "beat_within_bar": 3,
  "beat_number": 512,
  "playback_state": "playing",
  "is_on_air": true,
  "track_source_player": 1,
  "track_source_slot": "usb",
  "track_type": "rekordbox",
  "rekordbox_id": 42,
  "playback_position_ms": 64000.0
}
```

#### `beat`
```json
{
  "beat_within_bar": 1,
  "bpm": 128.0
}
```

#### `track_metadata`
```json
{
  "title": "Track Name",
  "artist": "Artist Name",
  "album": "",
  "genre": "House",
  "key": "Am",
  "duration": 300,
  "color": "#FF0000",
  "rating": 0,
  "comment": "",
  "rekordbox_id": 42
}
```

#### `beat_grid`
```json
{
  "beats": [
    { "beat_number": 1, "time_ms": 230.5, "bpm": 128.0 }
  ]
}
```

#### `phrase_analysis`
```json
{
  "phrases": [
    { "start_beat": 1, "end_beat": 64, "kind": "intro", "mood": 1 }
  ]
}
```

#### `cue_points`
```json
{
  "cue_points": [{ "time_ms": 1000.0, "name": "", "color": "#FF0000" }],
  "memory_points": [{ "time_ms": 2000.0, "name": "Drop", "color": "#00FF00" }],
  "hot_cues": [{ "time_ms": 3000.0, "name": "A", "color": "#0000FF" }]
}
```

#### `track_waveform`
Pioneer RGB waveform data.
```json
{
  "data": "<base64-encoded bytes, 3 bytes per sample: low/mid/high, range 0-31>",
  "frame_count": 400,
  "total_time_ms": 300000.0,
  "is_color": true
}
```

#### `command_response`
```json
{
  "request_id": "uuid-string",
  "status": "ok",
  "command": "browse_all_tracks",
  "data": { },
  "error_message": null
}
```

### Command Channel (Python → Java)

```json
{
  "command": "browse_all_tracks",
  "request_id": "uuid-string",
  "params": { "player_number": 1, "slot": "usb" }
}
```

Commands: `browse_root_menu`, `browse_playlist`, `browse_all_tracks`, `load_track`

---

## 3. Python → Frontend: WebSocket Messages (port 8000)

### `bridge_status`

Sent on every bridge state change. Payload is `BridgeManager.to_status_dict()`:

```json
{
  "type": "bridge_status",
  "payload": {
    "status": "running",
    "mode": "bridge",
    "port": 17400,
    "network_interface": "en16",
    "jar_path": "lib/beat-link-bridge.jar",
    "jar_exists": true,
    "jre_available": true,
    "restart_count": 0,
    "restart_attempt": 0,
    "next_retry_in_s": null,
    "route_correct": true,
    "route_warning": null,
    "devices": {
      "169.254.1.3": {
        "device_name": "XDJ-AZ",
        "device_number": 3,
        "device_type": "cdj",
        "uses_dlp": true
      }
    },
    "players": {
      "1": {
        "bpm": 128.0,
        "pitch": 0.0,
        "playback_state": "playing",
        "is_on_air": true,
        "rekordbox_id": 42,
        "beat_within_bar": 3,
        "track_type": "rekordbox",
        "playback_position_ms": 64000.0,
        "track_source_player": 1,
        "track_source_slot": "usb",
        "pioneer_waveform_version": 2
      }
    }
  }
}
```

**FE type:** `BridgeState` (`frontend/src/types/bridge.ts`)

### `pioneer_status`

Sent every 2 seconds as a heartbeat.

```json
{
  "type": "pioneer_status",
  "payload": {
    "is_receiving": true,
    "bridge_connected": true,
    "last_message_age_ms": 1200
  }
}
```

### `strata_live`

Sent on track load when Pioneer phrase analysis is available.

```json
{
  "type": "strata_live",
  "payload": {
    "player_number": 1,
    "formula": { }
  }
}
```

**FE type:** `ArrangementFormula` (`frontend/src/types/strata.ts`)

### `scan_progress` / `scan_complete`

Sent during hardware scanning.

```json
{
  "type": "scan_progress",
  "payload": {
    "status": "scanning",
    "total": 100,
    "scanned": 42,
    "skipped": 3,
    "errors": 0,
    "deck_progress": {
      "1": { "status": "scanning", "current_track": "Track Name", "scanned": 20, "total": 50 },
      "2": { "status": "scanning", "current_track": "Other Track", "scanned": 22, "total": 50 }
    }
  }
}
```

**FE type:** `HardwareScanStatus` (`frontend/src/types/ingestion.ts`)

---

## 4. REST API Response Contracts

### Conventions

1. **List responses** are always wrapped: `{ "tracks": [...] }` or `{ "items": [...] }`. Never bare arrays.
2. **Mutation success** returns `{ "ok": true, ... }` or a status object. Never bare strings.
3. **Async job triggers** return a discriminated union keyed on `status`:
   - `"complete"` — synchronous completion
   - `"started"` — background job created (includes `job_id`)
   - `"not_implemented"` — feature not yet available
4. **Error responses** use HTTP status codes with `{ "detail": "message" }` (FastAPI default).

---

### 4.1 Scanner (`/api/scanner/*`)

#### `GET /api/scanner/browse/{player}/{slot}`

Browse all tracks on a player's USB/SD.

```json
{
  "player": 1,
  "slot": "usb",
  "track_count": 42,
  "tracks": [
    { "rekordbox_id": 1, "title": "Track A", "artist": "Artist A" }
  ]
}
```

**FE type:** `UsbBrowseResponse` — must include `player`, `slot`, `track_count` fields.

#### `GET /api/scanner/browse/{player}/{slot}/menu`

Browse root menu (folders/playlists).

```json
{
  "items": [
    { "id": 1, "name": "My Playlist", "is_folder": true }
  ]
}
```

**FE type:** `UsbMenuResponse`

#### `GET /api/scanner/browse/{player}/{slot}/folder/{folder_id}`

Browse folder contents.

```json
{
  "items": [
    { "id": 2, "name": "Subfolder", "is_folder": true }
  ],
  "tracks": [
    { "rekordbox_id": 5, "title": "Track B", "artist": "Artist B" }
  ]
}
```

**FE type:** `UsbFolderResponse`

#### `POST /api/scanner/start`

Start a scan job.

```json
{
  "status": "started",
  "player": 1,
  "slot": "usb",
  "target_players": [1, 2]
}
```

#### `GET /api/scanner/status`

Current scan progress. Shape matches `HardwareScanStatus` (see §3 `scan_progress`).

#### `POST /api/scanner/stop`

```json
{ "status": "stopping" }
```

#### `GET /api/scanner/history`

```json
{
  "tracks": [
    { "rekordbox_id": 1, "title": "Track A", "artist": "Artist A", "fingerprint": "abc123", "scanned_at": 1711382400.0 }
  ]
}
```

**FE type:** `ScanHistoryResponse`

---

### 4.2 Local Library (`/api/local-library/*`)

#### `GET /api/local-library/detect`

```json
{ "path": "/Users/user/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ", "dat_count": 42 }
```

HTTP 404 if not found.

**FE type:** `LibraryDetectResponse`

#### `POST /api/local-library/scan`

```json
{
  "source": "/path/to/USBANLZ",
  "total_tracks": 100,
  "matched": 42,
  "unmatched": 58,
  "already_linked": 10,
  "scan_timestamp": 1711382400.0,
  "matched_tracks": [
    { "title": "Track A", "file_path": "/path/to/file.dat", "fingerprint": "abc123def456", "match_method": "fingerprint" }
  ],
  "unmatched_tracks": [
    { "title": "Track B", "file_path": "/path/to/file2.dat" }
  ]
}
```

**FE type:** `LibraryScanResult` — must use field names `source`, `total_tracks`, `matched_tracks`, `unmatched_tracks`.

#### `GET /api/local-library/status`

**Discriminated union** on presence of `status` field:

Before first scan:
```json
{ "status": "no_scan", "message": "No local library scan has been performed yet." }
```

After scan: same shape as `POST /scan` response above.

**FE type:** `LibraryScanResult | { status: "no_scan"; message: string }`

---

### 4.3 Strata (`/api/strata/*`, `/api/tracks/{fp}/strata/*`)

#### `POST /api/tracks/{fp}/strata/analyze`

**Discriminated union** on `status` field:

Quick/live_offline (synchronous):
```json
{
  "fingerprint": "abc123",
  "completed_tiers": ["quick"],
  "requested_tiers": ["quick"],
  "analysis_source": "latest",
  "status": "complete"
}
```

Standard (background job):
```json
{
  "fingerprint": "abc123",
  "requested_tiers": ["standard"],
  "analysis_source": "latest",
  "status": "started",
  "job_id": "uuid-string",
  "message": "Analysis started. Poll GET /api/strata/jobs/{job_id} for progress."
}
```

Deep (not implemented):
```json
{
  "fingerprint": "abc123",
  "requested_tiers": ["deep"],
  "status": "not_implemented",
  "message": "Deep tier analysis is not yet available (Phase 6)."
}
```

#### `GET /api/strata/jobs/{job_id}`

```json
{
  "job_id": "uuid",
  "fingerprint": "abc123",
  "tier": "standard",
  "status": "running",
  "progress": 0.5,
  "error": null,
  "created_at": 1711382400.0,
  "completed_at": null
}
```

#### Other strata endpoints

See `scue/api/strata.py` for full list. All follow the conventions in §4.

---

### 4.4 Tracks (`/api/tracks/*`)

#### `GET /api/tracks`

```json
{
  "tracks": [ ],
  "total": 42
}
```

#### `GET /api/tracks/{fp}`

Full TrackAnalysis JSON (see `frontend/src/types/track.ts`).

#### `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}`

```json
{
  "fingerprint": "abc123def456...",
  "title": "Track Name",
  "artist": "Artist Name"
}
```

HTTP 404 if not resolved.

#### `GET /api/tracks/{fp}/events`

```json
{
  "fingerprint": "abc123",
  "events": [ ],
  "drum_patterns": [ ],
  "total_events": 100,
  "total_patterns": 10,
  "event_types": ["kick", "snare"]
}
```

---

## 5. FE Type Mapping Table

| Endpoint | BE Return | FE Type | File |
|----------|-----------|---------|------|
| WS `bridge_status` | `to_status_dict()` | `BridgeState` | `types/bridge.ts` |
| WS `pioneer_status` | 3-field dict | inline in `WSPioneerStatus` | `types/ws.ts` |
| WS `scan_progress/complete` | `ScanProgress.to_dict()` | `HardwareScanStatus` | `types/ingestion.ts` |
| `GET /scanner/browse/{p}/{s}` | `{player,slot,track_count,tracks}` | `UsbBrowseResponse` | `types/ingestion.ts` |
| `GET /scanner/browse/.../menu` | `{items}` | `UsbMenuResponse` | `types/ingestion.ts` |
| `GET /scanner/browse/.../folder/{id}` | `{items,tracks}` | `UsbFolderResponse` | `types/ingestion.ts` |
| `GET /scanner/history` | `{tracks}` | `ScanHistoryResponse` | `types/ingestion.ts` |
| `GET /scanner/status` | `ScanProgress.to_dict()` | `HardwareScanStatus` | `types/ingestion.ts` |
| `GET /local-library/detect` | `{path,dat_count}` | `LibraryDetectResponse` | `types/ingestion.ts` |
| `POST /local-library/scan` | `{source,total_tracks,...}` | `LibraryScanResult` | `types/ingestion.ts` |
| `GET /local-library/status` | union (see §4.2) | `LibraryScanResult \| NoScanStatus` | `types/ingestion.ts` |
| `POST /tracks/{fp}/strata/analyze` | union (see §4.3) | `AnalyzeStrataResult` | `types/strata.ts` |
| `GET /strata/jobs/{id}` | job dict | `StrataJobStatus` | `types/strata.ts` |
| `GET /tracks` | `{tracks,total}` | `TrackListResponse` | `types/track.ts` |
| `GET /tracks/{fp}` | TrackAnalysis | `TrackAnalysis` | `types/track.ts` |
| `GET /tracks/resolve/{p}/{s}/{id}` | `{fingerprint,title,artist}` | `ResolveResult` | `api/tracks.ts` |
| `GET /tracks/{fp}/events` | `{fingerprint,events,...}` | `TrackEventsResponse` | `types/events.ts` |

---

## 6. Known DLP (Device Library Plus) Caveats

These affect XDJ-AZ, Opus Quad, and other DLP hardware:

1. `CdjStatus.getTrackType()` returns `NO_TRACK` even with loaded track — must infer from `isPlaying()` + `getRekordboxId() != 0`
2. `rekordbox_id` value can change between paused/playing states
3. `TimeFinder` unreliable over DLP/NFS — compute position from beat + beatgrid Python-side
4. BLUE-style waveforms require different extraction than THREE_BAND
5. Device discovery may be delayed; adapter synthesizes DeviceInfo from player_status if device_found was missed
