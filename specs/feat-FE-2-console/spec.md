# Spec: FE-2 Console Panel

## Summary

The Console panel is a collapsible log viewer docked at the bottom of the SCUE shell layout. It displays real-time system events sourced from existing WebSocket messages (`bridge_status`, `pioneer_status`), with two audience modes (Clean for DJs, Verbose for developers), a ring-buffer retention model, and an optional Record mode that captures log history for export. No new backend WebSocket message types are introduced in v1.

## User-Facing Behavior

The console occupies the bottom region of the shell, below the main content area. It collapses to a thin header bar (already implemented via `uiStore.consoleOpen`). When expanded, the user sees:

1. A **header row** with controls: mode toggle, record button, clear button, and a collapse/expand chevron.
2. A **scrollable log area** showing timestamped, color-coded entries that auto-scroll to the bottom as new entries arrive.
3. In **Clean mode**, only meaningful state changes appear (connection events, mode changes, errors). In **Verbose mode**, every incoming WS message generates an entry.

---

## Component Hierarchy

```
Console (existing — becomes thin wrapper)
  ConsoleHeader
    ModeToggle (Clean / Verbose)
    RecordButton (idle / recording / saving)
    ClearButton
    CollapseChevron (existing toggle, relocated into header)
  ConsolePanel
    LogEntry (repeated, virtualized if needed in v2)
      Timestamp
      SourceBadge
      SeverityIndicator
      Message
```

### Component Responsibilities

| Component | Reusable? | Notes |
|-----------|-----------|-------|
| `Console` | No | Existing component. Refactored to compose `ConsoleHeader` + `ConsolePanel`. Retains the border/bg styling and open/close behavior from `uiStore`. |
| `ConsoleHeader` | No | Feature-specific. Renders controls in a single horizontal row. Always visible (even when console is collapsed). |
| `ModeToggle` | No | Two-state button: "Clean" / "Verbose". Visual toggle, not a dropdown. |
| `RecordButton` | No | Tri-state: idle (circle icon), recording (pulsing red dot + "Stop"), saving (spinner). |
| `ClearButton` | No | Simple icon button. Clears visible log. |
| `ConsolePanel` | No | Scrollable log container. Only rendered when `consoleOpen === true`. |
| `LogEntry` | Yes | Stateless presentational row. Receives entry data as props. Could be reused in a future Logs page. |
| `SourceBadge` | Yes | Small pill badge showing the event source. Reuses the badge pattern from track table mood badges. |

---

## State Model: `consoleStore`

A new independent Zustand store at `frontend/src/stores/consoleStore.ts`. Per project rules, it does not import any other store.

### State Shape

```typescript
interface ConsoleEntry {
  id: string;             // Unique ID (nanoid or incrementing counter)
  timestamp: number;      // Date.now() at time of entry creation
  source: ConsoleSource;  // "bridge" | "pioneer" | "system"
  severity: ConsoleSeverity; // "info" | "warn" | "error"
  message: string;        // Human-readable message string
  verbose: boolean;       // true = only shown in Verbose mode
  raw?: unknown;          // Original WS payload (only in Verbose mode entries)
}

type ConsoleSource = "bridge" | "pioneer" | "system";
type ConsoleSeverity = "info" | "warn" | "error";

interface ConsoleStoreState {
  // Log entries — ring buffer, max 200
  entries: ConsoleEntry[];

  // Mode
  verboseMode: boolean;

  // Recording
  isRecording: boolean;
  recordBuffer: ConsoleEntry[];

  // Actions
  addEntry: (entry: Omit<ConsoleEntry, "id" | "timestamp">) => void;
  setVerboseMode: (verbose: boolean) => void;
  startRecording: () => void;
  stopRecording: () => ConsoleEntry[];  // Returns buffer for save
  clearEntries: () => void;
}
```

### Ring Buffer Behavior

- `entries` array is capped at `MAX_ENTRIES = 200`.
- When a new entry is added and the array is at capacity, the oldest entry is dropped (shift from front, push to back).
- The `addEntry` action also appends to `recordBuffer` if `isRecording === true`. The record buffer has no size limit.

### State Transitions

