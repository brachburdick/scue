# Spec: FE-Live-Deck-Monitor

## Summary

A real-time 2-deck monitoring page showing per-deck waveform with beat-synced cursor, track metadata, section/event overlays, and full diagnostic information. Each deck displays the currently loaded track's analysis data (resolved via composite key `(source_player, source_slot, rekordbox_id) → fingerprint → TrackAnalysis`) with a live playback cursor driven by `playback_position_ms` from the backend. Stacked vertical layout (Deck 1 on top, Deck 2 below). Requires backend contract changes to add `playback_position_ms`, `track_source_player`, and `track_source_slot` to the bridge status players dict, and a multi-USB-safe resolve endpoint.

Route: `/live`
Sidebar: Top-level entry "Live Monitor" (not nested under Data or System).

**Research-driven design note:** `rekordbox_id` is a per-USB auto-increment key, NOT globally unique. Two USBs plugged into different decks can have the same `rekordbox_id` for completely different tracks. Track resolution MUST use the composite key `(source_player, source_slot, rekordbox_id)` to avoid silent mismatches. See `research/dlp-track-id-reliability.md`.

---

## User-Facing Behavior

The user navigates to `/live` and sees two vertically stacked deck panels. When Pioneer hardware is connected and decks are loaded, each panel shows:
1. A Pioneer-style colored waveform (shared `WaveformCanvas` component from Analysis Viewer) with a moving playback cursor.
2. Section overlays on the waveform showing current/upcoming sections.
3. Full diagnostic metadata: title, artist, BPM (effective + original), key, current section, playback state, pitch %, on-air status, fingerprint, rekordbox_id, confidence scores, data source.

The waveform auto-scrolls to keep the cursor centered. Sections highlight as the cursor enters them. The page is primarily for debugging and development, eventually becoming user-facing.

---

## Backend Contract Change: `playback_position_ms`

**Required change:** Add `playback_position_ms` to the players dict within `bridge_status` WS messages.

### Current players dict shape (from `docs/interfaces.md`):
```json
{
  "1": {
    "bpm": 128.0,
    "pitch": 0.0,
    "playback_state": "playing",
    "is_on_air": true,
    "rekordbox_id": 42001,
    "beat_within_bar": 3,
    "track_type": "rekordbox"
  }
}
```

### New players dict shape:
```json
{
  "1": {
    "bpm": 128.0,
    "pitch": 0.0,
    "playback_state": "playing",
    "is_on_air": true,
    "rekordbox_id": 42001,
    "beat_within_bar": 3,
    "track_type": "rekordbox",
    "playback_position_ms": 92450,
    "track_source_player": 1,
    "track_source_slot": "usb"
  }
}
```

**New fields:**
- `playback_position_ms` (float | null): Milliseconds from track start. Source: `CdjStatus.getPlaybackPosition()`. `null` when position is unknown.
- `track_source_player` (int): Player number where the track's media is physically inserted. Already parsed in `messages.py:PlayerStatusPayload` but not yet included in `to_status_dict()`.
- `track_source_slot` (string): Media slot — `"usb"`, `"sd"`, `"cd"`, or `"collection"`. Already parsed in `messages.py:PlayerStatusPayload` but not yet included in `to_status_dict()`.

**Why composite key matters:** `rekordbox_id` is a per-USB auto-increment key. Player 1 playing from USB-A and Player 2 playing from USB-B can both report `rekordbox_id: 1` for completely different tracks. The composite key `(track_source_player, track_source_slot, rekordbox_id)` disambiguates.

**Files to change:**
- `lib/beat-link-bridge.jar` source (Java) — include `playbackPosition` in player status JSON
- `scue/bridge/manager.py` — include `playback_position_ms`, `track_source_player`, `track_source_slot` in `to_status_dict()` player output (lines ~690-696)
- `docs/interfaces.md` — update `bridge_status` player schema
- `docs/CONTRACTS.md` — note the contract addition
- `frontend/src/types/bridge.ts` — add all three fields to `PlayerInfo` type
- `frontend/src/stores/bridgeStore.ts` — ensure fields flow through

