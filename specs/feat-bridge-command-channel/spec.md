---
status: DRAFT
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
pdr_ref: none
evidence_ref: none
---

# Spec: Bridge Command Channel + Track Scanner

## Frozen Intent

### Problem Statement
SCUE's bridge is read-only (ADR-005). When a track is physically loaded on a CDJ, the bridge streams rich data (phrases, beatgrid, cues, waveform, metadata) that isn't available from USB scanning alone. The most valuable piece is Pioneer phrase analysis — instant arrangement structure without audio analysis. Currently there is no way to programmatically load tracks on a CDJ to capture this data. Manual loading is impractical for a full library.

### Target Users
Brach (DJ/operator) — batch-scan USB libraries through Pioneer hardware to capture Pioneer-only analysis data for all tracks.

### Desired Outcome
SCUE can iterate through tracks on connected USB drives, load each onto a CDJ deck, capture all available bridge data, persist it, and move to the next track. Three modes: scan ALL tracks on 1+ USBs, scan a filtered SUBSET, or scan a SINGLE track. Already-scanned tracks can be skipped or rescanned.

### Non-Goals
- Playback control (play/pause/pitch/sync)
- Playlist management or writing data TO the CDJ
- Frontend UI (follow-up spec — this spec covers backend only)

### Hard Constraints
- Bridge stays transport-only — no file I/O, no dedup logic, no scan state in Java
- Python Layer 1 owns all persistence and orchestration
- Must work with XDJ-AZ (DLP hardware, beat-link 8.1.0-SNAPSHOT)
- Must not interfere with a live DJ set — scan mode is an offline/prep workflow
- NEVER overwrite Pioneer-sourced data with SCUE-derived data (existing rule)

### Quality Priorities
1. Correctness — every track's data must be captured completely or not at all
2. Reliability — graceful handling of timeouts, disconnects, hardware quirks
3. Performance — secondary; scanning speed is bounded by hardware load time (~2-5s/track)

## Mutable Specification

### Summary
Extend the beat-link bridge with a bidirectional command channel over the existing WebSocket. Add four commands: `browse_root_menu`, `browse_playlist`, `browse_all_tracks`, and `load_track`. Build a Python scan orchestrator that uses these commands to iterate through a USB's track list, load each track, wait for Finder data to arrive via the existing read-only stream, and persist the captured data.

### User-Facing Behavior
REST API endpoints for:
- Browsing USB contents on connected players (playlists, folders, tracks)
- Starting/stopping/monitoring a scan job
- WebSocket progress updates during scan

### Technical Requirements

#### 1. Java Bridge: Bidirectional WebSocket + Command Handler

- `BridgeWebSocketServer.onMessage()` parses incoming JSON commands and routes to `CommandHandler`
- `CommandHandler` maps command names to beat-link API calls
- `MessageEmitter` gains `emitCommandResponse()` for request/response correlation
- No new Finder code — existing listeners already emit all data when a track loads

**Command protocol (JSON over existing WebSocket):**

```json
// Client → Bridge
{
  "command": "load_track",
  "request_id": "uuid-1234",
  "params": {
    "target_player": 1,
    "rekordbox_id": 42001,
    "source_player": 1,
    "source_slot": "usb",
    "source_type": "rekordbox"
  }
}

// Bridge → Client
{
  "type": "command_response",
  "timestamp": 1234567890.5,
  "player_number": null,
  "payload": {
    "request_id": "uuid-1234",
    "status": "ok",
    "command": "load_track",
    "data": {}
  }
}
```

**Commands:**

| Command | beat-link API | Returns |
|---------|--------------|---------|
| `browse_root_menu` | `MenuLoader.requestRootMenuFrom(player, slot)` | Menu items (folders, playlists) |
| `browse_playlist` | `MenuLoader.requestPlaylistMenuFrom(player, slot, folderId, sortOrder)` | Track list within a folder |
| `browse_all_tracks` | `MenuLoader.requestTracklistFrom(player, slot, sortOrder)` | Flat list of all tracks |
| `load_track` | `VirtualCdj.sendLoadTrackCommand(...)` | Ack (data arrives via existing Finder stream) |