| Action | Effect on `entries` | Effect on `recordBuffer` |
|--------|-------------------|-------------------------|
| `addEntry` | Append (ring buffer, max 200) | Append if `isRecording` |
| `clearEntries` | Empty array | No effect (recording continues if active) |
| `startRecording` | No effect | Initialize empty array, set `isRecording = true` |
| `stopRecording` | No effect | Return buffer contents, clear buffer, set `isRecording = false` |
| `setVerboseMode` | No effect (filtering is at render time) | No effect |

---

## Log Entry Format

### Timestamp: Absolute (HH:MM:SS.mmm)

**Decision:** Use absolute timestamps in `HH:MM:SS.mmm` format (24-hour, with milliseconds).

**Reasoning:** Relative timestamps ("2s ago") require continuous re-rendering to stay accurate, adding CPU cost for no real benefit. In a debugging scenario, absolute timestamps are essential for correlating console entries with other logs or recordings. DJs in Clean mode see fewer entries, so timestamp clutter is minimal. Absolute timestamps also export cleanly to `.log` files without needing conversion.

**Alternative rejected:** Relative timestamps ("2s ago", "just now"). These are friendlier but require a timer to update displayed values, create ambiguity when scrolling back through history, and lose precision during export.

### Source Badge

A colored pill displaying the event source:

| Source | Label | Color (Tailwind) | When Used |
|--------|-------|-------------------|-----------|
| `bridge` | `BRG` | `bg-blue-900 text-blue-300` | Events derived from `bridge_status` WS messages |
| `pioneer` | `PIO` | `bg-cyan-900 text-cyan-300` | Events derived from `pioneer_status` WS messages |
| `system` | `SYS` | `bg-gray-700 text-gray-300` | WebSocket connect/disconnect, internal frontend events |

**Decision:** Use 3-letter abbreviations to save horizontal space. The console is information-dense; full words like "BRIDGE" consume too much room per row.

### Severity Indicator

A small colored dot or icon preceding the message:

| Severity | Visual | Color (Tailwind) | Usage |
|----------|--------|-------------------|-------|
| `info` | Dim dot or no indicator | `text-gray-500` | Normal state changes, status updates |
| `warn` | Yellow dot | `text-yellow-500` | Route warnings, degraded mode, high message age |
| `error` | Red dot | `text-red-500` | Crashes, connection failures, missing JAR/JRE |

**Decision:** Use a small filled circle (Unicode `\u25CF`) rather than icons. This keeps the log compact and avoids importing an icon library just for severity.

### Message String

Plain text, single line. Examples:

- Clean info: `Bridge connected on en16 (port 17400)`
- Clean info: `Pioneer traffic resumed`
- Clean warn: `Bridge entered fallback mode`
- Clean error: `Bridge crashed (restart 2/3, retry in 8s)`
- Verbose info: `bridge_status: running, 2 devices, 2 players`
- Verbose info: `pioneer_status: receiving=true, age=450ms`

### Full Entry Layout (single row)

```
HH:MM:SS.mmm  [BRG]  *  Bridge connected on en16 (port 17400)
^timestamp     ^badge ^severity  ^message
```

Monospace font (`font-mono`). Each entry is a single line; no wrapping. Horizontal scroll if a message exceeds container width (unlikely given message brevity, but handles edge cases).

---

## Mode Toggle: Clean vs Verbose

### Clean Mode (default)

The DJ-facing mode. Shows only high-signal events:

**From `bridge_status` messages — shown when state changes (diff detection):**
- Status changes: `stopped -> starting`, `starting -> running`, `running -> crashed`, etc.
- Mode changes: `bridge -> fallback`
- Device discovery: new device appears or disappears (diff `devices` object)
- Restart events: `restart_count` increases
- Route warnings: `route_warning` changes from null to a string
- Errors: `jar_exists` becomes false, `jre_available` becomes false

**From `pioneer_status` messages — shown on transitions only:**
- `is_receiving` flips from `false` to `true`: "Pioneer traffic resumed"
- `is_receiving` flips from `true` to `false`: "Pioneer traffic lost"
- `bridge_connected` flips: "Bridge connection lost" / "Bridge connection restored"

**From system events:**
- WebSocket connected: "Connected to backend"
- WebSocket disconnected: "Backend connection lost"
- WebSocket reconnecting: "Reconnecting... (attempt N)"