**Note:** `track_source_player` and `track_source_slot` are already parsed in `scue/bridge/messages.py:PlayerStatusPayload` (lines 85-86). They just need to be forwarded through `manager.py:to_status_dict()`.

**Contract note:** These are additive, non-breaking changes. Existing consumers are unaffected.

### New REST Endpoint: Resolve track by composite key

**Endpoint:** `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}`
**Example:** `GET /api/tracks/resolve/1/usb/42001` — player 1, USB slot, rekordbox_id 42001.
**Response:** `{ "fingerprint": "abc123...", "title": "...", "artist": "..." }` or 404.

**Resolution strategy (tiered):**
1. Composite key lookup in `track_ids` table: `(source_player, source_slot, rekordbox_id) → fingerprint` — instant.
2. If miss: fallback to file path stem match (from USB scan metadata) — instant.
3. If miss: fallback to title+artist match — instant.
4. If all miss: return 404 ("Unknown track").

**Backend schema change:** The `track_ids` table must migrate from a single-column primary key to a composite key:
- **Current:** `rekordbox_id INTEGER PRIMARY KEY` (broken for multi-USB)
- **New:** `PRIMARY KEY (source_player, source_slot, rekordbox_id)` with columns `source_player INTEGER`, `source_slot TEXT`, `rekordbox_id INTEGER`, `fingerprint TEXT NOT NULL`, `first_seen REAL NOT NULL`
- `lookup_fingerprint()` must accept all three fields
- `link_rekordbox_id()` must accept all three fields

**Files to change:**
- `scue/layer1/storage.py` — migrate `track_ids` table schema, update `lookup_fingerprint()` and `link_rekordbox_id()` signatures
- `scue/layer1/usb_scanner.py` — pass `source_player` and `source_slot` to `link_rekordbox_id()`
- `scue/api/tracks.py` — add resolve endpoint (must be BEFORE `/{fingerprint}` catch-all)
- `frontend/src/api/tracks.ts` — add `useResolveTrack(sourcePlayer, sourceSlot, rekordboxId)` hook

---

## Page Layout

```
+----------------------------------------------------------+
| Deck 1                                                    |
| +------------------------------------------------------+ |
| | Waveform Canvas (auto-scrolling, cursor centered)    | |
| | [section overlays + cursor line]                      | |
| +------------------------------------------------------+ |
| | Metadata Row                                          | |
| | Title | Artist | BPM | Key | Section | State | ...   | |
| +------------------------------------------------------+ |
+----------------------------------------------------------+
| Deck 2                                                    |
| +------------------------------------------------------+ |
| | Waveform Canvas                                       | |
| +------------------------------------------------------+ |
| | Metadata Row                                          | |
| +------------------------------------------------------+ |
+----------------------------------------------------------+
```

Each deck panel takes ~50% of the available vertical space (minus TopBar/Console). Full-width waveform with a compact metadata row below.

---

## Component Hierarchy

```
LiveDeckMonitorPage
  DeckPanel (x2, key=player_number)
    DeckWaveform
      WaveformCanvas (shared, with cursorPosition + auto-scroll)
    DeckMetadata
      MetadataRow (full diagnostic fields)
      SectionIndicator (current section label + progress bar)
    DeckEmptyState (when no track loaded or track unresolved)
```

### Component Responsibilities

| Component | Reusable? | Notes |
|-----------|-----------|-------|
| `LiveDeckMonitorPage` | No | Page shell. Reads `bridgeStore.players` for deck 1 and 2. |
| `DeckPanel` | Yes | Single deck container. Accepts player number, player state, resolved analysis. |
| `DeckWaveform` | No | Wraps `WaveformCanvas` with auto-scroll logic tied to cursor position. |
| `WaveformCanvas` | **Yes** | Shared from Analysis Viewer. Receives `cursorPosition` prop. |
| `DeckMetadata` | No | Full diagnostic metadata display for one deck. |
| `SectionIndicator` | Yes | Shows current section label + progress bar. Reusable in future contexts. |
| `DeckEmptyState` | No | Shown when deck has no track or track can't be resolved. |

