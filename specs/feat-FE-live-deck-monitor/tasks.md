# Tasks: FE-Live-Deck-Monitor

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

**Research applied:** Composite key `(source_player, source_slot, rekordbox_id)` required for multi-USB safety. See `research/dlp-track-id-reliability.md` and `research/research-findings-bridge-data-strategy.md`.

## Dependency Graph

```
TASK-001 (Backend: playback_position_ms + source fields in bridge + Java)
  |
  +---> TASK-003 (FE types + bridgeStore update)
  |       |
  |       +---> TASK-005 (DeckWaveform — auto-scroll + cursor)
  |       |       |
  |       |       +---> TASK-007 (Page assembly + routing)
  |       |
  |       +---> TASK-006 (DeckMetadata + SectionIndicator)
  |               |
  |               +---> TASK-007 (Page assembly)
  |
TASK-002 (Backend: composite key migration + resolve endpoint)
  |
  +---> TASK-004 (FE: useResolveTrack hook + auto-resolve logic)
          |
          +---> TASK-007 (Page assembly)

[Analysis Viewer TASK-002: WaveformCanvas] ---> TASK-005 (reuses shared component)
```

**Critical path:** TASK-001 (backend) → TASK-003 (FE types) → TASK-005 (deck waveform) → TASK-007 (assembly).

**Parallel tracks:**
- Track A: TASK-001 → TASK-003 → TASK-005 (position pipeline)
- Track B: TASK-002 → TASK-004 (track resolution pipeline)
- Track C: TASK-006 (metadata, parallel with A and B after TASK-003)
- TASK-007 is final assembly (depends on A, B, C).

**External dependency:** Analysis Viewer TASK-002 (WaveformCanvas) must be complete before this feature's TASK-005.

## Tasks

### TASK-001: Backend — add playback_position_ms + forward source fields through bridge pipeline
- **Layer:** Backend (Layer 0 bridge: Java + Python) + Docs
- **Estimated effort:** 45 min
- **Depends on:** none
- **Interface Scope:** END_TO_END — Java emits new field, Python forwards it, contract docs updated. Combined because all three new fields are additive with `null`/absent-safe defaults; no existing consumer breaks.
- **QA Required:** YES — live hardware verification of new fields in bridge_status WS payload
- **State Behavior:** N/A (backend only)
- **Scope:**
  - `bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java` (modify — extract `status.getPlaybackPosition()`)
  - `bridge-java/src/main/java/com/scue/bridge/MessageEmitter.java` (modify — add `playbackPositionMs` param + payload field)
  - `scue/bridge/messages.py` (modify — add `playback_position_ms` to `PlayerStatusPayload`)
  - `scue/bridge/manager.py` (modify — include `playback_position_ms`, `track_source_player`, `track_source_slot` in `to_status_dict()` player output at lines 688-699)
  - `docs/interfaces.md` (modify — update bridge_status player schema)
  - `docs/CONTRACTS.md` (modify — note contract addition)
- **Inputs:**
  - beat-link `CdjStatus.getPlaybackPosition()` returns milliseconds from track start (long, -1 when unknown)
  - `track_source_player` and `track_source_slot` already parsed in `messages.py:PlayerStatusPayload` (lines 85-86) and emitted from Java (lines 543-546, 118-119) — they just need to be added to `to_status_dict()`
  - Current `to_status_dict()` in `manager.py` (lines 688-699)
- **Outputs:**
  - Java: `playback_position_ms` extracted and emitted in `player_status` message payload
  - Python: `playback_position_ms` field (float | None) added to `PlayerStatusPayload`
  - Python: `playback_position_ms`, `track_source_player`, `track_source_slot` all included in `bridge_status` WS message players dict
  - `playback_position_ms` is `null` when position is unknown (-1 from Java, or no track loaded)
  - Contract docs updated
- **Acceptance Criteria:**
  - [ ] Java bridge emits `playback_position_ms` in player_status JSON payload
  - [ ] Java bridge emits `null` for playback_position_ms when `getPlaybackPosition()` returns -1
  - [ ] `PlayerStatusPayload` dataclass includes `playback_position_ms: float | None = None`
  - [ ] `bridge_status` WS message player dict includes `playback_position_ms`, `track_source_player`, `track_source_slot`
  - [ ] `docs/interfaces.md` updated with all three new fields in player schema
  - [ ] `docs/CONTRACTS.md` updated with contract change note
  - [ ] Existing bridge tests pass (no regressions)
  - [ ] New test: verify `playback_position_ms` appears in player status dict
  - [ ] New test: verify `track_source_player` and `track_source_slot` appear in player status dict
