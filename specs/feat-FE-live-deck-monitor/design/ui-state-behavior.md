# UI State Behavior: Live Deck Monitor Page

> Maps system states to expected component display for every component in the
> Live Deck Monitor page. This is the source of truth for what each component
> should show in each state. Developers implement against it; Validators and
> QA Testers verify against it.

---

## States Reference

The Live Deck Monitor is a **real-time page** with dependencies on both the bridge
lifecycle (WebSocket, bridge status, Pioneer hardware) and data-fetching (track
resolution, analysis loading). It combines bridge states from the BLT disconnect
artifact with per-deck data states.

### Bridge States (from BLT ui-state-behavior-disconnect.md)

| # | State Key | Conditions | `dotStatus` |
|---|-----------|-----------|-------------|
| S1 | `running` (healthy) | `status=running`, devices non-empty, `isReceiving=true` | `connected` |
| S2 | `running` (no hardware) | `status=running`, devices empty, `isReceiving=false` | `connected` |
| S3 | `crashed` | `status=crashed` | `disconnected` |
| S4 | `starting` | `status=starting` | `disconnected` |
| S5 | `waiting_for_hardware` | `status=waiting_for_hardware` | `degraded` |
| S7 | WS disconnected | `wsConnected=false` | `disconnected` |

### Per-Deck States

Each deck (1 and 2) independently transitions through these states:

| # | State Key | Conditions |
|---|-----------|-----------|
| D1 | No player data | `players[N]` is undefined or absent |
| D2 | No track loaded | `players[N].rekordbox_id === 0` |
| D3 | Track loaded, resolution pending | `rekordbox_id > 0`, `useResolveTrack` query in flight |
| D4 | Track loaded, not found | `useResolveTrack` returned 404 |
| D5 | Track resolved, analysis loading | Fingerprint resolved, `useTrackAnalysis` query in flight |
| D6 | Track resolved, full data | Analysis loaded, waveform present |
| D7 | Track resolved, no waveform | Analysis loaded, `waveform === null` |
| D8 | Track resolved, no sections | Analysis loaded, `sections.length === 0` |

**D6, D7, D8 can combine** (e.g., analysis loaded with waveform but no sections).

### Compound: Bridge State x Deck State

Bridge states S3, S4, S5, S7 override per-deck display — the deck panels show
bridge-level messaging. Per-deck states (D1-D8) are only relevant when the bridge
is in S1 or S2.

---

## Component: LiveDeckMonitorPage (Page Shell)

| System State | Expected Display | Notes |
|---|---|---|
| S7: WS disconnected | Full page message: "Backend unreachable" with muted icon. Both deck panels hidden. | `text-gray-500 text-sm`, centered. Same pattern as bridge page WS-down state. |
| S3: crashed | Both deck panels show bridge-level empty state (see DeckPanel below). | Decks are still rendered but show crash-specific messaging. |
| S4: starting | Both deck panels show "Bridge starting..." with spinner. | `isStartingUp` is true. |
| S5: waiting_for_hardware | Both deck panels show "Waiting for hardware..." | |
| S1/S2: running | Both deck panels rendered. Each deck independently resolves its state (D1-D8). | Normal operation. |

### Layout

```
[Deck 1 Panel — ~50% height]
[Deck 2 Panel — ~50% height]
```

- Full-width, stacked vertically.
- Each panel: `flex flex-col` with waveform taking remaining space.
- Responsive: on very short viewports, panels may need scroll. No horizontal stacking.
- Container: `flex flex-col gap-4 h-full` (fills available height below TopBar).

### Page Styling

- Container: `flex flex-col gap-4` filling the main content area.
- No page title header (unlike Analysis Viewer) — maximize vertical space for waveforms.
- Page is thin (<50 lines). Reads `bridgeStore.players` for decks 1 and 2.

---

## Component: DeckPanel

A single deck container. Rendered twice (deck 1 and deck 2). Accepts player number,
player state from bridgeStore, and resolved analysis data.

### Bridge-Level States (override per-deck display)

| System State | Expected Display | Notes |
|---|---|---|
| S7: WS disconnected | "Backend unreachable" (centered, muted) | Page-level message may hide panels entirely; if panels render, this is the fallback. |
| S3: crashed | "Bridge crashed. Deck data will resume after restart." | `text-gray-500 text-sm`, centered in panel. |
| S4: starting | "Bridge starting..." with pulsing indicator | `animate-pulse`. |
| S5: waiting_for_hardware | "Waiting for Pioneer hardware..." | `text-gray-500 text-sm`. |

### Per-Deck States (when bridge is S1 or S2)

