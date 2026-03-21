# Spec: Pioneer Waveform Live Fallback (FE-LIVE-DECK-PIONEER-WF)

## Frozen Intent
- **Stakeholder:** Brach
- **Problem:** Live Deck Monitor shows empty waveform for tracks without SCUE analysis. Pioneer decks already have waveform data (ANLZ) available via Pro DJ Link.
- **Desired outcome:** When a track loads on a deck, if no SCUE analysis exists, display the Pioneer waveform with playhead + auto-scroll — same UX as SCUE waveforms.
- **Non-goals:** Loop visualization (follow-up task). Replacing SCUE analysis. USB-scan path (separate spec: feat-pioneer-waveform-reading). Modifying WaveformCanvas.
- **Hard constraints:** WaveformFinder works on XDJ-AZ via beat-link 8.1.0-SNAPSHOT (ADR-017). Still broken on Opus Quad (no dbserver). Must degrade gracefully on unsupported hardware. Pioneer waveform sent once per track load (not per status update). Output must match RGBWaveform shape.
- **References:** ADR-014, feat-FE-live-deck-monitor spec, feat-pioneer-waveform-reading spec

## Specification

### Data flow

```
WaveformFinder (Java/beat-link)
  → BeatLinkBridge.emitTrackWaveform()     [extract per-band heights via segmentHeight API]
  → MessageEmitter.emitTrackWaveform()      [new message type: "track_waveform"]
  → Python adapter._handle_track_waveform() [decode base64, convert to RGBWaveform dict]
  → PlayerState.pioneer_waveform            [stored as RGBWaveform-shaped dict]
  → PlayerState.pioneer_waveform_version    [int, increments on change]
  → bridge_status WS payload                [version number only, not waveform data]
  → GET /api/bridge/pioneer-waveform/{pn}   [serves full RGBWaveform dict]
  → usePioneerWaveform(pn, version) hook    [TanStack Query, refetches on version change]
  → DeckPanel fallback                      [renders DeckWaveform + "Pioneer" badge]
```

### Java bridge changes

New method in BeatLinkBridge: `emitTrackWaveform(int player, WaveformDetail detail)`
- Uses `detail.segmentHeight(i, 31, ThreeBandLayer.LOW/MID/HIGH)` for color waveforms
- Uses `detail.segmentHeight(i, 31)` for mono (same value all 3 bands)
- Packs as interleaved bytes (low, mid, high per sample), base64-encodes
- Emits with frame_count, total_time_ms, is_color metadata
- Triggered by existing WaveformListener (alongside existing waveform_detail emission)

New method in MessageEmitter: `emitTrackWaveform(player, base64, frameCount, totalTimeMs, isColor)`
- Message type: "track_waveform"

### Python bridge changes

New dataclass `TrackWaveformPayload` in messages.py:
- data: str (base64 of interleaved LMH bytes)
- frame_count: int
- total_time_ms: int
- is_color: bool

New handler `_handle_track_waveform()` in adapter.py:
- Decodes base64 → extracts low/mid/high arrays → normalizes 0-31 to 0.0-1.0
- Computes sample_rate = frame_count / (total_time_ms / 1000)
- Stores as RGBWaveform dict: { low, mid, high, sample_rate, duration }
- Increments pioneer_waveform_version

New fields on PlayerState:
- pioneer_waveform: dict | None (RGBWaveform shape)
- pioneer_waveform_version: int (starts 0, increments on update)

### REST endpoint

`GET /api/bridge/pioneer-waveform/{player_number}` → RGBWaveform dict or 404

### Frontend changes

PlayerInfo type gets: `pioneer_waveform_version: number`

New hook `usePioneerWaveform(playerNumber: number, version: number)`:
- TanStack Query, fetches from REST endpoint
- Query key includes version for automatic refetch
- enabled only when version > 0

DeckPanel changes:
- After D4 (not-found) or D7 (no-waveform): check if Pioneer waveform available
- If available: render DeckWaveform with Pioneer data + metadata if available
- Show small "Pioneer" badge on the waveform area

### Edge cases

- WaveformFinder never fires (Opus Quad — no dbserver): pioneer_waveform stays null, no badge, existing behavior
- Mono waveform: all three bands same value, renders as blue-ish monochrome
- Track changes: version increments, hook refetches, old waveform replaced
- Bridge restarts: adapter.clear() resets pioneer_waveform state
- Very long tracks (>10min): ~90K samples, ~270KB base64 — acceptable for one-time REST fetch

### Acceptance criteria

1. Track loads on non-DLP deck → Pioneer waveform appears on /live within 2s
2. Playhead + auto-scroll work identically to SCUE waveform
3. SCUE-analyzed track → SCUE waveform shown (not Pioneer)
4. Track change → waveform updates
5. DLP device (XDJ-AZ) → graceful degradation, no errors
6. "Pioneer" badge visible when showing Pioneer waveform
7. No modification to WaveformCanvas.tsx

## Change Log
- 2026-03-21: Initial spec