---

## Data Flow

### Live State (WebSocket → bridgeStore → component)

```
bridge_status WS message
  → bridgeStore.players["1"] and players["2"]
    → LiveDeckMonitorPage reads both
      → DeckPanel receives per-deck state:
          - rekordbox_id, track_source_player, track_source_slot
          - bpm, pitch, playback_state, is_on_air
          - beat_within_bar
          - playback_position_ms (NEW)
```

### Track Resolution (composite key → fingerprint → TrackAnalysis)

When a deck's composite key `(track_source_player, track_source_slot, rekordbox_id)` changes (new track loaded):

1. `DeckPanel` detects change via `useEffect` on the composite key.
2. Calls `useResolveTrack(sourcePlayer, sourceSlot, rekordboxId)` — `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}`.
3. If resolved → gets `fingerprint`. Calls `useTrackAnalysis(fingerprint)` (shared hook from Analysis Viewer).
4. If not resolved → shows "Unknown track" state with rekordbox_id + source info visible.

This is fully automatic with graceful fallback. No user action required.

### Cursor Position

`playback_position_ms` arrives in each `bridge_status` update (frequency depends on bridge event rate, typically ~5-20Hz during playback). Converted to seconds and passed as `cursorPosition` to `WaveformCanvas`.

Between updates, the frontend does NOT interpolate — it renders the last known position. The update rate from beat-link is fast enough for a smooth visual at debugging fidelity. If this proves too jumpy, frontend-side interpolation (using BPM + last update timestamp) can be added as a follow-up.

### Auto-Scroll

`DeckWaveform` controls `viewStart`/`viewEnd` to keep the cursor centered. The visible window is ~10-15 seconds wide (configurable), auto-advancing as `playback_position_ms` updates. The user cannot manually zoom/scroll the Live Monitor waveform in v1 — it's always auto-following.

---

## Deck Metadata — Full Diagnostic

Displayed as a compact row below each deck's waveform:

### Primary Row (always visible)

| Field | Source | Format |
|-------|--------|--------|
| Title | `analysis.title` | Plain text, truncated with ellipsis |
| Artist | `analysis.artist` | Plain text, truncated with ellipsis |
| BPM (effective) | `player.bpm` | `128.00` — live from bridge |
| BPM (original) | `analysis.bpm` | `(orig: 126.00)` — from analysis |
| Pitch | `player.pitch` | `+2.3%` |
| Key | `analysis.features.key` | e.g., "Cm" |
| Playback State | `player.playback_state` | Badge: playing (green), paused (yellow), stopped (gray) |
| On Air | `player.is_on_air` | Green dot if true, gray if false |

### Secondary Row (diagnostic, smaller text)

| Field | Source | Format |
|-------|--------|--------|
| Current Section | Derived from cursor position + sections | "drop (bar 12/16, 75%)" |
| Section Confidence | Current section's confidence | Color-coded 0.00-1.00 |
| Section Source | Current section's source | Badge: "analysis" / "pioneer_enriched" |
| Fingerprint | `analysis.fingerprint` | First 12 chars, copy-on-click |
| rekordbox_id | `player.rekordbox_id` | Number |
| Source Player | `player.track_source_player` | "Player 1" |
| Source Slot | `player.track_source_slot` | Badge: "usb" / "sd" / "collection" |
| Data Source | `analysis.source` | Badge |
| Version | `analysis.version` | Number |
| Track Type | `player.track_type` | Badge |
| Beat | `player.beat_within_bar` | "Beat 3/4" |

### Section Progress Indicator

Below the metadata rows, a thin horizontal progress bar showing:
- Current section label (text, left-aligned)
- Progress through section (colored bar, 0-100%)
- Next section label (text, right-aligned, muted)