| System State | Expected Display | Notes |
|---|---|---|
| D1: No player data | "Waiting for Deck {N} data..." | `text-gray-500 text-sm`. Bridge is running but no player info for this deck number yet. |
| D2: No track loaded | "No track loaded on Deck {N}" | `text-gray-500 text-sm`. `rekordbox_id === 0`. |
| D3: Resolution pending | "Resolving track..." with spinner | Brief — resolve endpoint is fast (local DB lookup). |
| D4: Not found in DB | "Unknown track (rekordbox_id: {id}, source: Player {N} {slot}) — analyze this track to see waveform" | `text-gray-400 text-sm`. Show all available bridge metadata (BPM, pitch, state) even without analysis. |
| D5: Analysis loading | Waveform skeleton (`animate-pulse bg-gray-800 rounded h-32`) + "Loading analysis..." | Brief — JSON read is fast. |
| D6: Full data | `DeckWaveform` + `DeckMetadata` + `SectionIndicator` rendered with full data. | Normal happy path. Cursor moves with `playback_position_ms`. |
| D7: No waveform | Waveform area: "No waveform data — re-analyze with waveform enabled". Metadata row still renders. | Same message as Analysis Viewer. |
| D8: No sections | Waveform renders normally without section overlays. SectionIndicator shows "No sections". | Waveform and cursor still work. |

### Panel Container Styling

- Outer: `rounded border border-gray-800 bg-gray-950 p-3 flex flex-col`
- Header bar: `flex items-center justify-between mb-2`
  - Deck label: `text-xs font-semibold uppercase tracking-wider text-gray-500` — "DECK 1" / "DECK 2"
  - Playback state badge (when player data exists): `px-2 py-0.5 rounded text-xs`
    - playing: `bg-green-900/50 text-green-300`
    - paused: `bg-amber-900/50 text-amber-300`
    - stopped: `bg-gray-800 text-gray-400`
  - On-air indicator: small green dot if `is_on_air === true`, gray otherwise
- Empty states: centered in panel with `min-h-[120px] flex items-center justify-center`

---

## Component: DeckWaveform

Wraps `WaveformCanvas` with auto-scroll logic. Only rendered when analysis with
waveform is available (D6).

| System State | Expected Display | Notes |
|---|---|---|
| D6: Full data, playing | Waveform with cursor line auto-scrolling. View window (~10-15s) follows cursor. Section overlays visible. Current section highlighted. | `cursorPosition` updates at bridge update rate (~5-20Hz). |
| D6: Full data, paused | Waveform with cursor frozen at last position. View window static. | Cursor stays put. Playback state badge shows "paused". |
| D6: Full data, stopped | Waveform at default position (start). No cursor. | `playback_position_ms` is null when stopped. |
| Cursor jumps backwards (scratching) | Cursor follows position directly. Auto-scroll adjusts immediately. No smoothing. | DJ scratching/cueing produces rapid position changes. |

### Auto-Scroll Logic

`DeckWaveform` manages `viewStart`/`viewEnd` to keep the cursor centered:

```typescript
// Auto-scroll: center cursor in a ~12s window
const WINDOW_SECONDS = 12;
const half = WINDOW_SECONDS / 2;
const viewStart = Math.max(0, cursorSec - half);
const viewEnd = Math.min(duration, cursorSec + half);
```

- Recomputed on every `playback_position_ms` update.
- No user interaction (no zoom/scroll). `onViewChange` is NOT passed to `WaveformCanvas`.
- At track start (cursor < half window): window starts at 0, cursor is left-of-center.
- At track end (cursor > duration - half): window ends at duration, cursor is right-of-center.

### WaveformCanvas Props (Live Deck Monitor Context)

```typescript
<WaveformCanvas
  waveform={analysis.waveform}
  sections={analysis.sections}
  duration={analysis.duration}
  viewStart={viewStart}
  viewEnd={viewEnd}
  cursorPosition={cursorSec}
  highlightedSection={currentSectionIndex}
  selectedSection={null}
  // No onSectionHover, onSectionClick, onViewChange, energyCurve
/>
```

- `energyCurve` is NOT passed — not useful in live monitoring context.
- `highlightedSection` is set to the current section (derived from cursor position).
- `selectedSection` is always null — no manual selection in live mode.
- No interaction callbacks — the canvas is display-only.

### Canvas Height

- `h-32` (128px) per deck — more compact than Analysis Viewer's `h-48` to fit two decks on screen.

---

## Component: DeckMetadata

Full diagnostic metadata row below each deck's waveform. Only rendered when player
data exists (D1 is false).

### When Track Is Resolved (D6/D7/D8)

Two rows of metadata:

**Primary Row:**