**Filtering mechanism:** Entries have a `verbose` boolean. Clean mode renders `entries.filter(e => !e.verbose)`. This means filtering happens at render time, not at insertion time. If the user switches from Clean to Verbose, all 200 buffered entries (including verbose ones) become visible immediately.

### Verbose Mode

Shows everything Clean shows, plus:

**From `bridge_status` messages — every message:**
- Full status summary: `bridge_status: {status}, {N} devices, {N} players`

**From `pioneer_status` messages — every message:**
- Full payload: `pioneer_status: receiving={bool}, age={N}ms`

Verbose entries have `verbose: true` set on the entry.

### Toggle Interaction

- Single button in the header. Displays current mode label.
- Clean mode: button reads "Clean" with a muted style.
- Verbose mode: button reads "Verbose" with an accent style (slightly brighter) to indicate the noisier mode is active.
- Switching modes does NOT clear the log. The render filter instantly shows/hides verbose entries.

---

## Record Mode Flow

### Button States

| State | Button Label | Visual | Behavior on Click |
|-------|-------------|--------|-------------------|
| **Idle** | Circle icon (outline) | `text-gray-500` | Start recording |
| **Recording** | "Stop" + pulsing red dot | `text-red-500 animate-pulse` | Stop and trigger save |
| **Saving** | Spinner | `text-gray-400` | Non-interactive (brief, during file generation) |

### Recording Flow

1. **Start:** User clicks record button. `isRecording` becomes `true`. `recordBuffer` initializes as empty array. A pulsing red dot appears next to the button. From this point, every entry added via `addEntry` is also appended to `recordBuffer` (regardless of verbose/clean mode — all entries are captured).

2. **During recording:** Entries accumulate in `recordBuffer` without limit. The ring buffer (`entries`) continues to operate normally (capped at 200). The Clear button still works on `entries` but does not affect `recordBuffer`.

3. **Stop & Save:** User clicks the "Stop" button. `stopRecording()` is called, which:
   - Sets `isRecording = false`
   - Returns the full `recordBuffer` contents
   - Clears `recordBuffer`

   The calling component then formats the entries and triggers a browser download.

### Export Format

Plain text `.log` file. One entry per line:

```
2026-03-18T14:30:01.123Z  [BRG]  INFO   Bridge connected on en16 (port 17400)
2026-03-18T14:30:03.456Z  [PIO]  INFO   pioneer_status: receiving=true, age=450ms
2026-03-18T14:30:05.789Z  [SYS]  WARN   Pioneer traffic lost
```

- ISO 8601 timestamps in the export (not the HH:MM:SS display format) for unambiguous log correlation.
- Severity as padded uppercase string (`INFO `, `WARN `, `ERROR`).
- Filename: `scue-console-YYYYMMDD-HHmmss.log`
- Download triggered via `Blob` + `URL.createObjectURL` + temporary `<a>` element click.

### Edge Cases

- **Mode switch during recording:** Recording captures all entries regardless of mode. The `verbose` flag is preserved on each entry. No special handling needed.
- **Clear during recording:** Only `entries` (display buffer) is cleared. `recordBuffer` is unaffected. This is intuitive: "clear the screen" is not "delete my recording."
- **Close console during recording:** Recording continues in the background. The pulsing indicator remains visible in the collapsed header bar to remind the user.
- **Navigation during recording:** Recording continues across page navigation (store is global). No data loss.

---

## Clear Button

- Empties the `entries` array in `consoleStore`.
- Does NOT affect `recordBuffer` if recording is active.
- Does NOT affect `verboseMode`.
- Visual: Trash/X icon, muted color, no confirmation dialog (entries are ephemeral and low-value individually).

---

## Layout Description

### Collapsed State (consoleOpen === false)

The console header bar is always visible at the bottom of the shell:

```
[v] Console                           [Clean] [Rec] [Clear]
```

- Left: Collapse chevron + "Console" label (existing behavior, preserved).
- Right: Mode toggle, Record button, Clear button.
- Height: ~32px (py-1.5 as existing).
- The record indicator (pulsing red dot) is visible even when collapsed.

### Expanded State (consoleOpen === true)