- **Context files:**
  - `bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java` — `handleCdjStatus()` at line 534
  - `bridge-java/src/main/java/com/scue/bridge/MessageEmitter.java` — `emitPlayerStatus()` at line 106
  - `scue/bridge/messages.py` — `PlayerStatusPayload` at line 77
  - `scue/bridge/manager.py` — `to_status_dict()` player dict at line 688
  - `docs/interfaces.md` — current bridge_status schema
  - `specs/feat-FE-live-deck-monitor/spec.md` — Backend Contract Change section
  - `skills/contract-integrity.md`
- **Note:** The bridge JAR must be rebuilt after Java changes. Build with `cd bridge-java && ./gradlew shadowJar` and copy to `lib/beat-link-bridge.jar`. See `bridge-java/README.md`.
- **Status:** [ ] Not started

### TASK-002: Backend — composite key migration + resolve endpoint
- **Layer:** Backend (Layer 1 storage + API)
- **Estimated effort:** 40 min
- **Depends on:** none
- **Interface Scope:** PRODUCER — defines new REST endpoint and changes internal storage signatures. No contract doc update needed (REST endpoint is new, not a modification of an existing contract in `docs/interfaces.md`).
- **QA Required:** YES — verify composite key correctness and endpoint behavior with multi-USB scenarios
- **State Behavior:** N/A (backend only)
- **Scope:**
  - `scue/layer1/storage.py` (modify — migrate `track_ids` table to composite PK, update `lookup_fingerprint()` and `link_rekordbox_id()`)
  - `scue/api/tracks.py` (modify — add `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}` endpoint)
- **Research context:** `rekordbox_id` is a per-USB auto-increment key, NOT globally unique. Two USBs can have the same `rekordbox_id` for different tracks. The current `track_ids` table uses bare `rekordbox_id INTEGER PRIMARY KEY` which silently overwrites in multi-USB setups. See `research/dlp-track-id-reliability.md`.
- **Inputs:**
  - Current `track_ids` table: `rekordbox_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, first_seen REAL NOT NULL`
  - Current `lookup_fingerprint(rekordbox_id)` at storage.py:284
  - Current `link_rekordbox_id(rekordbox_id, fingerprint)` at storage.py:293
- **Outputs:**
  - **Schema migration:** `track_ids` table with `PRIMARY KEY (source_player, source_slot, rekordbox_id)` and columns `source_player INTEGER`, `source_slot TEXT`, `rekordbox_id INTEGER`, `fingerprint TEXT NOT NULL`, `first_seen REAL NOT NULL`
  - **Migration strategy:** Drop and recreate (SQLite is a derived cache, not source of truth). Old mappings are rebuilt on next USB scan.
  - `lookup_fingerprint(source_player, source_slot, rekordbox_id)` — updated signature
  - `link_rekordbox_id(source_player, source_slot, rekordbox_id, fingerprint)` — updated signature
  - `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}` endpoint:
    - Returns `{ "fingerprint": "abc...", "title": "...", "artist": "..." }` on success
    - Returns 404 if no link exists
    - Route defined BEFORE `/{fingerprint}` catch-all
- **Acceptance Criteria:**
  - [ ] `track_ids` table uses composite primary key `(source_player, source_slot, rekordbox_id)`
  - [ ] `lookup_fingerprint(1, "usb", 42001)` returns fingerprint when linked
  - [ ] `lookup_fingerprint(1, "usb", 42001)` returns None when not linked
  - [ ] `link_rekordbox_id(1, "usb", 42001, "abc...")` inserts/updates correctly
  - [ ] Two different composite keys with same `rekordbox_id` can coexist (multi-USB test)
  - [ ] `GET /api/tracks/resolve/1/usb/42001` returns fingerprint + title + artist when linked
  - [ ] `GET /api/tracks/resolve/1/usb/99999` returns 404 when no link exists
  - [ ] Endpoint registered BEFORE `/{fingerprint}` catch-all
  - [ ] All callers of `lookup_fingerprint` and `link_rekordbox_id` updated (check `usb_scanner.py`)
  - [ ] Existing tests pass (no regressions)
  - [ ] New test: composite key lookup works
  - [ ] New test: same rekordbox_id on different source_player/slot returns different fingerprints
  - [ ] New test: resolve endpoint returns correct data
  - [ ] New test: resolve endpoint returns 404 for unknown composite key