#### 2. Python Bridge: Command Sender

- `commands.py` — typed command dataclasses + serialization
- `client.py` — `send_command()` method with request/response correlation via `request_id`
- `messages.py` — add `COMMAND_RESPONSE` type and `CommandResponsePayload`

#### 3. Python Layer 1: Scan Orchestrator

- `scanner.py` — `TrackScanner` class with multi-deck parallel scanning
- Browse USB via bridge commands → filter (skip already-scanned unless rescan) → dispatch tracks to deck workers → each deck loads, waits for Finder data, persists → progress update → next
- Track is "already scanned" if its track data has a `pioneer_scan_data` field
- Configurable settle delay between loads (default 2s)
- 15s timeout per track load (tracks load fast, data arrives within seconds)
- **Multi-deck scanning:** `target_players` parameter specifies which decks to use (1-6). Tracks are placed in a shared `asyncio.Queue`. Each deck runs a worker coroutine that pulls from the queue concurrently. Per-deck capture slots (`DeckCaptureSlot`) route Finder data by `player_number`. Defaults to single-deck when `target_players` is omitted.

#### 4. Python API: Scanner Endpoints

- `POST /api/scanner/start` — `{ player, slot, mode, track_ids?, force_rescan, target_players? }`
- `GET /api/scanner/status` — current scan progress (includes per-deck breakdown via `deck_progress`)
- `POST /api/scanner/stop` — abort current scan
- `GET /api/scanner/browse/{player}/{slot}` — browse USB contents
- WebSocket: `scan_progress`, `scan_complete` messages

### Interface Definitions

```python
# scue/bridge/commands.py

@dataclass
class LoadTrackCommand:
    target_player: int
    rekordbox_id: int
    source_player: int
    source_slot: str       # "usb" | "sd"
    source_type: str = "rekordbox"

@dataclass
class BrowseAllTracksCommand:
    player_number: int
    slot: str              # "usb" | "sd"
    sort_order: str = "default"

@dataclass
class CommandResponse:
    request_id: str
    status: str            # "ok" | "error"
    command: str
    data: dict
    error_message: str | None = None
```

```java
// bridge-java CommandHandler.java

public class CommandHandler {
    void handleCommand(String command, String requestId, Map<String, Object> params);
    // Routes to: handleBrowseRootMenu, handleBrowsePlaylist,
    //            handleBrowseAllTracks, handleLoadTrack
}
```

### Layer Boundaries
- **Layer 0 (bridge)** is responsible for: accepting commands, forwarding to beat-link, streaming responses. No state, no persistence.
- **Layer 1 (scanner)** is responsible for: orchestration, dedup/skip logic, persistence, progress tracking.
- Interface between them: command/response JSON over WebSocket (Layer 0) + existing Finder data stream (Layer 0 → Layer 1).

### Edge Cases
- Track load timeout (15s): mark as error, continue to next track
- Bridge disconnect mid-scan: pause scan, attempt reconnect, resume or abort
- USB removed during scan: bridge will emit device_lost, scanner aborts with partial results
- Empty USB (no tracks): scan completes immediately with 0 scanned
- Track with no phrase data: still capture whatever is available (beatgrid, cues, waveform)
- Track already loaded on deck: load command may be a no-op; still wait for Finder data
- MenuLoader returns empty for DLP hardware without dbserver: error response, scan cannot proceed

### Open Questions
- None

### Change Log
<!-- When spec changes during implementation, record the change and its upstream cause. -->
- **2026-03-25:** Removed "multi-deck parallel scanning" from Non-Goals. Added multi-deck support to Technical Requirements §3 and §4. Scanner now accepts `target_players` for 1-6 concurrent deck workers. Upstream: operator decision to support parallel scanning from day one (minimum 2 decks practical for any DJ setup).
