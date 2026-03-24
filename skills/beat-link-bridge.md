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

## API Reference (Key Classes)

### CdjStatus (org.deepsymmetry.beatlink.CdjStatus)
- `getEffectiveTempo()` → actual BPM as double (NOT BPM*100). Returns garbage (e.g., 658.63) when no track loaded — guard with `isTrackLoaded()` or `isPlaying()`
- `getBeatNumber()` → current beat number in the track
- `isPlaying()` → boolean, whether deck is actively playing
- `isTrackLoaded()` → boolean (use to guard tempo/position calls)
- `getTrackSourcePlayer()` → int, which player the track was loaded from
- `getTrackSourceSlot()` → `CdjStatus.TrackSourceSlot` enum
- `getRekordboxId()` → int, rekordbox track ID

### TimeFinder (org.deepsymmetry.beatlink.data.TimeFinder)
- `getTimeFor(CdjStatus)` → milliseconds position in track
- UNRELIABLE over DLP/NFS connections — prefer computing position from beat_number + beatgrid Python-side
- Must be started BEFORE MetadataFinder

### Finder Start Order (critical)
```
TimeFinder → MetadataFinder → BeatGridFinder → WaveformFinder → AnalysisTagFinder
```
Dependencies flow left-to-right. Starting out of order causes silent failures.

### WaveformFinder
- XDJ-AZ produces BLUE-style waveforms (single color channel), NOT THREE_BAND (RGB)
- `WaveformDetail.segmentHeight(i, max, ThreeBandLayer)` THROWS on BLUE-style — check style first
- Opus Quad has no dbserver — WaveformFinder doesn't work via standard path (needs CrateDigger NFS)

### pyrekordbox gotchas
- Tempo field returns actual BPM (NOT BPM*100 like some Pioneer formats)
- Time fields return seconds (NOT milliseconds)
- `anlz.get("beat_grid")` returns a tuple, not a tag directly — unpack it

## Anti-Patterns

- Using bare `python` to run bridge-related code (use `.venv/bin/python`)
- Assuming bridge is always connected — handle degraded/fallback mode
- Directly parsing UDP in Python when the Java bridge is available
- [TODO: Fill from project experience]