- **Context files:**
  - `scue/layer1/storage.py` — `track_ids` table creation at line 165, `lookup_fingerprint()` at line 284, `link_rekordbox_id()` at line 293
  - `scue/api/tracks.py` — existing endpoints
  - `scue/layer1/usb_scanner.py` — calls `link_rekordbox_id()` (needs source_player + source_slot params added)
  - `research/dlp-track-id-reliability.md` — full research on why composite key is needed
  - `specs/feat-FE-live-deck-monitor/spec.md` — New REST Endpoint section
- **Status:** [ ] Not started

### TASK-003: Frontend types + bridgeStore update for new player fields
- **Layer:** Frontend-State
- **Estimated effort:** 15 min
- **Depends on:** TASK-001 (backend must emit the fields)
- **Interface Scope:** CONSUMER — adds new fields to `PlayerInfo` TypeScript type to match backend contract from TASK-001.
- **QA Required:** NO — type-only change verified by typecheck, no runtime behavior change
- **State Behavior:** N/A (type plumbing only)
- **Scope:**
  - `frontend/src/types/bridge.ts` (modify — add `playback_position_ms`, `track_source_player`, `track_source_slot` to `PlayerInfo`)
  - `frontend/src/stores/bridgeStore.ts` (verify fields flow through — likely no change needed since store uses raw payload)
- **Inputs:**
  - Updated `bridge_status` player schema from TASK-001
  - Current `PlayerInfo` type at bridge.ts:68-76
- **Outputs:**
  - `playback_position_ms: number | null` added to `PlayerInfo`
  - `track_source_player: number` added to `PlayerInfo`
  - `track_source_slot: string` added to `PlayerInfo`
  - Verified that bridgeStore correctly passes all fields from WS message to store state
- **Acceptance Criteria:**
  - [ ] `PlayerInfo` type includes all three new fields
  - [ ] `bridgeStore.players["1"].playback_position_ms` reflects the value from WS messages
  - [ ] `bridgeStore.players["1"].track_source_player` reflects the value from WS messages
  - [ ] `bridgeStore.players["1"].track_source_slot` reflects the value from WS messages
  - [ ] TypeScript compilation passes (`npm run typecheck`)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `frontend/src/types/bridge.ts` — `PlayerInfo` type at line 68
  - `frontend/src/stores/bridgeStore.ts` — player state handling
  - `docs/interfaces.md` — bridge_status player schema (verify FE type matches)
  - `skills/contract-integrity.md`
- **Status:** [ ] Not started

### TASK-004: Frontend — useResolveTrack hook (composite key)
- **Layer:** Frontend-State
- **Estimated effort:** 20 min
- **Depends on:** TASK-002 (backend endpoint must exist)
- **Interface Scope:** CONSUMER — consumes the resolve REST endpoint from TASK-002.
- **QA Required:** NO — hook tested via integration in TASK-007; unit test coverage in acceptance criteria
- **State Behavior:** N/A (data-fetching hook only)
- **Scope:**
  - `frontend/src/api/tracks.ts` (modify — add `useResolveTrack` hook)
- **Inputs:**
  - New `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}` endpoint
  - `apiFetch` from `api/client.ts`
- **Outputs:**
  - `useResolveTrack(sourcePlayer: number, sourceSlot: string, rekordboxId: number | null)` TanStack Query hook
  - Returns `{ fingerprint, title, artist }` or undefined
  - `enabled` when `rekordboxId` is non-null and > 0
  - Query key includes all three fields so switching tracks/USBs auto-cancels stale queries
