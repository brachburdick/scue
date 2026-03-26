# Feature: Live Pioneer Data Persistence

## Problem

SCUE receives rich per-track analysis data from Pioneer hardware via Ethernet (phrase analysis, beat grid, RGB waveform, cue points) — but only while tracks are loaded on a player. Once the set ends or hardware disconnects, that data is gone. To iterate on cue generation quality using live data offline, we need to persist it.

## Goal

Capture and store all Pioneer-sourced track data as it streams in during a live set, so that:
1. Tracks played during a set accumulate a "live" dataset in the DB
2. Strata can run a "Live - Offline" analysis tier against saved live data without hardware
3. The DJ can build up a library of live-analyzed tracks over multiple sessions

## Data Shape Per Track

When a track is loaded on a Pioneer player, the bridge delivers these payloads (all arrive once per track load, except playback state which streams continuously):

### Static Data (captured once per track load)

| Field | Shape | Source Message |
|-------|-------|----------------|
| **Phrase analysis** | `list[{start_beat: int, end_beat: int, kind: str, mood: int}]` | `phrase_analysis` |
| **Beat grid** | `list[{beat_number: int, time_ms: float, bpm: float}]` | `beat_grid` |
| **RGB waveform** | `{low: float[], mid: float[], high: float[], sample_rate: float}` | `track_waveform` |
| **Cue points** | `list[{time_ms: float, name: str, color: str}]` | `cue_points` |
| **Memory points** | `list[{time_ms: float, name: str, color: str}]` | `cue_points` |
| **Hot cues** | `list[{slot: int, time_ms: float, name: str, color: str}]` | `cue_points` |

### Track Identity

| Field | Shape | Notes |
|-------|-------|-------|
| `rekordbox_id` | `int` | DLP track ID from CdjStatus |
| `fingerprint` | `str` | SCUE content hash (resolved Python-side via TrackCache) |
| `title` | `str` | From rekordbox metadata |
| `artist` | `str` | From rekordbox metadata |
| `bpm` | `float` | From CdjStatus (effective BPM) |
| `duration` | `float` | From rekordbox metadata (seconds) |
| `key` | `str` | From rekordbox metadata |

### Playback Context (optional, for future use)

| Field | Shape | Notes |
|-------|-------|-------|
| `player_number` | `int` | Which deck (1-4) |
| `session_timestamp` | `datetime` | When this track was loaded |
| `pitch_range_observed` | `(float, float)` | Min/max pitch during playback |
| `was_on_air` | `bool` | Whether the track was actually mixed (fader up) |

## Storage Design

### Option A: JSON sidecar files (recommended, matches existing strata pattern)
- Store in `tracks/{fingerprint}/live_pioneer.json`
- One file per track, overwritten if re-captured (newer data wins)
- Fits the existing "JSON files are source of truth" convention

### Option B: SQLite table
- New `pioneer_live_data` table in the track cache DB
- Columns for each data type (JSON blobs for arrays)
- Better for querying "which tracks have live data" but adds schema migration

### Recommendation
Option A for data storage (consistency with strata JSON patterns), with a boolean flag in SQLite for fast filtering (`has_live_data: bool` column on `tracks` table).

## Capture Trigger

Data should be captured automatically when:
1. A track is loaded on a player AND
2. Phrase analysis + beat grid have both arrived (these are the minimum useful set)

The capture point is in `tracking.py` where `PlayerState` accumulates bridge messages. Once the required fields are populated, snapshot to disk.

### UI Trigger (secondary)
A manual "Save Live Data" button on the Bridge page could force-capture current player state, useful for:
- Debugging
- Capturing data from a track that's about to be unloaded
- Re-capturing after a bridge reconnect

## What This Does NOT Include

- Parsing ANLZ files directly from USB (that's a separate feature)
- Scanning all tracks on USB without loading them (bridge limitation)
- Any changes to the strata analysis engine (separate "Live - Offline" tier spec)

## Integration Points

| Layer | Change | Notes |
|-------|--------|-------|
| `scue/layer1/tracking.py` | Add capture logic in `on_player_update()` | When PlayerState has phrases + beat_grid, save snapshot |
| `scue/layer1/storage.py` | Add `save_live_data()` / `load_live_data()` / `has_live_data()` | JSON sidecar read/write |
| `scue/api/tracks.py` | Expose `has_live_data` in track list response | For table filtering |
| `scue/api/bridge.py` or similar | Optional manual capture endpoint | `POST /api/tracks/{fp}/capture-live` |
| SQLite schema | Add `has_live_data` bool to tracks table | Fast filtering |

## Acceptance Criteria

1. When a track is loaded on a Pioneer player and phrase + beat grid arrive, the data is persisted to disk automatically
2. `GET /api/tracks` response includes `has_live_data: bool` per track
3. Saved data survives server restart
4. Re-loading the same track overwrites with fresh data (idempotent)
5. `TrackStore.load_live_data(fingerprint)` returns the saved pioneer data or None

## Scope Boundaries

- **Owned paths:** `scue/layer1/storage.py`, `scue/layer1/tracking.py`, `scue/api/tracks.py`, track JSON files
- **NOT owned:** `scue/layer1/strata/` (the "Live - Offline" tier that consumes this data is a separate task)
- **NOT owned:** Frontend changes (track table column additions are a separate task)
