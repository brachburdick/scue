# Tasks: FE-2 Console Panel

## Dependency Graph

```
TASK-001 (consoleStore)
  |
  +---> TASK-002 (consoleMapper) ---> TASK-003 (WS dispatch wiring)
  |
  +---> TASK-004 (ConsoleHeader UI)
  |       |
  |       +---> TASK-006 (Record mode + export)
  |
  +---> TASK-005 (LogEntry + ConsolePanel UI)
```

- TASK-001 has no dependencies (pure store, testable in isolation).
- TASK-002 depends on TASK-001 (needs `ConsoleEntry` type and `addEntry` action).
- TASK-003 depends on TASK-002 (wires mapper into `ws.ts` dispatch).
- TASK-004 depends on TASK-001 (reads store state for button states).
- TASK-005 depends on TASK-001 (reads `entries` and `verboseMode` from store).
- TASK-006 depends on TASK-001 + TASK-004 (record UI triggers store actions, export logic).

**Parallel tracks:** TASK-002/003 (FE-State) and TASK-004/005 (FE-UI) can proceed in parallel after TASK-001 is complete.

## Tasks

### TASK-001: Create consoleStore with ring buffer and recording state
- **Layer:** Frontend-State
- **Estimated effort:** 20 min
- **Depends on:** none
- **Scope:**
  - `frontend/src/stores/consoleStore.ts` (create)
  - `frontend/src/types/console.ts` (create)
  - `frontend/src/types/index.ts` (update — re-export console types)
- **Inputs:** Type definitions from `specs/feat-FE-2-console/spec.md` (State Model section)
- **Outputs:**
  - `ConsoleEntry`, `ConsoleSource`, `ConsoleSeverity` types exported from `types/console.ts`
  - `useConsoleStore` Zustand store with: `entries`, `verboseMode`, `isRecording`, `recordBuffer`, `addEntry`, `setVerboseMode`, `startRecording`, `stopRecording`, `clearEntries`
  - Ring buffer logic in `addEntry` (cap at 200, drop oldest)
  - `addEntry` appends to `recordBuffer` when `isRecording === true`
  - `stopRecording` returns buffer contents and clears it
- **Acceptance Criteria:**
  - [ ] `addEntry` appends to `entries` and caps at 200 (adding entry 201 drops entry 1)
  - [ ] `addEntry` appends to `recordBuffer` when `isRecording === true`
  - [ ] `addEntry` does NOT append to `recordBuffer` when `isRecording === false`
  - [ ] `clearEntries` empties `entries` but does NOT affect `recordBuffer`
  - [ ] `stopRecording` returns the full `recordBuffer`, clears it, and sets `isRecording = false`
  - [ ] `setVerboseMode` toggles `verboseMode` without affecting entries
  - [ ] Store is independent (no imports from other stores)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-2-console/spec.md` — State Model section
  - `frontend/src/stores/bridgeStore.ts` — reference for Zustand store pattern
  - `frontend/src/types/index.ts` — for re-export pattern
  - `frontend/CLAUDE.md` — store independence rule
- **Status:** [ ] Not started

### TASK-002: Create consoleMapper utility for WS message to entry conversion
- **Layer:** Frontend-State
- **Estimated effort:** 25 min
- **Depends on:** TASK-001
- **Scope:**
  - `frontend/src/utils/consoleMapper.ts` (create)
- **Inputs:**
  - `ConsoleEntry` type from TASK-001
  - `WSMessage` union type from `types/ws.ts`
  - `BridgeState` type from `types/bridge.ts`
  - Mapping rules from `specs/feat-FE-2-console/spec.md` (WS Message Routing + Mode Toggle sections)
- **Outputs:**
  - `mapWSMessageToEntries(msg: WSMessage): ConsoleEntry[]` function
  - Diff detection via module-level previous-state tracking
  - Clean entries (with `verbose: false`) generated only on state changes
  - Verbose entries (with `verbose: true`) generated for every message
  - `resetMapperState(): void` function (for testing)
- **Acceptance Criteria:**
  - [ ] `bridge_status` with status change from `stopped` to `running` produces a Clean entry with `verbose: false`, source `"bridge"`, severity `"info"`
  - [ ] `bridge_status` with status change to `crashed` produces a Clean entry with severity `"error"`
  - [ ] `bridge_status` with status change to `fallback` produces a Clean entry with severity `"warn"`
  - [ ] `bridge_status` with no state change produces only a Verbose entry (`verbose: true`)
  - [ ] `pioneer_status` with `is_receiving` flip from `false` to `true` produces a Clean entry: "Pioneer traffic resumed"
  - [ ] `pioneer_status` with `is_receiving` flip from `true` to `false` produces a Clean entry: "Pioneer traffic lost"
  - [ ] `pioneer_status` with no change produces only a Verbose entry
  - [ ] New device appearing in `bridge_status.devices` produces a Clean entry with device name
  - [ ] Device disappearing produces a Clean entry
  - [ ] `resetMapperState()` clears all tracked previous values (for test isolation)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-2-console/spec.md` — WS Message Routing section, Mode Toggle section
  - `frontend/src/types/ws.ts` — WSMessage union
  - `frontend/src/types/bridge.ts` — BridgeState, DeviceInfo, PlayerInfo
  - `docs/CONTRACTS.md` — bridge_status and pioneer_status payload schemas