| Field | Source | Format | Styling |
|---|---|---|---|
| Title | `analysis.title` | Truncated with `truncate` | `text-white font-medium text-sm` |
| Artist | `analysis.artist` | Truncated with `truncate` | `text-gray-300 text-sm` |
| BPM (effective) | `player.bpm` | `128.00` | `font-mono text-sm text-gray-300` |
| BPM (original) | `analysis.bpm` | `(orig: 126.00)` | `font-mono text-xs text-gray-500` |
| Pitch | `player.pitch` | `+2.3%` | `font-mono text-sm`. Green if positive, red if negative, gray if 0. |
| Key | `analysis.features.key` | e.g., "Cm" | `text-gray-300 text-sm` |
| State | `player.playback_state` | Badge | Same badge styles as DeckPanel header |
| On Air | `player.is_on_air` | Dot | Green if true, gray if false |

**Secondary Row (diagnostic, smaller):**

| Field | Source | Format | Styling |
|---|---|---|---|
| Current Section | Derived | "drop (bar 12/16, 75%)" | `text-xs text-gray-400`. Section label color-coded. |
| Confidence | Current section | `0.85` | Color-coded (red/amber/green) `text-xs` |
| Source | Current section | Badge | `text-[10px]` badge |
| Fingerprint | `analysis.fingerprint` | First 12 chars, copy-on-click | `font-mono text-xs text-gray-500 cursor-pointer hover:text-gray-300` |
| rekordbox_id | `player.rekordbox_id` | Number | `font-mono text-xs text-gray-500` |
| Source Player | `player.track_source_player` | "Player 1" | `text-xs text-gray-500` |
| Source Slot | `player.track_source_slot` | Badge | `text-[10px]` badge |
| Data Source | `analysis.source` | Badge | `text-[10px]` badge |
| Beat | `player.beat_within_bar` | "Beat 3/4" | `font-mono text-xs text-gray-400` |

### When Track Is NOT Resolved (D4)

Show bridge-only metadata in a single row:

| Field | Source | Format |
|---|---|---|
| BPM | `player.bpm` | `128.00` |
| Pitch | `player.pitch` | `+2.3%` |
| State | `player.playback_state` | Badge |
| On Air | `player.is_on_air` | Dot |
| rekordbox_id | `player.rekordbox_id` | Number |
| Beat | `player.beat_within_bar` | "Beat 3/4" |

All other fields are unavailable without analysis data.

### Layout

- Primary row: `flex items-center gap-3 text-sm`
- Secondary row: `flex items-center gap-3 mt-1`
- Container: `px-2 py-1.5`

---

## Component: SectionIndicator (Shared)

Thin horizontal bar below metadata showing current section progress. Only rendered
when track has sections and cursor is in a section.

| System State | Expected Display | Notes |
|---|---|---|
| D6: Track with sections, cursor in section | Current section label badge (left), progress bar (0-100%, section-colored), next section label (right, muted) | Progress = `(cursor - section.start) / (section.end - section.start)` |
| D6: Cursor between sections | "Between sections" (muted), no progress bar, next section label (right) | Edge case if section coverage has gaps |
| D8: No sections | "No sections" | `text-gray-500 text-xs` |
| D2/D4: No track or unresolved | Not rendered | DeckEmptyState shown instead |

### Progress Bar Styling

- Track (background): `h-1 rounded-full bg-gray-800 flex-1`
- Fill: `h-1 rounded-full` with section-color fill (use same color map as SectionList badges)
- Container: `flex items-center gap-2 h-6 px-2`

### Current Section Derivation

```typescript
function findCurrentSection(sections: Section[], positionSec: number): number {
  return sections.findIndex(s => positionSec >= s.start && positionSec < s.end);
}
```

Returns -1 if cursor is not in any section (gap or before first / after last).

### Next Section Derivation

If current section index is `i`, next section is `sections[i + 1]` (if exists).
If cursor is between sections, next section is the first section where `start > positionSec`.

---

## Component: DeckEmptyState

Shown when deck cannot display waveform + metadata. Replaces the entire deck
content area.

| System State | Expected Display | Notes |
|---|---|---|
| D1: No player data | "Waiting for Deck {N} data..." | Pulsing opacity animation |
| D2: No track loaded | "No track loaded on Deck {N}" | Static muted text |
| D3: Resolution pending | "Resolving track..." with spinner | Brief state |
| D4: Not found | Full line: "Unknown track (rekordbox_id: {id}, source: Player {srcPlayer} {srcSlot}) — analyze this track to see waveform" | Show what we know. Bridge metadata still shown in DeckMetadata. |
| D5: Analysis loading | Waveform skeleton + "Loading analysis..." | Skeleton matches waveform dimensions |
| D7: No waveform | "No waveform data — re-analyze with waveform enabled" | Metadata and SectionIndicator still render |

### Styling

- Container: `min-h-[120px] flex items-center justify-center`
- Text: `text-gray-500 text-sm`
- Spinner: `animate-spin h-4 w-4 border-2 border-gray-500 border-t-transparent rounded-full` inline before text

---

## Compound States

### S1 + D6 on both decks (Normal Live Operation)