```
[^] Console                           [Clean] [Rec] [Clear]
-----------------------------------------------------------------
14:30:01.123  [BRG]  *  Bridge connected on en16 (port 17400)
14:30:03.456  [PIO]  *  pioneer_status: receiving=true, age=450ms
14:30:05.789  [SYS]  *  Pioneer traffic lost
                                                    [auto-scroll]
```

- Header row: Same as collapsed, but chevron points up.
- Log area: Fixed height `h-48` (192px, matching existing placeholder). Scrollable via `overflow-y-auto`.
- Auto-scroll: The log area scrolls to bottom on each new entry UNLESS the user has manually scrolled up. If the user scrolls up, auto-scroll pauses. It resumes when the user scrolls back to the bottom (within ~20px of the bottom edge).

### Responsive Behavior

- No breakpoint changes. The console spans the full width below the main content area at all screen sizes.
- On very narrow screens (<640px), source badges may truncate but timestamps and messages remain visible.
- The header controls wrap to a second line only if the container is extremely narrow (<400px), which is unlikely given the shell's sidebar takes ~200px.

---

## Visual Hierarchy

### Typography

- **Header controls:** `text-xs` (12px), `font-sans` (system default).
- **Log entries:** `text-xs` (12px), `font-mono` (monospace). Monospace ensures timestamp and badge columns align visually.
- **Timestamps:** `text-gray-600` (muted, not the primary read target).
- **Messages:** `text-gray-400` (default), `text-yellow-400` (warn), `text-red-400` (error).

### Color

All colors reference Tailwind's gray scale (dark theme):

| Element | Tailwind Class |
|---------|---------------|
| Console background | `bg-gray-950` (existing) |
| Header background | `bg-gray-950` (same as console body) |
| Header border | `border-t border-gray-800` (existing) |
| Entry hover | `hover:bg-gray-900` (subtle) |
| Timestamp text | `text-gray-600` |
| Message text (info) | `text-gray-400` |
| Message text (warn) | `text-yellow-400` |
| Message text (error) | `text-red-400` |
| Source badge backgrounds | See Source Badge table above |

### Spacing

- Entry vertical padding: `py-0.5` (2px) — tight to maximize visible entries.
- Entry horizontal padding: `px-4` (16px) — matches existing console padding.
- Gap between badge and message: `gap-2` (8px).
- Gap between timestamp and badge: `gap-2` (8px).

---

## Interaction Patterns

### Auto-Scroll

- Default: log area is scrolled to bottom, new entries appear and scroll into view.
- User scrolls up: auto-scroll pauses. A small "scroll to bottom" indicator could appear (v2 consideration, not required for v1).
- User scrolls back to bottom: auto-scroll resumes.
- Implementation: Check `scrollTop + clientHeight >= scrollHeight - 20` before each append. If true, scroll after append.

### Keyboard / Accessibility

- Header controls are focusable buttons with `aria-label` attributes.
- Mode toggle: `aria-label="Switch to Verbose mode"` / `"Switch to Clean mode"`.
- Record button: `aria-label="Start recording"` / `"Stop recording"` / `"Saving recording"`.
- Clear button: `aria-label="Clear console"`.
- Log area: `role="log"` and `aria-live="polite"` so screen readers announce new entries (rate-limited by the browser).

### Loading / Empty / Error States

| State | Display |
|-------|---------|
| **Empty (no entries)** | Centered muted text: "No console entries yet." |
| **Empty after clear** | Same as empty state. |
| **WS disconnected** | A system entry is logged: "Backend connection lost". The console continues to show existing entries. No special empty state. |
| **Error in entry parsing** | Silently dropped. Console never shows its own errors to avoid recursive noise. |

---

## WS Message Routing

The existing `dispatch()` function in `api/ws.ts` routes messages to `bridgeStore`. The console needs to observe these same messages without duplicating the WS connection.

**Approach:** Add a second dispatch target in `api/ws.ts`. After dispatching to the relevant store, also call `consoleStore.getState().addEntry(...)` with an appropriately formatted entry.

This is a minimal change to `ws.ts`: add a `dispatchToConsole(msg: WSMessage)` function that maps each message type to one or more `ConsoleEntry` objects, then call it from the existing `dispatch()` function.