- **Status:** [ ] Not started

### TASK-003: Wire consoleMapper into WS dispatch
- **Layer:** Frontend-State
- **Estimated effort:** 10 min
- **Depends on:** TASK-002
- **Scope:**
  - `frontend/src/api/ws.ts` (modify — add console dispatch)
  - `frontend/src/stores/consoleStore.ts` (import for `addEntry` call)
- **Inputs:**
  - `mapWSMessageToEntries` from TASK-002
  - `useConsoleStore` from TASK-001
- **Outputs:**
  - Every incoming WS message is dispatched to both the existing store AND `consoleStore` via the mapper
  - System entries for WS connect/disconnect events
- **Acceptance Criteria:**
  - [ ] `onOpen` adds a system entry: source `"system"`, severity `"info"`, message "Connected to backend", `verbose: false`
  - [ ] `onClose` adds a system entry: source `"system"`, severity `"error"`, message "Backend connection lost", `verbose: false`
  - [ ] Every `onMessage` call runs the message through `mapWSMessageToEntries` and calls `addEntry` for each resulting entry
  - [ ] Existing `bridge_status` and `pioneer_status` dispatch to `bridgeStore` is unchanged
  - [ ] Malformed messages that fail JSON parse do NOT produce console entries (existing silent-drop behavior preserved)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `frontend/src/api/ws.ts` — existing dispatch logic
  - `specs/feat-FE-2-console/spec.md` — WS Message Routing section
- **Status:** [ ] Not started

### TASK-004: Build ConsoleHeader with mode toggle, record button, clear button
- **Layer:** Frontend-UI
- **Estimated effort:** 25 min
- **Depends on:** TASK-001
- **Scope:**
  - `frontend/src/components/layout/ConsoleHeader.tsx` (create)
  - `frontend/src/components/layout/Console.tsx` (modify — compose ConsoleHeader)
- **Inputs:**
  - `useConsoleStore` (for `verboseMode`, `isRecording`, `setVerboseMode`, `startRecording`, `clearEntries`)
  - `useUIStore` (for `consoleOpen`, `toggleConsole`)
  - Layout and visual spec from `specs/feat-FE-2-console/spec.md` (Layout + Visual Hierarchy sections)
- **Outputs:**
  - `ConsoleHeader` component rendering: collapse chevron, "Console" label, mode toggle button, record button, clear button
  - Chevron and label on the left; controls on the right
  - Mode toggle shows "Clean" or "Verbose" with appropriate styling
  - Record button shows circle icon (idle), pulsing red dot + "Stop" (recording)
  - Clear button with trash/X icon
  - All buttons have `aria-label` attributes
  - `Console.tsx` updated to use `ConsoleHeader` instead of inline header markup
