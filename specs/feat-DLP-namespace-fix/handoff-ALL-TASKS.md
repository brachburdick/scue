# Handoff Packet: DLP ID Namespace Fix — TASK-001 → TASK-002 → TASK-003

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: specs/feat-DLP-namespace-fix/handoff-TASK-001.md
superseded_by: none
---

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `preambles/COMMON_RULES.md`
3. `preambles/DEVELOPER.md`

## Dispatch
- Mode: ORCHESTRATOR DISPATCH
- Output path: `specs/feat-DLP-namespace-fix/sessions/session-developer.md`
- Parallel wave: none

## Objective
Fix the DLP ID namespace mismatch so that SCUE correctly resolves tracks from both DLP hardware (XDJ-AZ, CDJ-3000X) and legacy hardware (CDJ-2000NXS2, CDJ-3000) — including mixed setups sharing the same USB. Three sequential tasks, all in this session.

## Role
Developer

## Working Directory
- Run from: `/Users/brach/Documents/THE_FACTORY/projects/DjTools/scue`
- Related feature/milestone: feat-DLP-namespace-fix

## Task Sequence

Complete these three tasks **in order**. Run the test suite after each task. Do not begin the next task until the current one passes all tests.

---

### TASK-001: Composite key for track_ids and pioneer_metadata tables

**Goal:** Change `track_ids` and `pioneer_metadata` tables from bare `rekordbox_id` primary key to composite `(source_player, source_slot, rekordbox_id)` so tracks from multiple USBs and both ID namespaces can coexist.

**Files to modify:**
- `scue/layer1/storage.py` — change table schemas, update all functions that read/write these tables

**What to change:**

1. `track_ids` table (lines 165-169): Change schema to:
   ```sql
   CREATE TABLE IF NOT EXISTS track_ids (
     source_player TEXT NOT NULL,
     source_slot TEXT NOT NULL,
     rekordbox_id INTEGER NOT NULL,
     fingerprint TEXT NOT NULL,
     first_seen REAL NOT NULL,
     PRIMARY KEY (source_player, source_slot, rekordbox_id)
   )
   ```

2. `pioneer_metadata` table (lines 183-195): Change schema similarly — add `source_player TEXT NOT NULL` and `source_slot TEXT NOT NULL` columns, composite PK.

3. `lookup_fingerprint()` (lines 283-290): Add params with defaults:
   ```python
   def lookup_fingerprint(self, rekordbox_id: int, source_player: str = "1", source_slot: str = "usb") -> str | None:
   ```
   Update the SQL WHERE clause to match all three fields.

4. `link_rekordbox_id()` (lines 292-299): Add params with defaults:
   ```python
   def link_rekordbox_id(self, rekordbox_id: int, fingerprint: str, source_player: str = "1", source_slot: str = "usb") -> None:
   ```
   Update the SQL INSERT to include all three fields.

5. `store_pioneer_metadata()` (lines 351-382) and `get_pioneer_metadata()` (lines 384-414): Same pattern — add `source_player` and `source_slot` params with defaults, update SQL.

6. If the old single-column-PK table exists in a pre-existing DB, DROP and recreate. Data loss is acceptable — USB rescan repopulates.

**Why defaults:** `tracking.py` and `usb_scanner.py` call these functions without the new params. Defaults keep them working. TASK-002 and TASK-003 will pass explicit values.

**Tests:** Update existing tests in `tests/test_layer1/` for new signatures. Add a test proving two entries with same `rekordbox_id` but different `source_player`/`source_slot` coexist.

**Done when:**
- [ ] Both tables use composite PK
- [ ] All four functions accept `source_player` and `source_slot` with defaults
- [ ] Composite key collision test passes
- [ ] `python -m pytest tests/test_layer1/` passes

---

### TASK-002: Dual-namespace USB scanning

**Goal:** Extend USB scanning to read BOTH `exportLibrary.db` (DLP) and `export.pdb` (DeviceSQL) from the same USB, linking tracks across namespaces by file path. Populate `track_ids` with entries for both namespaces.

**Files to modify:**
- `scue/layer1/usb_scanner.py` — add DeviceSQL reading, dual-namespace mapping
- `tests/test_layer1/test_usb_scanner.py` — add tests

**Files to read (not modify):**
- `tools/pdb_lookup.py` — reference implementation for parsing `export.pdb` (DeviceSQL format)
- `scue/config/loader.py` — lines 62-64, UsbConfig paths

**What to change:**

