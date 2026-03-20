# Tasks: DLP ID Namespace Fix

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

## Summary

Fix the DLP ID namespace mismatch so that SCUE correctly resolves tracks from both DLP hardware (XDJ-AZ, CDJ-3000X) and legacy hardware (CDJ-2000NXS2, CDJ-3000) — including mixed setups sharing the same USB.

Three atomic tasks, sequential dependency chain.

## Dependency Graph

```
TASK-001 (composite key)
    ↓
TASK-002 (dual-namespace USB scanning)
    ↓
TASK-003 (namespace-aware live resolution)
```

---

## TASK-001: Composite key for track_ids table

- **Layer:** 1
- **Effort:** ~30 min
- **Depends on:** none
- **Scope:**
  - `scue/layer1/storage.py` — change `track_ids` schema, update `lookup_fingerprint()`, `link_rekordbox_id()`, `store_pioneer_metadata()`, `get_pioneer_metadata()`
  - `tests/test_layer1/` — add/update tests
- **Inputs:** Current `track_ids` table with bare `rekordbox_id INTEGER PRIMARY KEY`
- **Outputs:** `track_ids` table with composite PK `(source_player, source_slot, rekordbox_id)`; `pioneer_metadata` table updated similarly
- **Interface Scope:** PRODUCER — signatures of `lookup_fingerprint()` and `link_rekordbox_id()` change (new params)
- **QA Required:** NO (unit tests sufficient)
- **State Behavior:** N/A — backend only
- **Acceptance Criteria:**
  - [ ] `track_ids` table uses composite PK `(source_player TEXT, source_slot TEXT, rekordbox_id INTEGER)`
  - [ ] `lookup_fingerprint(rekordbox_id, source_player, source_slot)` queries with all three fields
  - [ ] `link_rekordbox_id(rekordbox_id, fingerprint, source_player, source_slot)` inserts with all three fields
  - [ ] `pioneer_metadata` table also keyed by composite `(source_player, source_slot, rekordbox_id)`
  - [ ] `store_pioneer_metadata()` and `get_pioneer_metadata()` updated to match
  - [ ] Two different USBs with the same `rekordbox_id=1` can coexist without collision
  - [ ] All pre-existing tests pass (updated for new signatures)
  - [ ] SQLite migration: if old DB exists, table is recreated (data loss acceptable — USB rescan repopulates)
- **Context files:**
  - `scue/layer1/storage.py` — lines 165-169 (track_ids schema), 283-299 (lookup/link), 351-425 (pioneer_metadata)
  - `research/dlp-track-id-reliability.md` — composite key rationale
- **Status:** not started

---

## TASK-002: Dual-namespace USB scanning

- **Layer:** 1
- **Effort:** ~30 min
- **Depends on:** TASK-001
- **Scope:**
  - `scue/layer1/usb_scanner.py` — add `export.pdb` reading alongside `exportLibrary.db`, populate both namespace mappings
  - `scue/config/loader.py` — add `pdb_relative_path` to UsbConfig if needed
  - `tests/test_layer1/test_usb_scanner.py` — add tests for dual-database scanning
  - `tools/pdb_lookup.py` — read-only reference for PDB parsing
- **Inputs:** USB mount path containing both `exportLibrary.db` and `export.pdb`
- **Outputs:** `track_ids` table populated with entries for BOTH ID namespaces (DLP and DeviceSQL), linked by file path matching
- **Interface Scope:** NONE — internal scanner changes, no contract changes
- **QA Required:** NO (unit tests sufficient)
- **State Behavior:** N/A — backend only
- **Acceptance Criteria:**
  - [ ] `read_usb_library()` or a new companion function reads `export.pdb` when present
  - [ ] File path is used as the shared key to link DLP IDs to DeviceSQL IDs for the same track
  - [ ] `apply_scan_results()` populates `track_ids` with entries for both namespaces (same fingerprint, different `(source_player, source_slot, rekordbox_id)` tuples)
  - [ ] When `export.pdb` is missing (DLP-only export), scanning still works (DLP-only mapping)
  - [ ] When `exportLibrary.db` is missing (legacy-only export), scanning still works (DeviceSQL-only mapping)
  - [ ] All pre-existing tests pass
- **Context files:**
  - `scue/layer1/usb_scanner.py` — full file
  - `tools/pdb_lookup.py` — DeviceSQL parsing reference
  - `scue/config/loader.py` — lines 62-64 (UsbConfig)
  - `research/beatlink-dlp-fix-investigation.md` — Q3 (ID mapping by file path)
  - `research/findings-dlp-dbserver-protocol-namespaces.md` — section 7 (mapping feasibility)
- **Status:** not started

---

## TASK-003: Namespace-aware live track resolution

- **Layer:** 1
- **Effort:** ~30 min
- **Depends on:** TASK-001, TASK-002
- **Scope:**
  - `scue/layer1/tracking.py` — pass `source_player`, `source_slot` to lookup; use `uses_dlp` to select correct scan namespace for pre-populating mappings
  - `scue/bridge/adapter.py` — ensure `PlayerState` exposes `track_source_player` and `track_source_slot` (may already exist)
  - `tests/test_layer1/` — add tests for namespace-aware resolution
  - `tests/test_bridge/` — update integration tests if adapter changes
- **Inputs:** `player_status` messages with `rekordbox_id`, `track_source_player`, `track_source_slot`; device `uses_dlp` flag
- **Outputs:** Correct fingerprint resolved regardless of whether the device reports DLP or DeviceSQL IDs
- **Interface Scope:** NONE — internal resolution changes, no contract changes
- **QA Required:** YES — mixed-hardware resolution is the core bug fix
- **State Behavior:** N/A — backend only
- **Acceptance Criteria:**
  - [ ] `_load_track_for_player()` passes `source_player` and `source_slot` to `cache.lookup_fingerprint()`
  - [ ] XDJ-AZ (DLP) loading track with DLP ID 42 resolves to correct fingerprint
  - [ ] CDJ-3000 (legacy) loading same track with DeviceSQL ID 17 resolves to same fingerprint
  - [ ] Mixed setup: both devices on network, same USB, both resolve correctly
  - [ ] Track change detection still works (rekordbox_id change fires callback)
  - [ ] `PlayerState` exposes `track_source_player` and `track_source_slot` for lookup
  - [ ] All pre-existing tests pass
- **Context files:**
  - `scue/layer1/tracking.py` — lines 45-150 (track resolution pipeline)
  - `scue/bridge/adapter.py` — lines 53 (DeviceInfo.uses_dlp), 76 (PlayerState.rekordbox_id), 213-258 (_handle_player_status)
  - `scue/bridge/messages.py` — line 88 (PlayerStatusPayload fields)
  - `research/beatlink-dlp-fix-investigation.md` — recommended fix section
- **Status:** not started
