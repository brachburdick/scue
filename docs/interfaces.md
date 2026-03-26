# Interface Contracts

This file is the canonical cross-layer and backend/frontend contract reference for SCUE.
It supersedes `docs/CONTRACTS.md`, which remains as a compatibility pointer for older workflow docs.

## Layer 0 -> Layer 1: BridgeMessage

The bridge streams typed JSON messages over a local WebSocket. The adapter in `scue/bridge/adapter.py` normalizes these into Layer 1's internal types.

```python
@dataclass
class BridgeMessage:
    type: str               # "device_found" | "device_lost" | "bridge_status" |
                            # "player_status" | "track_metadata" | "beat_grid" |
                            # "waveform_detail" | "phrase_analysis" | "cue_points" | "beat"
    timestamp: float
    player_number: int | None
    payload: dict           # type-specific, see ARCHITECTURE.md for schemas
```

**bridge_status payload (v1.2.0):** Includes `network_interface`, `network_address`, `interface_candidates` (list of scored interface options), `warning`, and `error` fields. See `docs/ARCHITECTURE.md` and `scue/bridge/messages.py:BridgeStatusPayload` for the full schema.

### Command channel (ADR-022)

The bridge also accepts commands from Python over the same WebSocket. Commands are JSON objects; responses are `command_response` messages correlated by `request_id`.

```python
# Python → Java (command)
{
    "command": "load_track" | "browse_root_menu" | "browse_playlist" | "browse_all_tracks",
    "request_id": "uuid",
    "params": { ... }  # command-specific
}

# Java → Python (response, uses standard BridgeMessage envelope)
BridgeMessage(
    type="command_response",
    payload={
        "request_id": "uuid",
        "status": "ok" | "error",
        "command": "load_track",
        "data": { ... },
        "error_message": None | "..."
    }
)
```

Command sender: `scue/bridge/client.py:BridgeWebSocket.send_command()`
Command handler: `bridge-java/.../CommandHandler.java`
See `specs/feat-bridge-command-channel/spec.md` for the full protocol.

### Scanner API (multi-deck)

The track scanner supports 1-6 decks scanning in parallel from a shared work queue.

```python
# POST /api/scanner/start
{
    "player": 1,                    # player used for browsing + default scan deck
    "slot": "usb",                  # "usb" | "sd"
    "target_players": [1, 2],       # optional: which decks to use (default: [player])
    "track_ids": [42001, 42002],    # optional: filter to these rekordbox IDs
    "force_rescan": false
}

# GET /api/scanner/status → ScanProgress
{
    "status": "scanning",
    "total": 100,
    "scanned": 42,
    "skipped": 5,
    "errors": 1,
    "deck_progress": {              # per-deck breakdown
        "1": {"scanned": 22, "errors": 0, "current_track": "..."},
        "2": {"scanned": 20, "errors": 1, "current_track": "..."}
    }
}
```

Data routing: Finder data callbacks route by `player_number` to per-deck `DeckCaptureSlot` instances. `CapturedTrackData.source_player` tracks which deck captured each track.

Scanner orchestrator: `scue/layer1/scanner.py:TrackScanner`
Scanner API: `scue/api/scanner.py`

### Local Library Scanner

Reads rekordbox ANLZ files from the local filesystem without hardware.

```python
# GET /api/local-library/detect → library info or 404
{"path": "~/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ", "dat_count": 342}

# POST /api/local-library/scan
{"path": null, "force_rescan": false}  # null = auto-detect
```

Persistence uses composite key `source_player="local"`, `source_slot="library"`.

Scanner: `scue/layer1/rekordbox_scanner.py`
API: `scue/api/local_library.py`

## Layer 1 -> Layer 2: DeckMix

The DeckMix is the interface between Layer 1 and Layer 2.
Layer 2 MUST NOT import anything from layer1 except `DeckMix`, `WeightedCursor`, `TrackCursor`, and their contained types.