1. Add a function to read `export.pdb` alongside the existing `read_usb_library()` which reads `exportLibrary.db`. You can use pyrekordbox's PDB support or adapt the parsing logic from `tools/pdb_lookup.py`. The function should return a list of tracks with `(devicesql_id, file_path)` tuples.

2. In `match_usb_tracks()` or `apply_scan_results()`, after matching DLP tracks to fingerprints:
   - Read `export.pdb` if it exists on the USB
   - For each DeviceSQL track, match to a DLP track by **normalized file path** (the shared key)
   - If matched, call `cache.link_rekordbox_id(devicesql_id, fingerprint, source_player, source_slot)` to create a DeviceSQL-namespace entry pointing to the same fingerprint

3. The source_player/source_slot for USB scan entries: use a convention like `source_player="usb-scan"` and `source_slot="usb"` for the initial scan. During live playback, TASK-003 will populate entries with actual player numbers.

   Actually — better approach: during USB scan, we don't know which player will load the USB. So create entries with a **wildcard or per-device-type marker**:
   - DLP entries: `source_player="dlp"`, `source_slot="usb"`
   - DeviceSQL entries: `source_player="devicesql"`, `source_slot="usb"`

   Then in TASK-003, the live resolver looks up by namespace type based on `uses_dlp`, not by actual player number. This avoids needing to know player assignments at scan time.

4. Handle edge cases:
   - `export.pdb` missing (DLP-only USB): skip DeviceSQL scanning, DLP entries only
   - `exportLibrary.db` missing (legacy-only USB): read `export.pdb` only, DeviceSQL entries only
   - Tracks in one DB but not the other: link what matches, skip the rest

**Tests:** Add tests for:
- Dual-database scan with both DBs present
- DLP-only USB (no `export.pdb`)
- Legacy-only USB (no `exportLibrary.db`)
- File path matching across namespaces

**Done when:**
- [ ] USB scan reads both databases when both exist
- [ ] `track_ids` has entries for both DLP and DeviceSQL namespaces for the same track
- [ ] Same fingerprint is linked from both namespace entries
- [ ] Single-database USBs still work
- [ ] `python -m pytest tests/test_layer1/` passes

---

### TASK-003: Namespace-aware live track resolution

**Goal:** When a player reports a `rekordbox_id` in a `player_status` message, resolve it through the correct namespace (DLP or DeviceSQL) based on the device's `uses_dlp` flag.

**Files to modify:**
- `scue/layer1/tracking.py` — update `_load_track_for_player()` to pass namespace info to lookup
- `scue/bridge/adapter.py` — ensure `PlayerState` exposes `track_source_player` and `track_source_slot` (check if already present)
- `tests/test_layer1/` — add namespace-aware resolution tests
- `tests/test_bridge/` — update if adapter changes needed

**Files to read (not modify):**
- `scue/bridge/messages.py` — line 88, PlayerStatusPayload fields (check for `track_source_player`, `track_source_slot`)

**What to change:**

1. Check `scue/bridge/adapter.py` `PlayerState` dataclass (~line 76). Verify it has `track_source_player` and `track_source_slot` fields. If not, add them, populated from `player_status` message payload.

2. Check `_handle_player_status()` (~lines 213-258). Verify it parses `track_source_player` and `track_source_slot` from the message payload and stores them on `PlayerState`.

3. In `scue/layer1/tracking.py` `_load_track_for_player()` (~line 108):
   - Currently calls: `cache.lookup_fingerprint(rb_id)`
   - Change to determine the namespace from the device's `uses_dlp` flag
   - Call: `cache.lookup_fingerprint(rb_id, source_player="dlp" if uses_dlp else "devicesql", source_slot="usb")`
   - This matches the namespace markers set during USB scanning in TASK-002

4. Similarly update the `cache.get_pioneer_metadata(rb_id)` call (~line 125) to pass namespace info.

5. The `uses_dlp` flag: `tracking.py` receives player updates. It needs access to the device's `uses_dlp` flag. Check how `PlaybackTracker` accesses device info — it may need to query the adapter's `_devices` dict or receive `uses_dlp` as part of the player update callback.

**Tests:** Add tests for:
- DLP device resolves track via DLP namespace
- Legacy device resolves same track via DeviceSQL namespace
- Mixed setup: both devices resolve to the same fingerprint
- Unknown device (no USB scan data): returns None gracefully