- **Acceptance Criteria:**
  - [ ] `useResolveTrack(1, "usb", 42001)` fetches `GET /api/tracks/resolve/1/usb/42001`
  - [ ] `useResolveTrack(1, "usb", null)` does not fire a request
  - [ ] `useResolveTrack(1, "usb", 0)` does not fire a request
  - [ ] Changing any of the three params auto-cancels the previous request
  - [ ] Returns `{ fingerprint, title, artist }` on success
  - [ ] Returns `error` on 404 (track not in DB)
  - [ ] TypeScript compilation passes
  - [ ] All pre-existing tests pass
- **Context files:**
  - `frontend/src/api/tracks.ts` — existing hook patterns, `useTrackAnalysis` from Analysis Viewer
  - `frontend/src/api/client.ts` — `apiFetch`
- **Status:** [ ] Not started

### TASK-005: DeckWaveform — auto-scroll waveform with live cursor
- **Layer:** Frontend-UI
- **Estimated effort:** 30 min
- **Depends on:** TASK-003, Analysis Viewer TASK-002 (WaveformCanvas)
- **Interface Scope:** NONE — internal component, no contract boundary.
- **QA Required:** NO — visual component verified by page-level QA in TASK-007
- **State Behavior:** `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — DeckWaveform section
- **Scope:**
  - `frontend/src/components/live/DeckWaveform.tsx` (create)
- **Inputs:**
  - Shared `WaveformCanvas` component
  - `playback_position_ms` from bridgeStore (via TASK-003)
  - `TrackAnalysis` with waveform + sections
- **Outputs:**
  - `DeckWaveform` component wrapping `WaveformCanvas` with:
    - Auto-scroll: visible window (~10-15 seconds) centered on cursor position
    - `cursorPosition` prop passed to WaveformCanvas (converted from ms to seconds)
    - Section highlighting: automatically highlights the section containing the cursor
    - No manual zoom/scroll in v1 (auto-follow only)
- **Acceptance Criteria:**
  - [ ] Waveform renders with `WaveformCanvas` using the track's `RGBWaveform` data
  - [ ] Cursor line tracks `playback_position_ms` (converted to seconds)
  - [ ] Visible window auto-scrolls to keep cursor approximately centered
  - [ ] Window width is ~10-15 seconds of track time
  - [ ] Current section is automatically highlighted on the waveform
  - [ ] No manual zoom/scroll interaction (mouse events don't pan/zoom)
  - [ ] Component handles `null` cursorPosition gracefully (no cursor, waveform at start)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-live-deck-monitor/spec.md` — Auto-Scroll, Cursor Rendering sections
  - `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — DeckWaveform states
  - `frontend/src/components/shared/WaveformCanvas.tsx` — shared component
- **Status:** [ ] Not started

### TASK-006: DeckMetadata + SectionIndicator components
- **Layer:** Frontend-UI
- **Estimated effort:** 30 min
- **Depends on:** TASK-003 (needs new PlayerInfo fields)
- **Interface Scope:** NONE — internal UI components, no contract boundary.
- **QA Required:** NO — visual components verified by page-level QA in TASK-007
- **State Behavior:** `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — DeckMetadata and SectionIndicator sections
- **Scope:**
  - `frontend/src/components/live/DeckMetadata.tsx` (create)
  - `frontend/src/components/shared/SectionIndicator.tsx` (create)
- **Inputs:**
  - `PlayerInfo` type (with `playback_position_ms`, `track_source_player`, `track_source_slot`)
  - `TrackAnalysis` type
  - Metadata fields from spec (full diagnostic)
- **Outputs:**
  - `DeckMetadata` component: two-row layout
    - Primary row: title, artist, BPM (effective + original), pitch %, key, playback state badge, on-air indicator
    - Secondary row (smaller, diagnostic): current section info, confidence, source, fingerprint (truncated, copy-on-click), rekordbox_id, source player, source slot, data source, version, track type, beat position
  - `SectionIndicator` component: thin progress bar showing current section label, progress %, next section label
  - Section derivation: map `playback_position_ms` to current section from analysis sections
