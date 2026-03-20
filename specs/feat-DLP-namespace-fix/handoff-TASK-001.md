# Handoff Packet: TASK-001 — Composite key for track_ids and pioneer_metadata tables

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `preambles/COMMON_RULES.md`
3. `preambles/DEVELOPER.md`

## Dispatch
- Mode: ORCHESTRATOR DISPATCH
- Output path: `specs/feat-DLP-namespace-fix/sessions/session-TASK-001-developer.md`
- Parallel wave: none

## Objective
Change `track_ids` and `pioneer_metadata` tables from bare `rekordbox_id` primary key to a composite key `(source_player, source_slot, rekordbox_id)` so that tracks from multiple USBs and both DLP/DeviceSQL namespaces can coexist without collision.

## Role
Developer

## Working Directory
- Run from: `/Users/brach/Documents/THE_FACTORY/projects/DjTools/scue`
- Related feature/milestone: feat-DLP-namespace-fix

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/layer1/storage.py` — change table schemas, update lookup/link/store/get functions
  - `tests/test_layer1/` — add/update tests for new function signatures
- Files this agent MAY read (not modify):
  - `scue/layer1/tracking.py` — understand callers of `lookup_fingerprint()` (do NOT modify — TASK-003 handles this)
  - `scue/layer1/usb_scanner.py` — understand callers of `link_rekordbox_id()` (do NOT modify — TASK-002 handles this)
  - `scue/bridge/adapter.py` — understand PlayerState fields available
  - `research/dlp-track-id-reliability.md` — composite key rationale
  - `research/beatlink-dlp-fix-investigation.md` — full investigation
- Files this agent must NOT touch:
  - `scue/layer1/tracking.py` — caller updates are TASK-003
  - `scue/layer1/usb_scanner.py` — scanner changes are TASK-002
  - `scue/api/` — API layer
  - `scue/bridge/` — bridge layer
  - `frontend/` — all frontend files
  - `docs/interfaces.md` — no contract changes (these are internal tables)

## Context Files
- `AGENT_BOOTSTRAP.md`
- `preambles/COMMON_RULES.md`
- `preambles/DEVELOPER.md`
- `scue/layer1/storage.py` — full file. Key locations:
  - `track_ids` table schema: lines 165-169 (`rekordbox_id INTEGER PRIMARY KEY`)
  - `lookup_fingerprint(rekordbox_id)`: lines 283-290
  - `link_rekordbox_id(rekordbox_id, fingerprint)`: lines 292-299
  - `pioneer_metadata` table schema: lines 183-195 (`rekordbox_id INTEGER PRIMARY KEY`)
  - `store_pioneer_metadata(rekordbox_id, metadata)`: lines 351-382
  - `get_pioneer_metadata(rekordbox_id)`: lines 384-414
- `research/dlp-track-id-reliability.md` — "Q2: Multi-USB DLP ID Collision" section explains why composite key is needed
- `specs/feat-DLP-namespace-fix/tasks.md` — full task breakdown

## Interface Contracts
- `lookup_fingerprint()` and `link_rekordbox_id()` are called by:
  - `scue/layer1/tracking.py` — `_load_track_for_player()` line 108
  - `scue/layer1/usb_scanner.py` — `match_usb_tracks()` line 326, `apply_scan_results()` line 397
- These callers will be updated in TASK-002 and TASK-003. For now, **add `source_player` and `source_slot` as parameters with defaults** so existing callers don't break:
  - `lookup_fingerprint(rekordbox_id: int, source_player: str = "1", source_slot: str = "usb") -> str | None`
  - `link_rekordbox_id(rekordbox_id: int, fingerprint: str, source_player: str = "1", source_slot: str = "usb") -> None`
  - Same pattern for `store_pioneer_metadata()` and `get_pioneer_metadata()`

## State Behavior
N/A — backend only, no UI components affected.

## Constraints
- Use default parameter values (`source_player="1"`, `source_slot="usb"`) so existing callers (tracking.py, usb_scanner.py) continue to work without changes. TASK-002 and TASK-003 will pass explicit values.
- SQLite migration: if the old single-column-PK table exists, DROP and recreate. Data loss is acceptable — a USB rescan repopulates everything. Do NOT attempt complex ALTER TABLE migration.
- `source_player` is TEXT (not INTEGER) because it's used as part of a composite key and comes from bridge messages as varying types.
- `source_slot` is TEXT with values like `"usb"`, `"sd"`, `"collection"`.
- Do not add new dependencies.
- All pre-existing tests must continue to pass (update test calls for new signatures using defaults).

## Acceptance Criteria
- [ ] `track_ids` table uses composite PK: `PRIMARY KEY (source_player, source_slot, rekordbox_id)`
- [ ] `pioneer_metadata` table uses composite PK: `PRIMARY KEY (source_player, source_slot, rekordbox_id)`
- [ ] `lookup_fingerprint(rekordbox_id, source_player="1", source_slot="usb")` queries with all three fields
- [ ] `link_rekordbox_id(rekordbox_id, fingerprint, source_player="1", source_slot="usb")` inserts with all three fields
- [ ] `store_pioneer_metadata()` and `get_pioneer_metadata()` accept and use `source_player` and `source_slot` params (with defaults)
- [ ] Two entries with same `rekordbox_id` but different `source_player`/`source_slot` can coexist
- [ ] Old DB with single-column PK is handled gracefully (table recreated, no crash)
- [ ] All pre-existing tests pass (`python -m pytest tests/test_layer1/`)
- [ ] New tests verify composite key uniqueness and collision prevention

## Dependencies
- Requires completion of: none
- Blocks: TASK-002 (dual-namespace scanning), TASK-003 (namespace-aware resolution)

## Open Questions
None.