```python
@dataclass
class DeckMix:
    cursors: list[WeightedCursor]          # one per active deck

@dataclass
class WeightedCursor:
    cursor: TrackCursor
    weight: float                          # 0.0-1.0, how much this deck contributes
    source: str                            # "on_air" | "crossfader" | "manual"

@dataclass
class TrackCursor:
    player_number: int                     # physical deck (1, 2, 3, 4)
    current_section: SectionInfo
    next_section: SectionInfo | None
    upcoming_events: list[MusicalEvent]    # next N events, time-adjusted for current tempo
    current_features: TrackFeatures
    beat_position: BeatPosition
    playback_state: PlaybackState

@dataclass
class SectionInfo:
    label: str                             # intro, verse, build, drop, breakdown, outro
    start_time: float
    end_time: float
    bar_count: int
    expected_bar_count: int
    progress: float                        # 0.0-1.0
    confidence: float
    irregular_phrase: bool
    fakeout: bool
    source: str                            # "analysis" | "pioneer_enriched"

@dataclass
class BeatPosition:
    beat_in_bar: int                       # 1-4
    bar_in_section: int
    is_downbeat: bool
    bpm: float
    original_bpm: float
    timestamp: float
```

## Layer 2 -> Layer 3: CueEvent stream

```python
@dataclass
class CueEvent:
    id: str
    type: str                              # see taxonomy in ARCHITECTURE.md
    timestamp: float
    duration: float | None
    intensity: float                       # 0.0-1.0
    musical_context: MusicalContext
    payload: dict                          # type-specific, schema per cue type
    priority: int                          # for drop decisions under load

@dataclass
class MusicalContext:
    section_label: str
    section_progress: float
    track_energy: float
    track_mood: str
```

## Layer 3 -> Layer 4: AbstractOutput

```python
@dataclass
class FixtureOutput:
    fixture_name: str
    group: str
    channels: dict[str, float]             # channel_name -> 0.0-1.0 normalized value
    # Standard channel names: brightness, color_r, color_g, color_b,
    # color_h, color_s, color_v, position, beam_width, strobe_rate
```

## Backend -> Frontend: WebSocket Messages

The backend streams typed JSON messages to the frontend over `ws://localhost:8000/ws`.
Managed by `scue/api/ws.py` + `scue/api/ws_manager.py`. Frontend dispatch lives in `frontend/src/api/ws.ts`.

### bridge_status (on every bridge state change)

```json
{
  "type": "bridge_status",
  "payload": {
    "status": "running",
    "port": 17400,
    "network_interface": "en16",
    "jar_path": "lib/beat-link-bridge.jar",
    "jar_exists": true,
    "jre_available": true,
    "restart_count": 0,
    "restart_attempt": 0,
    "next_retry_in_s": null,
    "mode": "bridge",
    "route_correct": true,
    "route_warning": null,
    "devices": { "<ip>": { "device_name": "XDJ-AZ", "device_number": 1, "device_type": "cdj", "uses_dlp": true } },
    "players": { "1": { "bpm": 128.0, "pitch": 0.0, "playback_state": "playing", "is_on_air": true, "rekordbox_id": 42001, "beat_within_bar": 3, "track_type": "rekordbox", "playback_position_ms": 92450, "track_source_player": 1, "track_source_slot": "usb" } }
  }
}
```

- `restart_attempt`: current attempt number during restart backoff (0 when stable)
- `next_retry_in_s`: seconds until next restart attempt (null when not retrying)
- `mode`: one of three values:
  - `"bridge"` — full beat-link running (normal operation)
  - `"fallback"` — UDP-only degraded mode (JRE or JAR unavailable)
  - `"waiting_for_hardware"` — bridge reached crash threshold with no hardware detected; polling every 30s for hardware to reappear

### pioneer_status (every 2 seconds)

```json
{
  "type": "pioneer_status",
  "payload": {
    "is_receiving": true,
    "bridge_connected": true,
    "last_message_age_ms": 450
  }
}
```