The progress is derived by mapping `playback_position_ms` against the current section's `start` and `end` times from the analysis.

---

## Deck Empty States

| State | Display |
|-------|---------|
| **No bridge connection** | Full deck area: "Bridge not connected" with muted StatusDot |
| **Bridge connected, no player data** | "Waiting for deck {N} data..." |
| **Player data, rekordbox_id = 0** | "No track loaded on Deck {N}" |
| **rekordbox_id present, resolution pending** | "Resolving track..." with spinner |
| **rekordbox_id present, not found in DB** | "Unknown track (rekordbox_id: 42001, source: Player 1 USB) — analyze this track to see waveform" |
| **Resolved, analysis loading** | Waveform skeleton + "Loading analysis..." |
| **Resolved, analysis in progress (on-demand)** | "Analyzing track... (~3-8s)" with progress spinner. Beat-reactive defaults active in Layer 2 (strobe on downbeat, color cycle per bar). See research Q3: hybrid data flow. |
| **Resolved, analysis has no waveform** | Metadata visible, waveform area: "No waveform data — re-analyze with waveform enabled" |

---

## Cursor Rendering

The playback cursor is a vertical line rendered on the `WaveformCanvas`:
- **Color:** White with slight glow (`rgba(255, 255, 255, 0.9)` main line, `rgba(255, 255, 255, 0.3)` 2px glow on each side).
- **Width:** 2px main line.
- **Full height** of the canvas.
- **Position:** Mapped from `cursorPosition` (seconds) to pixel X coordinate based on the current view window.

---

## Live Section Tracking

As `playback_position_ms` updates, derive the current section by finding which `Section` contains the current timestamp:

```typescript
function findCurrentSection(sections: Section[], positionSec: number): number | null {
  return sections.findIndex(s => positionSec >= s.start && positionSec < s.end);
}
```

The current section index is passed to `WaveformCanvas` as `highlightedSection` and to `DeckMetadata` for the section display. When the cursor crosses a section boundary, the highlight shifts automatically.

---

## Navigation & Routing

Already specified in the Analysis Viewer spec. Both pages are added together:

**Route:** `<Route path="live" element={<LiveDeckMonitorPage />} />` in `App.tsx`.
**Sidebar:** Top-level "Live Monitor" entry.

---

## Shared Dependencies with Analysis Viewer

| Shared Component/Hook | Defined In | Used By |
|----------------------|------------|---------|
| `WaveformCanvas` | `frontend/src/components/shared/WaveformCanvas.tsx` | Both |
| `useTrackAnalysis` | `frontend/src/api/tracks.ts` | Both |
| `SectionIndicator` | `frontend/src/components/shared/SectionIndicator.tsx` | Both (optional in Viewer) |
| `PlaceholderPanel` | `frontend/src/components/shared/PlaceholderPanel.tsx` | Viewer only |

Build order: **Analysis Viewer first**. The shared `WaveformCanvas` is built and tested there, then reused in the Live Deck Monitor.

---

## v1 Scope Constraints

### In Scope
- `LiveDeckMonitorPage` with 2 stacked deck panels
- Backend: `playback_position_ms`, `track_source_player`, `track_source_slot` added to bridge_status players dict
- Backend: `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}` endpoint
- Backend: `track_ids` table migration to composite primary key
- Auto-resolve composite key → fingerprint → TrackAnalysis
- Live waveform with auto-scrolling cursor
- Full diagnostic metadata per deck
- Live section tracking + section progress indicator
- All empty/error states for various deck conditions
- Contract updates (`docs/interfaces.md`, `docs/CONTRACTS.md`)

### Out of Scope
- Manual zoom/scroll on live waveform (auto-follow only in v1)
- More than 2 decks (future: up to 6)
- Frontend-side cursor interpolation between updates
- Audio playback or monitoring
- Tier 2 event overlays (M7)
- Mix analysis / alignment between decks
- Fader/crossfader state visualization
- Audio fingerprinting for track resolution (future — see `docs/FUTURE_AUDIO_FINGERPRINTING (1).md`)