- **Acceptance Criteria:**
  - [ ] Primary row shows: title, artist, effective BPM, original BPM, pitch %, key, playback state badge, on-air dot
  - [ ] Playback state badge: green (playing), yellow (paused), gray (stopped)
  - [ ] On-air: green dot if true, gray if false
  - [ ] Secondary row shows: current section info, confidence (color-coded), source badge, fingerprint (truncated), rekordbox_id, source player, source slot badge, data source, version, track type, beat position
  - [ ] Fingerprint copy-on-click works
  - [ ] `SectionIndicator` shows current section label, progress bar, next section label
  - [ ] Section progress derived correctly from cursor position vs section start/end
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-live-deck-monitor/spec.md` — Deck Metadata, Section Progress Indicator sections
  - `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — DeckMetadata and SectionIndicator states
  - `frontend/src/types/bridge.ts` — `PlayerInfo`
  - `frontend/src/types/track.ts` — `TrackAnalysis`, `Section`
- **Status:** [ ] Not started

### TASK-007: Page assembly — LiveDeckMonitorPage + DeckPanel + empty states + routing
- **Layer:** Frontend-UI
- **Estimated effort:** 30 min
- **Depends on:** TASK-004, TASK-005, TASK-006
- **Interface Scope:** NONE — internal page assembly, no contract boundary.
- **QA Required:** YES — full page-level verification of all deck states (D1-D8), bridge states (S1-S7), compound states, and routing
- **State Behavior:** `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — LiveDeckMonitorPage, DeckPanel, DeckEmptyState, compound states sections
- **Scope:**
  - `frontend/src/pages/LiveDeckMonitorPage.tsx` (create)
  - `frontend/src/components/live/DeckPanel.tsx` (create)
  - `frontend/src/components/live/DeckEmptyState.tsx` (create)
  - `frontend/src/App.tsx` (modify — add route, if not done in Analysis Viewer TASK-008)
- **Inputs:**
  - `bridgeStore.players` for deck 1 and 2 state
  - `useResolveTrack` hook for composite key → fingerprint
  - `useTrackAnalysis` hook for fingerprint → full analysis
  - All deck sub-components (DeckWaveform, DeckMetadata)
  - Empty state specs
- **Outputs:**
  - `LiveDeckMonitorPage`: reads `bridgeStore.players["1"]` and `bridgeStore.players["2"]`, renders two `DeckPanel`s stacked vertically
  - `DeckPanel`: single deck container. Orchestrates:
    1. Reads player state from props (including `track_source_player`, `track_source_slot`, `rekordbox_id`)
    2. Auto-resolves via `useResolveTrack(sourcePlayer, sourceSlot, rekordboxId)`
    3. Fetches `TrackAnalysis` via `useTrackAnalysis(fingerprint)`
    4. Renders `DeckWaveform` + `DeckMetadata` when data available
    5. Renders `DeckEmptyState` for all degraded states
  - `DeckEmptyState`: renders appropriate message for each empty state (no bridge, no player, no track, resolving, unknown with source info, loading, analyzing, no waveform)
  - Route: `/live` → `LiveDeckMonitorPage`
  - Each deck takes ~50% vertical space
- **Acceptance Criteria:**
  - [ ] `/live` route renders `LiveDeckMonitorPage`
  - [ ] Two deck panels rendered, stacked vertically
  - [ ] Each deck panel shows waveform + metadata when track is loaded and resolved
  - [ ] Composite key change `(source_player, source_slot, rekordbox_id)` triggers auto-resolve → auto-fetch of new TrackAnalysis
  - [ ] "No bridge connection" state when bridge is disconnected
  - [ ] "Waiting for deck N data" when player data absent
  - [ ] "No track loaded" when rekordbox_id is 0
  - [ ] "Resolving track..." with spinner during resolution
  - [ ] "Unknown track (rekordbox_id: X, source: Player N SLOT)" when resolution returns 404
  - [ ] "Loading analysis..." skeleton during TrackAnalysis fetch
  - [ ] "Analyzing track... (~3-8s)" state for on-demand analysis
  - [ ] "No waveform data" when analysis has no waveform
  - [ ] Player 3/4 data ignored (only decks 1 and 2 rendered)
  - [ ] Page is thin (<100 lines per project convention)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-live-deck-monitor/spec.md` — Page Layout, Data Flow, Empty States sections
  - `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — all component state tables
  - `frontend/src/stores/bridgeStore.ts` — players state
  - `frontend/src/pages/AnalysisViewerPage.tsx` — thin page pattern
  - `frontend/CLAUDE.md` — startup gating pattern (use `isStartingUp` for initial state)
- **Status:** [ ] Not started
