# Feature: Track Table Analysis Tier Columns

## Problem

The track table (used on Tracks page and as TrackPicker on Strata/Detector pages) shows no indication of what analysis tiers are available per track. Users must click into a track and check the Strata page to see if quick/standard/deep/live data exists. This makes it impossible to filter for "tracks with standard analysis" or "tracks with live data".

## Goal

Add per-tier analysis availability indicators to the track table, with filtering support, so users can quickly see and filter by what analysis work has been done.

## Current Architecture

### Two Table Implementations (not shared)

1. **TrackTable** (`frontend/src/components/tracks/TrackTable.tsx`, ~370 lines)
   - Used on Tracks page (`/tracks`)
   - Virtualized, supports folder view + flat view
   - Columns: Title, Artist, Folder, BPM, Key, Duration, Sections, Mood, Source, Analyzed, ID

2. **TrackPicker** (`frontend/src/components/analysis/TrackPicker.tsx`, ~250 lines)
   - Used on Strata page (single + multi-select) and Detector Tuning page
   - Simpler, max-height scrollable list
   - Columns: Title, Artist, BPM, Key, Duration, Sections

### Data Source

- `GET /api/tracks` returns track metadata from SQLite cache
- `GET /api/strata` returns `{tracks: [{fingerprint, tiers: {quick: [...sources], standard: [...]}}]}`
- No joined endpoint currently exists

## Proposed Changes

### Backend: Extend `GET /api/tracks` response

Add optional analysis availability fields to each track in the response:

```python
# New fields per track (all optional booleans, default None/absent)
has_quick: bool | None       # Has quick strata analysis
has_standard: bool | None    # Has standard strata analysis
has_deep: bool | None        # Has deep strata analysis
has_live_data: bool | None   # Has saved Pioneer live data (from feat-live-data-persistence)
```

**Implementation approach:**
- On server startup (or lazily on first request), scan the `strata/` directory to build a fingerprint → available tiers mapping
- Join this with the track list response
- Cache in memory, invalidate when new analysis completes
- The `has_live_data` field comes from the live data persistence feature (separate spec)

**Alternative:** A separate `GET /api/tracks/analysis-status` endpoint that returns `{fingerprint: {quick: bool, standard: bool, ...}}` — avoids changing the existing contract but requires a second fetch.

### Frontend: TypeScript types

```typescript
// Update TrackSummary in src/types/tracks.ts
interface TrackSummary {
  // ... existing fields ...
  has_quick?: boolean;
  has_standard?: boolean;
  has_deep?: boolean;
  has_live_data?: boolean;
}
```

### Frontend: Column additions

Add a compact "Analysis" column group to both tables:

```
| ... existing columns ... | Q | S | D | L |
```

Where Q/S/D/L are narrow columns (24-32px each) showing:
- Filled dot (green) = analysis available
- Empty dot (gray) = not available
- The column headers are abbreviated: Q(uick), S(tandard), D(eep), L(ive)

**Filtering:** TanStack Table already supports column filtering. Add a filter row or dropdown that lets users show only tracks matching a tier predicate (e.g., "has standard", "missing live data").

### Visual Design

```
TITLE          ARTIST    BPM   ... Q  S  D  L
─────────────────────────────────────────────
Track One      DJ Foo    128   ... ●  ●  ○  ○
Track Two      DJ Bar    140   ... ●  ○  ○  ●
Track Three    DJ Baz    136   ... ●  ●  ●  ●
```

Colors:
- Quick: blue dot (`text-blue-400`)
- Standard: indigo dot (`text-indigo-400`)
- Deep: purple dot (`text-purple-400`)
- Live: green dot (`text-green-400`)
- Missing: gray dot (`text-gray-700`)

## Affected Files

| File | Change |
|------|--------|
| `scue/api/tracks.py` | Add analysis availability to track list response |
| `frontend/src/types/tracks.ts` | Add optional tier boolean fields to TrackSummary |
| `frontend/src/components/tracks/TrackTable.tsx` | Add Q/S/D/L columns + filtering |
| `frontend/src/components/analysis/TrackPicker.tsx` | Add Q/S/D/L columns (optional — may not need filtering here) |

## Scope Boundaries

- **Owned paths:** `scue/api/tracks.py`, `frontend/src/types/tracks.ts`, `frontend/src/components/tracks/TrackTable.tsx`, `frontend/src/components/analysis/TrackPicker.tsx`
- **Dependencies:** Strata filesystem layout (read-only — just check for file existence)
- **NOT owned:** Strata engine, strata storage, strata API, bridge code
- **Prerequisite for `has_live_data`:** The live data persistence feature must land first (or this field can be added later as a follow-up)

## Acceptance Criteria

1. `GET /api/tracks` includes `has_quick`, `has_standard`, `has_deep` booleans per track
2. TrackTable on Tracks page shows Q/S/D/L dot columns
3. Columns are filterable (at minimum: click column header to filter "has this tier")
4. TrackPicker on Strata page shows the same indicators (filtering optional)
5. No performance regression on track list load (strata scan should be cached)

## Reference

- Strata storage layout: `strata/{fingerprint}.{tier}.analysis.json` per tier/source
- `StrataStore.list_tracks()` already returns per-fingerprint tier availability
- TanStack Table column filtering: https://tanstack.com/table/latest/docs/guide/column-filtering
