# Spec: Pioneer Waveform Live Fallback (FE-LIVE-DECK-PIONEER-WF)

## Frozen Intent
- **Stakeholder:** Brach
- **Problem:** Live Deck Monitor shows empty waveform for tracks without SCUE analysis. Pioneer decks already have waveform data (ANLZ) available via Pro DJ Link.
- **Desired outcome:** When a track loads on a deck, if no SCUE analysis exists, display the Pioneer waveform with playhead + auto-scroll — same UX as SCUE waveforms.
- **Non-goals:** Loop visualization (follow-up — see Follow-Up section). Replacing SCUE analysis. USB-scan path (separate spec: feat-pioneer-waveform-reading). Modifying WaveformCanvas.
- **Hard constraints:** WaveformFinder works on XDJ-AZ via beat-link 8.1.0-SNAPSHOT (ADR-017). Still broken on Opus Quad (no dbserver). Must degrade gracefully on unsupported hardware. Pioneer waveform sent once per track load (not per status update). Output must match RGBWaveform shape.
- **References:** ADR-014, ADR-017, feat-FE-live-deck-monitor spec

## Specification

### Data flow

```
Track loads on deck → WaveformFinder fires detailChanged() callback
  → BeatLinkBridge.emitTrackWaveform()    [extract per-band heights via segmentHeight API]
  → MessageEmitter.emitTrackWaveform()     [message type: "track_waveform", base64-encoded]
  → Python adapter._handle_track_waveform() [decode base64, normalize 0-31 → 0.0-1.0]
  → PlayerState.pioneer_waveform           [stored as RGBWaveform-shaped dict]
  → PlayerState.pioneer_waveform_version   [int, increments on change]
  → bridge_status WS payload               [version number only — not waveform data]
  → GET /api/bridge/pioneer-waveform/{pn}  [serves full RGBWaveform dict on demand]
  → usePioneerWaveform(pn, version) hook   [TanStack Query, refetches when version changes]
  → DeckPanel fallback                     [renders DeckWaveform + "Pioneer" badge]
```

### Java bridge: BeatLinkBridge.java

**Trigger:** WaveformFinder's `WaveformListener.detailChanged()` callback (registered alongside the existing `waveform_detail` emission at line ~666). Both `emitWaveformDetail()` (raw bytes for storage) and `emitTrackWaveform()` (decoded RGB for live display) fire on the same event.

**Method: `emitTrackWaveform(int player, WaveformDetail detail)`**
- Iterates `detail.getFrameCount()` frames
- Color waveforms (`detail.isColor`): extracts per-band heights via `detail.segmentHeight(i, 31, WaveformFinder.ThreeBandLayer.LOW/MID/HIGH)` — returns int 0-31
- Mono waveforms: uses `detail.segmentHeight(i, 31)` and writes same value for all 3 bands
- Packs as interleaved bytes: `[low₀, mid₀, high₀, low₁, mid₁, high₁, ...]` (3 bytes per frame)
- Base64 encodes the packed byte array
- Emits via `MessageEmitter.emitTrackWaveform(player, base64, frameCount, totalTimeMs, isColor)`
- Logs frame count, duration, and color mode

### Java bridge: MessageEmitter.java

**Method: `emitTrackWaveform(int playerNumber, String base64Data, int frameCount, long totalTimeMs, boolean isColor)`**
- Message type: `"track_waveform"`
- Payload fields: `data` (base64 string), `frame_count`, `total_time_ms`, `is_color`

### Python: messages.py

**Dataclass: `TrackWaveformPayload`**
- `data: str` — base64 of interleaved low/mid/high bytes (3 bytes per sample, values 0-31)
- `frame_count: int`
- `total_time_ms: int`
- `is_color: bool = True`

Message type constant `TRACK_WAVEFORM = "track_waveform"` added to `ALL_TYPES` and `PAYLOAD_TYPES` mapping.

### Python: adapter.py

**Handler: `_handle_track_waveform(msg)`**
1. Decodes base64 payload → raw bytes
2. Validates `len(raw) == frame_count * 3` (logs warning and returns on mismatch)
3. Extracts three arrays normalized to 0.0-1.0: `raw[i*3] / 31.0` for low, mid, high
4. Computes `duration = total_time_ms / 1000.0`
5. Computes `sample_rate = frame_count / duration` (fallback 150.0 if duration is 0)
6. Stores on `PlayerState.pioneer_waveform` as RGBWaveform-shaped dict: `{ low, mid, high, sample_rate, duration }`
7. Increments `PlayerState.pioneer_waveform_version`

**New fields on PlayerState:**
- `pioneer_waveform: dict | None = None` — RGBWaveform shape
- `pioneer_waveform_version: int = 0` — starts 0, increments on update

### Python: manager.py

`to_status_dict()` includes `pioneer_waveform_version` in the per-player dict within `bridge_status` WS messages. The full waveform data is NOT included (too large for repeated WS frames).

### REST endpoint: bridge.py

`GET /api/bridge/pioneer-waveform/{player_number}` → RGBWaveform dict or 404

Returns the cached `PlayerState.pioneer_waveform` dict directly. Returns 404 if no Pioneer waveform has been received for that player number, or if the bridge manager isn't initialized (503).

### Frontend: types/bridge.ts

`PlayerInfo` includes `pioneer_waveform_version: number` — used as a cache-busting signal.

### Frontend: api/tracks.ts