Both decks show waveforms with cursors auto-scrolling. Each deck independently
tracks its current section and highlights it. This is the primary use case.

### S3 (crashed) + deck had data

When bridge crashes, `players` dict is cleared (per BLT TASK-001 `BridgeAdapter.clear()`).
Both decks transition to the bridge-level crash message. Previous analysis data
(from `useTrackAnalysis` cache) is still in TanStack Query cache but should NOT be
displayed — the bridge crash means playback state is unknown. Show crash message only.

### Track swap during playback (D6 → D3 → D6)

DJ loads a new track on a deck. `rekordbox_id` changes (with new `track_source_player`/`track_source_slot`).
1. `useResolveTrack` query key changes → previous query cancelled.
2. Brief D3 state (resolving). Waveform disappears, skeleton shown.
3. D5 (analysis loading) or D4 (unknown track).
4. D6 (full data) — new waveform appears with cursor.

Clean cut — no cross-fade or stale data. The resolve + analysis fetch is fast
(two local lookups), so the transition is near-instant.

### Two decks, same rekordbox_id from different USBs

Composite key `(track_source_player, track_source_slot, rekordbox_id)` disambiguates.
Each deck resolves independently. No conflict.

### playback_position_ms is null

Cursor is not rendered. Waveform shows at default position (full track, no
auto-scroll). This happens when the deck is stopped or position is unknown.
Auto-scroll logic guards: `if (cursorSec == null) return` (don't update view).

### Bridge reconnects while tracks are loaded

After bridge restart (S3/S4 → S1), `players` dict repopulates from fresh
`bridge_status` messages. Decks re-enter D3 (resolution) with the new composite
key. TanStack Query may serve the analysis from cache (same fingerprint), making
the transition near-instant.

---

## Transition Narrative: Typical Live Set Flow

1. User navigates to `/live`. Page shows two empty deck panels: "Waiting for Deck 1/2 data..."
2. Bridge is running, Pioneer hardware connected. Player data arrives via WebSocket.
3. DJ loads a track on Deck 1. `rekordbox_id` changes from 0 to a real ID.
4. Deck 1 transitions: D2 → D3 (resolving) → D5 (analysis loading) → D6 (full data).
5. Waveform appears. Cursor begins tracking `playback_position_ms`. Auto-scroll follows.
6. DJ presses play. Cursor moves. Current section highlights on waveform. SectionIndicator shows progress.
7. DJ loads a track on Deck 2. Same flow independently.
8. Both decks now show live waveforms side by side (stacked vertically).
9. DJ swaps a track on Deck 1. Brief flash of D3/D5, then new waveform appears.
10. Pioneer hardware disconnects. Bridge crashes. Both decks show crash message.
11. Hardware reconnects. Bridge restarts. Decks re-resolve and restore.

---

## New Type Changes Required (Pre-requisite)

These are backend contract changes that must land before the Live Deck Monitor
frontend can be built. They are documented in the spec but listed here for
Developer reference.

### PlayerInfo Type Extension

```typescript
// frontend/src/types/bridge.ts — add to PlayerInfo
export interface PlayerInfo {
  bpm: number;
  pitch: number;
  playback_state: string;
  is_on_air: boolean;
  rekordbox_id: number;
  beat_within_bar: number;
  track_type: string;
  // NEW fields:
  playback_position_ms: number | null;
  track_source_player: number;
  track_source_slot: string;  // "usb" | "sd" | "cd" | "collection"
}
```

### New Hook

```typescript
// frontend/src/api/tracks.ts — new hook
export function useResolveTrack(
  sourcePlayer: number | null,
  sourceSlot: string | null,
  rekordboxId: number | null,
) {
  return useQuery<{ fingerprint: string; title: string; artist: string }>({
    queryKey: ["resolve-track", sourcePlayer, sourceSlot, rekordboxId],
    queryFn: () =>
      apiFetch(`/tracks/resolve/${sourcePlayer}/${sourceSlot}/${rekordboxId}`),
    enabled: sourcePlayer != null && sourceSlot != null && rekordboxId != null && rekordboxId > 0,
    retry: false,  // 404 means unknown track, don't retry
  });
}
```

---

## Follow-Up Items (Out of Scope)

1. **Frontend cursor interpolation:** If 5-20Hz update rate proves too jumpy, add
   client-side interpolation using BPM + last update timestamp. Deferred per spec.

2. **More than 2 decks:** v1 renders only players 1 and 2. Player 3/4+ data is
   ignored (no error). Future: configurable deck count up to 6.

3. **Manual zoom/scroll on live waveform:** Conflicts with auto-follow. Could be
   a toggle ("follow mode" on/off). Deferred.

4. **Mix alignment visualization:** Show both decks' beatgrids aligned. Requires
   significant additional work. Deferred.