The mapping logic (which WS message fields produce which console messages, what severity, what constitutes a "change" for Clean mode diff detection) lives in a dedicated utility: `frontend/src/utils/consoleMapper.ts`. This keeps `ws.ts` thin and the mapping logic independently testable.

### Diff Detection for Clean Mode

To generate Clean mode entries only on state changes, the mapper must track previous values. A simple approach:

```typescript
// In consoleMapper.ts
let prevBridgeStatus: string | null = null;
let prevIsReceiving: boolean | null = null;
let prevBridgeConnected: boolean | null = null;
let prevDeviceCount: number = 0;
// ... etc.
```

On each message, compare current values to previous. Generate entries only for fields that changed. Update previous values.

This module-level state is acceptable because:
1. There is exactly one WS connection (singleton).
2. The mapper is called synchronously from `dispatch()`.
3. No race conditions are possible.

---

## v1 Scope Constraints

### In Scope
- Console UI (header, log area, entries)
- `consoleStore` (Zustand, independent)
- WS dispatch hook into existing `api/ws.ts`
- `consoleMapper.ts` utility for WS message -> console entry conversion
- Record mode with `.log` file export
- Clean / Verbose mode toggle
- Clear button

### Out of Scope
- New backend WS message types (no Python changes)
- Backend log streaming (v2)
- Log persistence across page reloads (all in-memory)
- Log search or filtering beyond Clean/Verbose toggle
- Resizable console height (fixed at `h-48`)
- Virtualized rendering (v2 if performance requires it with 200 entries)

---

## Design Decisions Summary

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|---------------------|
| 1 | Absolute timestamps (HH:MM:SS.mmm) | No re-render cost, unambiguous for debugging, exports cleanly | Relative ("2s ago") requires timer, loses precision on scroll-back |
| 2 | 3-letter source badges (BRG/PIO/SYS) | Saves horizontal space in dense log view | Full words ("BRIDGE") too wide for compact rows |
| 3 | Unicode dot for severity (not icons) | Compact, no icon library dependency | Icon library adds bundle weight for minimal visual gain |
| 4 | Render-time filtering for Clean/Verbose | All entries stored; mode switch is instant with full history | Insert-time filtering would lose verbose entries when switching modes |
| 5 | Module-level prev-state in consoleMapper | Simple, no race conditions with singleton WS | Storing prev-state in Zustand would couple consoleStore to bridge schema |
| 6 | ISO 8601 in export, HH:MM:SS in display | Export needs unambiguous timestamps; display needs compactness | Same format for both would compromise one use case |
| 7 | Record captures all entries (both modes) | Recording is for debugging; losing verbose entries defeats the purpose | Mode-filtered recording would surprise users who switch modes mid-session |
| 8 | Clear does not affect record buffer | "Clear screen" and "delete recording" are different intents | Single clear-all would risk accidental data loss during active recording |
| 9 | Ring buffer size 200 | ~200 entries at 12px each fills ~10 screens of scroll; enough for recent context without memory concern | 500 (overkill for in-memory), 50 (too few for debugging) |

---

## Edge Cases

| Edge Case | Expected Behavior |
|-----------|------------------|
| Console expanded with no WS connection | Empty state: "No console entries yet." System entry logged when WS connects. |
| Rapid bridge status changes (e.g., crash loop) | Each status change generates a Clean entry. Ring buffer naturally caps at 200. No throttling in v1. |
| `pioneer_status` arriving every 2s in Verbose mode | One verbose entry per message. At 200-cap, oldest entries age out in ~400s (~6.5 min). Acceptable. |
| User clears during recording | Display clears, recording continues. Pulsing dot remains visible. |
| User closes console during recording | Recording continues. Pulsing dot visible in collapsed header. |
| Mode toggle while entries exist | Render filter instantly shows/hides verbose entries. No re-fetch, no flicker. |
| Export with 0 recorded entries | Stop button returns empty array. UI shows brief "Nothing recorded" toast or simply downloads an empty file. Prefer empty file for simplicity. |
| Multiple `bridge_status` messages with identical state | Diff detection in `consoleMapper` suppresses duplicate Clean entries. Verbose entries still generated for every message. |
