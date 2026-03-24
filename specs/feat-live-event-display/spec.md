# Spec: Live Event Display

## Summary

A shared playback-context hook (`useActiveEvents`) and reusable display component
(`<LiveEventDisplay />`) that show what's happening at the current playback position:
active sections, point events as they fire, phrase position, and upcoming events.

Designed for reuse across the annotation page, live deck monitor, and analysis viewer.
Establishes a single source of truth for the "given time T + events + sections → what's
active now?" computation so each page doesn't reinvent it.

---

## Architectural Decision: Shared Hook, Not a New Store

**Decision:** Pure computation hook + shared component.

**Rationale:**
- Cursor position legitimately comes from different sources (bridge WebSocket for live
  decks, HTML audio for annotation, manual scrub for analysis viewer).
- Existing rule: "Zustand stores are independent — no store imports another store."
- The computation is cheap (O(log n) binary search on sorted arrays). Duplicating it
  across consumers is acceptable.
- No shared mutable state is needed — each consumer provides its own cursor time.

**Data Flow:**

```
1. PLAYBACK SOURCE (page provides cursor time)
   ├─ Live deck: bridgeStore.players[n].playback_position_ms / 1000
   ├─ Annotation: audioRef.current.currentTime
   └─ Analysis viewer: click/scrub position

2. useActiveEvents(currentTime, events, sections, beats, downbeats)
   └→ ActiveEventState {
        currentTime, activeSections, recentEvents, upcomingEvents, phrase
      }

3. PAGE-SPECIFIC ENRICHMENT (optional, per-page)
   ├─ Annotation: source badges (predicted/corrected/manual)
   ├─ Live deck: on-air status, deck identification
   └─ Analysis viewer: confidence scores

4. <LiveEventDisplay state={activeState} layout="horizontal|vertical" />
   └→ Section band + event flash indicators + phrase position + upcoming preview
```

---

## Types

### `ActiveEventState`

```typescript
interface ActiveEventState {
  currentTime: number;
  activeSections: Section[];         // sections where start <= currentTime < end
  recentEvents: FiredEvent[];        // events fired within recentWindow (default 300ms)
  upcomingEvents: EventPreview[];    // next N events after currentTime
  phrase: PhraseInfo | null;         // bar/phrase position from beatgrid
}
```

### `FiredEvent`

```typescript
interface FiredEvent {
  type: EventType;
  timestamp: number;
  duration?: number;
  age: number;                       // ms since event fired (for fade animation)
  source?: AnnotationSource;         // preserved from GroundTruthEvent if present
}
```

### `EventPreview`

```typescript
interface EventPreview {
  type: EventType;
  timestamp: number;
  timeUntil: number;                 // seconds until this event fires
}
```

### `PhraseInfo`

```typescript
interface PhraseInfo {
  barInPhrase: number;               // 0-indexed bar within current phrase
  phraseLength: number;              // total bars in phrase (typically 4, 8, 16)
  beatInBar: number;                 // 0-indexed beat within current bar
  beatsPerBar: number;               // typically 4
}
```

---

## Hook: `useActiveEvents`

**File:** `frontend/src/hooks/useActiveEvents.ts`

```typescript
function useActiveEvents(
  currentTime: number | null,
  events: Array<MusicalEvent | GroundTruthEvent>,
  sections: Section[],
  beats: number[],
  downbeats: number[],
  options?: {
    recentWindow?: number;           // ms, default 300
    previewCount?: number;           // default 5
  }
): ActiveEventState | null           // null when currentTime is null
```

**Behavior:**
- `activeSections`: filter sections where `start <= currentTime < end`
- `recentEvents`: binary search to find events where `0 <= (currentTime - timestamp) * 1000 < recentWindow`, sorted newest-first
- `upcomingEvents`: next N events after currentTime, sorted by timestamp
- `phrase`: derived from beats + downbeats arrays (find enclosing downbeat pair → bar index → phrase position)
- Returns `null` when `currentTime` is null (no playback)

**Performance:**
- Events are sorted by timestamp on first render (via `useMemo`)
- Binary search for recent/upcoming (not linear scan)
- `useMemo` on sections (stable unless sections array changes)
- Runs at cursor update rate (~60fps for audio, ~10-20fps for bridge) — must be fast

---

## Component: `<LiveEventDisplay />`

**File:** `frontend/src/components/shared/LiveEventDisplay.tsx`

### Props

```typescript
interface LiveEventDisplayProps {
  state: ActiveEventState | null;
  layout?: "horizontal" | "vertical";   // default "horizontal"
  className?: string;
}
```

### Visual Layout