- `is_receiving`: true when Pioneer hardware data (device/player/beat messages) arrived within threshold. Derived from `_last_pioneer_message_time`, not general bridge heartbeats.
- `bridge_connected`: true when the bridge subprocess is alive and sending any messages (including heartbeats).
- `last_message_age_ms`: milliseconds since last Pioneer hardware message.

Frontend types: `frontend/src/types/ws.ts` (`WSMessage` union), `frontend/src/types/bridge.ts` (payload shapes).
Store: `frontend/src/stores/bridgeStore.ts` (independent Zustand store).

### strata_live (on track load with Pioneer phrase data)

```json
{
  "type": "strata_live",
  "payload": {
    "player_number": 2,
    "formula": {
      "fingerprint": "live_2004",
      "version": 1,
      "pipeline_tier": "live",
      "analysis_source": "pioneer_live",
      "stems": [ { "stem_type": "other", "waveform": { "low": [...], "mid": [...], "high": [...], "sample_rate": 150, "duration": 180.0 }, "activity": [...], "events": [], "patterns": [], "energy_curve": [...] } ],
      "patterns": [],
      "sections": [ { "section_label": "intro", "section_start": 0.0, "section_end": 15.3, "energy_level": 0.3, "energy_trend": "rising", ... } ],
      "transitions": [ { "type": "energy_shift", "timestamp": 15.3, "energy_delta": 0.45, ... } ],
      "total_layers": 1,
      "total_patterns": 0,
      "arrangement_complexity": 0.5
    }
  }
}
```

- Fires when `PlaybackTracker` builds an `ArrangementFormula` from Pioneer phrase analysis + beat grid + waveform data. Constructed by `LiveStrataAnalyzer.build_from_pioneer()`.
- Broadcast is fire-and-forget — clients that connect after the broadcast use the `GET /api/strata/live` REST endpoint to fetch the current state.
- `fingerprint` is synthetic: `"live_{rekordbox_id}"` (no audio file hash available).
- `patterns` is always empty (no audio = no pattern discovery).
- `stems` contains a single "other" (mix) entry using the Pioneer RGB waveform.

Frontend types: `frontend/src/types/ws.ts` (`WSStrataLive`).
Store: `frontend/src/stores/strataLiveStore.ts` (independent Zustand store).

## Backend -> Frontend: Live Strata REST API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/strata/live` | GET | Get current live strata formulas for all active players |

### Response shape

```json
{
  "players": {
    "2": { "fingerprint": "live_2004", "pipeline_tier": "live", "analysis_source": "pioneer_live", "sections": [...], "transitions": [...], ... }
  }
}
```

- Returns per-player `ArrangementFormula` objects built from Pioneer hardware data.
- Players without sufficient data (no phrases or no beat grid) are omitted.
- Frontend polls every 2s when the Live tier is selected via `useLiveStrata()` hook.
- Complements the `strata_live` WS message: REST provides on-demand access, WS provides instant push.

Frontend hook: `frontend/src/api/strata.ts` (`useLiveStrata()`).

## Backend -> Frontend: Network REST API

Endpoints in `scue/api/network.py` for interface enumeration and route management.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/network/interfaces` | GET | List interfaces with scoring |
| `/api/network/route` | GET | Current route state |
| `/api/network/route/fix` | POST | Trigger route fix |
| `/api/network/route/setup-status` | GET | Sudoers + launchd status |

Frontend hooks: `frontend/src/api/network.ts` (TanStack Query).

## Backend -> Frontend: Events REST API

Endpoints in `scue/api/tracks.py` for event detection data (M7).

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tracks/{fingerprint}/events` | GET | Get detected events + drum patterns for a track |

### Response shape