---

## Design Decisions Summary

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|---------------------|
| 1 | Stacked vertical layout | Full-width waveforms. Natural for wide screens. Each deck gets maximum horizontal resolution. | Side-by-side (halves waveform width), shared timeline (too complex for v1) |
| 2 | Add `playback_position_ms` to backend | Accurate cursor requires real position data. beat_within_bar alone can't map to seconds without beatgrid interpolation on the FE. | Frontend interpolation from beats (drifts, complex), new high-freq WS stream (overkill) |
| 3 | Auto-resolve track, graceful fallback | Zero friction. If the track isn't in the DB, the deck still shows what it can (metadata from bridge). | Manual resolve button (unnecessary friction) |
| 4 | No manual zoom/scroll in v1 | Live monitoring is about following playback, not inspection. Analysis Viewer handles deep inspection. | Zoom/scroll (conflicts with auto-follow, confusing UX) |
| 5 | Full diagnostic metadata | This screen is for debugging. Engineers need fingerprint, rekordbox_id, confidence, source, etc. Clean version comes later. | Essential-only (insufficient for debugging), toggle (complexity) |
| 6 | No cursor interpolation in v1 | beat-link updates at ~5-20Hz during playback. At 10Hz, cursor moves every 100ms — smooth enough for debugging. Add interpolation if proven insufficient. | Interpolation (adds complexity, premature) |
| 7 | REST endpoint for track resolution | Clean separation: FE asks BE to resolve, BE uses its cache. Avoids exposing cache internals to FE. | Batch lookup (YAGNI), WS-based push (more complex) |
| 8 | Composite key `(source_player, source_slot, rekordbox_id)` for track resolution | `rekordbox_id` is per-USB auto-increment, NOT globally unique. Two USBs can have the same ID for different tracks. Research confirmed this is a real multi-USB scenario. | Bare `rekordbox_id` lookup (silent mismatches in multi-USB setups) |
| 9 | `track_ids` table migration to composite PK | Existing schema uses `rekordbox_id INTEGER PRIMARY KEY` which silently overwrites when a second USB has the same ID. Must be fixed before Live Monitor ships. | Leave broken (data corruption risk) |

---

## Edge Cases

| Edge Case | Expected Behavior |
|-----------|------------------|
| Track loaded on deck but not in SCUE DB | Show "Unknown track" state with rekordbox_id + source info. All bridge metadata (BPM, pitch, state) still visible. |
| Track swapped while analysis is loading | `useResolveTrack` query key includes full composite key — TanStack cancels the stale query automatically. |
| Two decks have same `rekordbox_id` (multi-USB) | Composite key disambiguates. Each deck resolves independently using its own `(source_player, source_slot, rekordbox_id)`. |
| `track_source_player` or `track_source_slot` missing/empty | Resolve endpoint returns 404. Show "Unknown track" state. Log warning for debugging. |
| `playback_position_ms` is null | Cursor not rendered. Waveform shows at default position (start). |
| Deck paused | Cursor stays at last position. Playback state badge shows "paused". |
| `rekordbox_id` is 0 (no track) | Show "No track loaded" empty state. Clear any previous analysis. |
| Bridge disconnects mid-playback | Cursor freezes at last known position. Bridge status indicators show disconnected. |
| Track has waveform but no sections | Waveform renders normally. Section indicator shows "No sections". |
| Very fast track swap (DJ hot-cueing) | Each rekordbox_id change triggers a new resolution. Previous resolution is cancelled. Brief flash of loading state is acceptable. |
| Player 3 or 4 data arrives | Ignored in v1 (only player 1 and 2 rendered). No error. |
| `playback_position_ms` jumps backwards (DJ scratching/cueing) | Cursor follows position directly. Auto-scroll adjusts. No smoothing. |