**Hook: `usePioneerWaveform(playerNumber: number, version: number)`**
- TanStack Query: `queryKey: ["pioneer-waveform", playerNumber, version]`
- Fetches `GET /api/bridge/pioneer-waveform/{playerNumber}`
- `enabled: version > 0` — no request until WaveformFinder has fired
- `staleTime: Infinity` — waveform data is immutable per version, never refetches the same version
- Returns `RGBWaveform` type

### Frontend: DeckPanel.tsx

Pioneer waveform used as fallback in two places:

1. **D4 (track not found in DB):** If `pioneerWf.data` exists, renders `DeckWaveform` with Pioneer data + bridge-only `DeckMetadata` (no analysis). No sections overlay (none available).

2. **D7 (SCUE analysis has no waveform):** If `pioneerWf.data` exists, renders `DeckWaveform` with Pioneer waveform but uses SCUE analysis sections and duration. `SectionIndicator` still renders.

Both cases render a "Pioneer" badge: `absolute top-1 right-1` blue pill (`bg-blue-900/70 text-blue-300 border border-blue-700/50`).

**Priority chain:** SCUE waveform (D6) > Pioneer waveform fallback > empty state.

### Playhead + auto-scroll

The existing `DeckWaveform` → `WaveformCanvas` pipeline handles playhead rendering. `playback_position_ms` from the bridge is passed through as `positionMs`, converted to seconds, and rendered as a cursor line. Auto-scroll keeps the cursor centered in a 12-second window. This works identically for Pioneer and SCUE waveforms — no special handling needed.

---

## Edge Cases

| Edge Case | Behavior |
|-----------|----------|
| WaveformFinder never fires (Opus Quad — no dbserver) | `pioneer_waveform` stays null, version stays 0, hook disabled. Falls through to existing empty states. |
| Mono waveform (non-color) | All three bands get same value in Java. Renders as monochrome blue-ish waveform. |
| Track changes on deck | `detailChanged()` fires for new track. Version increments. Hook refetches. Old waveform replaced. |
| Bridge restarts | `adapter.clear()` resets `pioneer_waveform` and version to defaults. |
| Very long tracks (>10min) | ~90K samples × 3 bytes = ~270KB base64. Acceptable for one-time REST fetch. |
| SCUE analysis exists with waveform | SCUE waveform used (D6 path). Pioneer waveform available but not displayed. |
| SCUE analysis exists without waveform | Pioneer waveform used as fallback (D7 path) with SCUE sections overlaid. |
| `playback_position_ms` is null (stopped) | Cursor not rendered. Waveform shows at default position. Same as SCUE path. |
| WaveformFinder fires before track resolution completes | Pioneer waveform cached on PlayerState. When DeckPanel reaches D4 render, data is already available. |

---

## Acceptance Criteria

1. Track loads on XDJ-AZ deck → Pioneer waveform appears on `/live` within ~2s (WaveformFinder latency)
2. Playhead + auto-scroll work identically to SCUE waveform (same DeckWaveform component)
3. SCUE-analyzed track with waveform → SCUE waveform shown, not Pioneer
4. Track change → Pioneer waveform updates (version increments, hook refetches)
5. XDJ-AZ works via WaveformFinder (ADR-017). Opus Quad degrades gracefully (no errors, falls through to empty state)
6. "Pioneer" badge visible (blue pill, top-right of waveform area) when showing Pioneer waveform
7. No modification to WaveformCanvas.tsx
8. D7 fallback: Pioneer waveform + SCUE sections overlaid when analysis exists but has no waveform

---

## Follow-Up: Loop Visualization

Beat-link exposes loop state on `CdjStatus`:
- `isLooping()` — boolean
- `getLoopStart()` / `getLoopEnd()` — long (ms? beats?)
- `getActiveLoopBeats()` — int (loop size in beats, e.g., 4, 8, 16)

These are not yet captured by the bridge. A future task should:
1. Extract loop fields in `handleCdjStatus()` and include in player_status payload
2. Add to `PlayerStatusPayload` and `PlayerInfo` types
3. Render loop region on the waveform (shaded overlay between loop start/end)
4. Show loop badge in DeckMetadata (e.g., "Loop 4 bars")

---

## Change Log
- 2026-03-21: Initial spec (pre-implementation)
- 2026-03-21: Updated to match implementation. Key corrections:
  - Acceptance criterion 5 updated: XDJ-AZ WaveformFinder WORKS (ADR-017), not "graceful degradation". Opus Quad is the broken case.
  - Added detail on WaveformListener trigger mechanism (fires alongside existing waveform_detail emission)
  - Documented `staleTime: Infinity` on usePioneerWaveform hook
  - Clarified priority chain: SCUE > Pioneer > empty
  - Added D7 fallback path (SCUE analysis without waveform + Pioneer waveform + SCUE sections)
  - Added playhead + auto-scroll section confirming existing pipeline handles this by design
  - Added follow-up section for loop visualization with beat-link API details
  - Added acceptance criterion 8 for D7 fallback
- 2026-03-21: Bug fix (e3e8101): `emitTrackWaveform()` used `ThreeBandLayer` overload for all color waveforms, but XDJ-AZ sends BLUE-style waveforms which don't support that overload. Fixed to branch on `detail.style`: THREE_BAND uses per-band heights, BLUE/RGB uses `segmentColor()` + `segmentHeight()`. Verified live on XDJ-AZ.