**Horizontal (annotation page, below toolbar):**
```
┌──────────────┬────────────────────────────────┬──────────────┐
│ ■ DROP       │ ● KICK  ● KICK  ○ CLAP        │ next: SNARE  │
│ bar 3 of 8   │ (flash and fade)               │ in 0.3s      │
└──────────────┴────────────────────────────────┴──────────────┘
```

**Vertical (deck panel, sidebar):**
```
┌──────────────────┐
│ ■ DROP           │
│ bar 3 of 8       │
├──────────────────┤
│ ● KICK           │
│ ● KICK           │
│ ○ CLAP (fading)  │
├──────────────────┤
│ next: SNARE 0.3s │
└──────────────────┘
```

### Visual Details

- **Section band:** Background color matches section type (reuse existing section color map from WaveformCanvas). Shows section label + phrase position ("bar 3 of 8").
- **Event indicators:** Colored dots per event type (reuse annotation/event color map). Flash on at full opacity, fade out over 300ms via CSS `transition: opacity 0.3s`. Each event type gets its own dot that activates on fire.
- **Upcoming preview:** Shows next event type and countdown in seconds (updates every frame). Only shown when an event is within 2 seconds.
- **Empty state:** When `state` is null, show muted "No playback" text.

### Event Type Colors (match existing maps)

| Type | Color | Indicator |
|------|-------|-----------|
| kick | `#ef4444` (red-500) | filled circle |
| snare | `#f97316` (orange-500) | filled circle |
| clap | `#eab308` (yellow-500) | filled circle |
| hihat | `#a3a3a3` (neutral-400) | filled circle |
| riser | `#22c55e` (green-500) | upward arrow |
| faller | `#3b82f6` (blue-500) | downward arrow |
| stab | `#a855f7` (purple-500) | diamond |

### Section Colors (match WaveformCanvas)

| Label | Color |
|-------|-------|
| intro | `rgba(156, 163, 175, 0.3)` (gray) |
| verse | `rgba(59, 130, 246, 0.3)` (blue) |
| build | `rgba(234, 179, 8, 0.3)` (yellow) |
| drop | `rgba(239, 68, 68, 0.3)` (red) |
| breakdown | `rgba(168, 85, 247, 0.3)` (purple) |
| fakeout | `rgba(249, 115, 22, 0.3)` (orange) |
| outro | `rgba(156, 163, 175, 0.3)` (gray) |

---

## Integration Points

### AnnotationPage

```typescript
const activeState = useActiveEvents(
  cursorPosition,
  visibleAnnotations,       // annotations filtered by visibleTypes
  analysis?.sections ?? [],
  analysis?.beats ?? [],
  analysis?.downbeats ?? [],
);

// Below the toolbar, above the timeline:
<LiveEventDisplay state={activeState} layout="horizontal" />
```

### LiveDeckMonitorPage (DeckPanel)

```typescript
const activeState = useActiveEvents(
  player?.playback_position_ms != null ? player.playback_position_ms / 1000 : null,
  trackEvents,              // expanded detector events for this track
  analysis?.sections ?? [],
  analysis?.beats ?? [],
  analysis?.downbeats ?? [],
);

// Below DeckMetadata:
<LiveEventDisplay state={activeState} layout="vertical" />
```

---

## Event Visibility Toggles

Each event type can be toggled on/off to control whether it appears in the
`LiveEventDisplay` and on the waveform timeline. The toggle state is owned by
the page (local state) and passed as a filter — the hook receives pre-filtered events.

This is already implemented on the annotation page via `visibleTypes: Set<EventType>`.
The live deck monitor will add the same pattern.

---

## Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/types/activeEvents.ts` | Create | Type definitions |
| `frontend/src/hooks/useActiveEvents.ts` | Create | Shared computation hook |
| `frontend/src/components/shared/LiveEventDisplay.tsx` | Create | Shared display component |
| `frontend/src/pages/AnnotationPage.tsx` | Modify | Integrate hook + component |
| `frontend/src/components/live/DeckPanel.tsx` | Modify | Integrate hook + component |
| `docs/interfaces.md` | Modify | Document ActiveEventState as FE internal contract |

---

## Acceptance Criteria

1. `useActiveEvents` returns correct active sections at various cursor positions
2. Recent events appear and fade out within 300ms window
3. Upcoming events show countdown, disappear when they fire
4. Phrase position tracks correctly with beatgrid
5. Component renders in both horizontal and vertical layouts
6. Works on AnnotationPage with local audio playback
7. Works on LiveDeckMonitorPage with bridge WebSocket cursor
8. `npm run typecheck` passes
9. No performance regression (60fps cursor updates remain smooth)