```json
{
  "fingerprint": "abc123...",
  "events": [
    {
      "type": "riser",
      "timestamp": 30.5,
      "duration": 4.2,
      "intensity": 0.85,
      "payload": { "slope": 120.5, "r_squared": 0.92, "section": "build" }
    }
  ],
  "drum_patterns": [
    {
      "bar_start": 0,
      "bar_end": 4,
      "kick": [1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0],
      "snare": [0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0],
      "clap": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
      "hihat_type": "8ths",
      "hihat_density": 0.5,
      "hihat_open_ratio": 0.0,
      "confidence": 0.7
    }
  ],
  "total_events": 42,
  "total_patterns": 16,
  "event_types": ["kick", "snare", "riser", "stab"]
}
```

Frontend types: `frontend/src/types/events.ts` (`MusicalEvent`, `DrumPattern`, `TrackEventsResponse`).

## Frontend Internal: ActiveEventState (Shared Playback Context)

The `useActiveEvents` hook computes a unified "what's happening at time T" state from any
cursor source. Used by `<LiveEventDisplay />` on the annotation page and live deck monitor.

```typescript
// Input: each page provides its own cursor time
useActiveEvents(
  currentTime: number | null,       // seconds (from audio element or bridge WS)
  events: EventInput[],              // MusicalEvent[] or GroundTruthEvent[]
  sections: Section[],
  beats: number[],
  downbeats: number[],
  options?: { recentWindow?: number; previewCount?: number }
): ActiveEventState | null

// Output
interface ActiveEventState {
  currentTime: number;
  activeSections: Section[];         // cursor inside [start, end)
  recentEvents: FiredEvent[];        // fired within recentWindow (default 300ms)
  upcomingEvents: EventPreview[];    // next N events after cursor
  phrase: PhraseInfo | null;         // bar/phrase position from beatgrid
}
```

**Files:** `src/hooks/useActiveEvents.ts`, `src/types/activeEvents.ts`, `src/components/shared/LiveEventDisplay.tsx`

**Design decision:** Shared hook + shared component, not a new Zustand store. Cursor sources
are legitimately different per page (bridge WS vs HTML audio). The computation is pure and
cheap (O(log n) binary search). See `specs/feat-live-event-display/spec.md`.

## Backend -> Frontend: Waveform Presets REST API

Endpoints in `scue/api/waveform_presets.py` for waveform rendering preset management.
Presets stored in `config/waveform-presets.yaml`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/waveform-presets` | GET | List all presets with active flag |
| `/api/waveform-presets/active` | GET | Get the currently active preset |
| `/api/waveform-presets` | POST | Create a new preset |
| `/api/waveform-presets/{id}` | PUT | Update a preset's params or name |
| `/api/waveform-presets/{id}` | DELETE | Delete a preset (cannot delete active) |
| `/api/waveform-presets/{id}/activate` | POST | Set a preset as active |

### List response shape

```json
{
  "activePresetId": "default",
  "presets": [
    {
      "id": "default",
      "name": "SCUE Default",
      "isActive": true,
      "createdAt": "2026-03-24T00:00:00Z",
      "updatedAt": "2026-03-24T00:00:00Z",
      "params": {
        "normalization": "global",
        "lowGain": 1.0, "midGain": 1.0, "highGain": 1.0,
        "frequencyWeighting": "none",
        "lowCrossover": 200, "highCrossover": 2500,
        "amplitudeScale": "linear",
        "gamma": 1.0, "logStrength": 10,
        "noiseFloor": 0.001, "peakNormalize": true,
        "colorMode": "rgb_blend",
        "lowColor": "#ff0000", "midColor": "#00ff00", "highColor": "#0000ff",
        "saturation": 1.0, "brightness": 1.0, "minBrightness": 0.0
      }
    }
  ]
}
```

Frontend types: `frontend/src/types/waveformPreset.ts` (`WaveformPreset`, `WaveformRenderParams`, `WaveformPresetsResponse`).
Store: `frontend/src/stores/waveformPresetStore.ts` (independent Zustand store).
API hooks: `frontend/src/api/waveformPresets.ts` (TanStack Query).

## Change Protocol

Any change to these contracts requires:
1. A discussion with Brach
2. An entry in `docs/DECISIONS.md` explaining why
3. Updates to both the producing and consuming layer
4. Updated tests on both sides