- **Acceptance Criteria:**
  - [ ] ConsoleHeader renders with collapse chevron, label, mode toggle, record button, clear button
  - [ ] Clicking mode toggle calls `setVerboseMode(!verboseMode)` and label updates
  - [ ] Record button shows idle state when `isRecording === false`
  - [ ] Record button shows pulsing red dot when `isRecording === true`
  - [ ] Clicking record (idle) calls `startRecording()`
  - [ ] Clear button calls `clearEntries()`
  - [ ] Clicking chevron calls `toggleConsole()`
  - [ ] Pulsing red indicator visible even when console is collapsed
  - [ ] All buttons have appropriate `aria-label`
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-2-console/spec.md` — Layout, Visual Hierarchy, Interaction Patterns sections
  - `frontend/src/components/layout/Console.tsx` — existing component to refactor
  - `frontend/src/stores/uiStore.ts` — consoleOpen state
  - `frontend/src/components/layout/TopBar.tsx` — reference for status indicator patterns
- **Status:** [ ] Not started

### TASK-005: Build LogEntry component and ConsolePanel log area
- **Layer:** Frontend-UI
- **Estimated effort:** 25 min
- **Depends on:** TASK-001
- **Scope:**
  - `frontend/src/components/layout/LogEntry.tsx` (create)
  - `frontend/src/components/layout/ConsolePanel.tsx` (create)
  - `frontend/src/components/layout/Console.tsx` (modify — compose ConsolePanel)
- **Inputs:**
  - `ConsoleEntry` type from TASK-001
  - `useConsoleStore` (for `entries`, `verboseMode`)
  - Layout and entry format from `specs/feat-FE-2-console/spec.md`
- **Outputs:**
  - `LogEntry` component: renders a single row with timestamp (HH:MM:SS.mmm), source badge, severity dot, message. Props: `entry: ConsoleEntry`.
  - `ConsolePanel` component: scrollable container (`h-48 overflow-y-auto`) rendering filtered entries. Reads `entries` and `verboseMode` from store. Filters entries: if `!verboseMode`, show only entries where `verbose === false`.
  - Auto-scroll behavior: scrolls to bottom on new entries unless user has scrolled up.
  - Empty state: "No console entries yet." centered and muted.
  - `Console.tsx` updated to render `ConsolePanel` when `consoleOpen === true`.
- **Acceptance Criteria:**
  - [ ] `LogEntry` renders timestamp in `HH:MM:SS.mmm` format from `entry.timestamp`
  - [ ] `LogEntry` renders source badge with correct label (BRG/PIO/SYS) and color per spec
  - [ ] `LogEntry` renders severity dot with correct color (gray/yellow/red)
  - [ ] `LogEntry` renders message text with severity-appropriate color
  - [ ] `ConsolePanel` renders only non-verbose entries when `verboseMode === false`
  - [ ] `ConsolePanel` renders all entries when `verboseMode === true`
  - [ ] `ConsolePanel` auto-scrolls to bottom on new entry when already at bottom
  - [ ] `ConsolePanel` does NOT auto-scroll when user has scrolled up
  - [ ] Empty state displays "No console entries yet." when `entries` is empty
  - [ ] All entries use `font-mono text-xs` styling
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-2-console/spec.md` — Log Entry Format, Visual Hierarchy, Interaction Patterns sections
  - `frontend/src/components/layout/Console.tsx` — existing component
  - `frontend/src/types/console.ts` — ConsoleEntry type
- **Status:** [ ] Not started

### TASK-006: Implement record stop and .log file export
- **Layer:** Frontend-UI
- **Estimated effort:** 15 min
- **Depends on:** TASK-001, TASK-004
- **Scope:**
  - `frontend/src/utils/consoleExport.ts` (create)
  - `frontend/src/components/layout/ConsoleHeader.tsx` (modify — wire stop button to export)
- **Inputs:**
  - `ConsoleEntry[]` from `stopRecording()` return value
  - Export format from `specs/feat-FE-2-console/spec.md` (Record Mode Flow section)
- **Outputs:**
  - `exportConsoleLog(entries: ConsoleEntry[]): void` function in `consoleExport.ts`
  - Formats entries as plain text: `ISO-timestamp  [SRC]  SEVERITY  message` (one per line)
  - Triggers browser download via Blob + createObjectURL + temporary anchor click
  - Filename: `scue-console-YYYYMMDD-HHmmss.log`
  - ConsoleHeader's stop button calls `stopRecording()`, passes result to `exportConsoleLog()`
  - Brief "saving" state on the button (spinner) during export
- **Acceptance Criteria:**
  - [ ] `exportConsoleLog` produces correct plain-text format: ISO 8601 timestamp, bracketed 3-letter source, padded uppercase severity, message
  - [ ] Filename follows `scue-console-YYYYMMDD-HHmmss.log` pattern using local time
  - [ ] Browser triggers a file download (Blob + createObjectURL approach)
  - [ ] Stop button in ConsoleHeader calls `stopRecording()` and passes entries to `exportConsoleLog()`
  - [ ] Empty recording (0 entries) still produces a download (empty file)
  - [ ] After export, record button returns to idle state
  - [ ] All pre-existing tests pass
- **Context files:**
  - `specs/feat-FE-2-console/spec.md` — Record Mode Flow, Export Format sections
  - `frontend/src/components/layout/ConsoleHeader.tsx` — from TASK-004
  - `frontend/src/stores/consoleStore.ts` — `stopRecording` action
- **Status:** [ ] Not started