**Done when:**
- [ ] `_load_track_for_player()` uses `uses_dlp` to select correct namespace
- [ ] XDJ-AZ with DLP ID 42 → correct fingerprint via DLP namespace
- [ ] CDJ-3000 with DeviceSQL ID 17 → same fingerprint via DeviceSQL namespace
- [ ] Track change detection still works
- [ ] `python -m pytest tests/` passes (full suite — bridge + layer1)
- [ ] No `[INTERFACE IMPACT]` — all changes are internal

---

## Scope Boundary (all tasks)
- Files this agent MAY read/modify:
  - `scue/layer1/storage.py`
  - `scue/layer1/usb_scanner.py`
  - `scue/layer1/tracking.py`
  - `scue/bridge/adapter.py` — only to add/verify `track_source_player`/`track_source_slot` fields on `PlayerState`
  - `scue/config/loader.py` — only to add `pdb_relative_path` to `UsbConfig` if needed
  - `tests/test_layer1/`
  - `tests/test_bridge/`
- Files this agent MAY read (not modify):
  - `scue/bridge/messages.py` — understand payload fields
  - `scue/api/usb.py` — understand scan endpoint callers
  - `tools/pdb_lookup.py` — DeviceSQL parsing reference
  - `research/beatlink-dlp-fix-investigation.md`
  - `research/dlp-track-id-reliability.md`
  - `research/findings-dlp-dbserver-protocol-namespaces.md`
  - `skills/pioneer-hardware.md`
- Files this agent must NOT touch:
  - `scue/api/` — API layer (except reading usb.py for context)
  - `scue/bridge/client.py` — WebSocket client
  - `scue/bridge/manager.py` — bridge lifecycle
  - `scue/bridge/messages.py` — message type definitions
  - `bridge-java/` — Java bridge
  - `frontend/` — all frontend files
  - `docs/interfaces.md` — no contract changes (all changes are internal)
  - `docs/CONTRACTS.md`

## Context Files
- `AGENT_BOOTSTRAP.md`
- `preambles/COMMON_RULES.md`
- `preambles/DEVELOPER.md`
- `scue/layer1/storage.py` — full file (primary target)
- `scue/layer1/usb_scanner.py` — full file
- `scue/layer1/tracking.py` — full file
- `scue/bridge/adapter.py` — full file
- `scue/bridge/messages.py` — read-only, understand payload shapes
- `tools/pdb_lookup.py` — DeviceSQL parsing reference
- `specs/feat-DLP-namespace-fix/tasks.md` — task breakdown and rationale
- `research/beatlink-dlp-fix-investigation.md` — sections 4 (recommended fix) and Q3 (ID mapping)
- `research/dlp-track-id-reliability.md` — composite key rationale, reconciliation strategy
- `skills/pioneer-hardware.md` — hardware context

## Interface Contracts
- No external interface changes. All modifications are internal to Layer 1.
- `lookup_fingerprint()` and `link_rekordbox_id()` signatures change but use defaults for backwards compatibility.
- If you discover an interface change is needed, flag `[INTERFACE IMPACT]` and stop.

## Required Output
- Write: `specs/feat-DLP-namespace-fix/sessions/session-developer.md`
- Include all three tasks in the session summary with per-task status.

## Constraints
- Complete tasks in order: TASK-001 → TASK-002 → TASK-003. Run tests after each.
- Use default parameter values in TASK-001 so existing callers survive until TASK-002/003 update them.
- SQLite migration for TASK-001: DROP and recreate tables. No complex ALTER TABLE.
- `source_player` and `source_slot` are TEXT in all tables and function signatures.
- Do not add new external dependencies. pyrekordbox is already installed. rbox is already installed.
- Do not import across layer boundaries except through defined contracts.
- NEVER overwrite Pioneer-sourced data with SCUE-derived data.
- Use `.venv/bin/python` for running tests, not bare `python`.

## Acceptance Criteria (session-level)
- [ ] All TASK-001 criteria met (composite key, defaults, migration)
- [ ] All TASK-002 criteria met (dual-database scan, file-path matching)
- [ ] All TASK-003 criteria met (namespace-aware resolution, uses_dlp routing)
- [ ] Full test suite passes: `.venv/bin/python -m pytest tests/`
- [ ] Session summary written to output path
- [ ] No `[INTERFACE IMPACT]` flags raised (or if raised, work stopped and documented)

## Dependencies
- Requires completion of: none
- Blocks: Validator dispatch, QA testing with XDJ-AZ hardware

## Open Questions
None.
