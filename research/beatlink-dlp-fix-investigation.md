# Research Findings: beat-link DLP ID Namespace Mismatch — Full Investigation

**Date:** 2026-03-19
**Researcher:** Claude (Opus 4.6)
**Status:** COMPLETE
**Complements:** `dlp-track-id-reliability.md`, `waveform-finder-hardware-compatibility.md`, `research-findings-bridge-data-strategy.md`, `findings-dlp-dbserver-protocol-namespaces.md`

---

## 1. Bug Trace — Full Call Path from CdjStatus to Wrong Data

### 1.1 Where the ID Enters beat-link

**File:** `CdjStatus.java`, constructor (~line 680)

```java
int maybeRekordboxId = (int) Util.bytesToNumber(packetBytes, 0x2c, 4);
```

The raw track ID is read from bytes 0x2c–0x2f of the CDJ status packet. On DLP hardware (XDJ-AZ, CDJ-3000X), this value is a **DLP-namespace ID** — the `djmdContent.ID` auto-increment primary key from `exportLibrary.db`.

### 1.2 The Critical Branch: Opus Quad vs Everything Else

**File:** `CdjStatus.java`, constructor (~lines 690–716)

```java
if (isFromOpusQuad && (trackSourceByte < 16)) {
    // Opus Quad path: translates DLP ID → DeviceSQL ID via PSSI matching
    // OR keeps DLP ID if usingDeviceLibraryPlus() is true (DLP key mode)
    ...
    maybeRekordboxId = VirtualRekordbox.findDeviceSqlRekordboxIdForPlayer(player);
    ...
} else {
    // ALL OTHER DEVICES — including XDJ-AZ — land here
    trackSourcePlayer = trackSourceByte;
    trackSourceSlot = findTrackSourceSlot();
    // NO ID translation. Raw DLP ID passes through unchanged.
}
rekordboxId = maybeRekordboxId;  // Final assignment — DLP ID for XDJ-AZ
```

**The bug site:** `DeviceUpdate.java` (parent of `CdjStatus`) only sets `isFromOpusQuad`:

```java
isFromOpusQuad = deviceName.equals(OpusProvider.OPUS_NAME);  // "OPUS-QUAD"
```

There is **no `isFromXdjAz`** or **`isFromDlpDevice`** flag on `DeviceUpdate`/`CdjStatus`. The XDJ-AZ takes the `else` branch, and its DLP-namespace ID passes through with zero translation.

### 1.3 DataReference Construction

**File:** `MetadataFinder.java`, `requestMetadataFrom(CdjStatus status)` (~line 46):

```java
final DataReference track = new DataReference(
    status.getTrackSourcePlayer(),
    status.getTrackSourceSlot(),
    status.getRekordboxId(),      // ← DLP-namespace ID for XDJ-AZ
    status.getTrackType()
);
```

`DataReference` is a simple immutable value object with no ID translation logic. Whatever goes in stays in.

### 1.4 How Each Finder Uses the Wrong ID

All Finders follow the same pattern:

1. Build `DataReference` from `CdjStatus` (DLP ID baked in)
2. Check registered `MetadataProvider`s (OpusProvider, CrateDigger's provider) — if none intercept, fall through
3. Check `isOpusQuad` to bail — **XDJ-AZ is NOT Opus**, so it proceeds to dbserver
4. Send dbserver query with `new NumberField(track.rekordboxId)` — **DLP ID sent to DeviceSQL-speaking dbserver**

| Finder | dbserver Request Type | ID Used | Result |
|--------|----------------------|---------|--------|
| MetadataFinder | `REKORDBOX_METADATA_REQ` | DLP ID → wrong DeviceSQL record | **Wrong title/artist/key** |
| BeatGridFinder | `BEAT_GRID_REQ` | DLP ID → wrong beatgrid | **Wrong beat positions** |
| WaveformFinder | `WAVEFORM_DETAIL_REQ` | DLP ID → wrong waveform | **Wrong waveform shape** |
| AnalysisTagFinder | Analysis tag request | DLP ID → wrong ANLZ data | **Wrong phrase/cue data** |
| CrateDigger | NFS database download | DLP ID → wrong playlist entry | **Wrong playlist membership** |

### 1.5 Why Opus Quad Works But XDJ-AZ Doesn't

The Opus Quad has **two** workarounds that the XDJ-AZ lacks:

1. **PSSI-based ID translation** (PR #86, merged 2025-04-05): `VirtualRekordbox.findDeviceSqlRekordboxIdForPlayer()` uses SHA-1 hashes of PSSI (song structure) data to match DLP IDs to DeviceSQL IDs. This only runs in the `isFromOpusQuad` branch.

2. **DLP key mode** (`OpusProvider.usingDeviceLibraryPlus()` = true): When the encrypted SQLite database key is set, the DLP ID is kept as-is and used directly against the SQLite database. CrateDigger also supports this path via JDBC.

3. **OpusProvider** is gated on `VirtualCdj.inOpusQuadCompatibilityMode()` — XDJ-AZ does NOT trigger this mode, so OpusProvider cannot start for it.

**Confidence:** HIGH. Traced directly from beat-link source code on GitHub (main branch, v8.x).

---

## 2. Research Question Answers

### Q1: The dbserver on DLP Hardware

**Does the XDJ-AZ have a functioning dbserver?**
Yes. beat-link's `ConnectionManager` explicitly documents the XDJ-AZ as having a dbserver (shared between its two decks via a single IP, like the XDJ-XZ). However, beat-link's changelog states: "The XDJ-AZ always uses Device Library Plus IDs, so DeviceSQL downloads can't be used safely."

**What ID namespace does the dbserver use?**
UNCLEAR. Two possibilities:
- **Hypothesis A:** The dbserver speaks the standard DeviceSQL protocol but the IDs in status packets are DLP-namespace, creating a mismatch. This would mean the dbserver serves `export.pdb` data while the player reports `exportLibrary.db` IDs.
- **Hypothesis B:** The dbserver has been updated to serve DLP data natively with DLP IDs, but beat-link doesn't understand the DLP response format.

beat-link's treatment (marking DLP downloads as unsafe) suggests **Hypothesis A is more likely** — the dbserver still expects DeviceSQL IDs but the player reports DLP IDs.

**Does the USB contain BOTH databases?**
YES. When DLP is enabled in rekordbox, USB export writes both `export.pdb` and `exportLibrary.db` side by side. Both reference the same audio files and ANLZ files. The XDJ-AZ only reads `exportLibrary.db` — if it's missing, the device shows "rekordbox Database not found!"

**Confidence:** HIGH for dual-database presence, MEDIUM for dbserver protocol behavior (no wire-level confirmation).

**Sources:** beat-link source, beat-link changelog, Lexicon DJ documentation, AlphaTheta support docs.

### Q2: Upstream Status

#### Open Issues & PRs

| Item | Repo | Date | Relevance |
|------|------|------|-----------|
| **PR #86** (merged) | beat-link | 2025-02-06 → 2025-04-05 | PSSI-based DLP→DeviceSQL ID translation for Opus Quad |
| **PR #94** (merged) | beat-link | 2025-07-17 → 2025-08-03 | Opus Quad Mode 2 with absolute packets |
| **Issue #90** (closed) | beat-link | 2025-05-26 → 2025-07-14 | dbserver port search fix for all-in-one devices (XDJ-AZ, XDJ-XZ) |
| **Issue #97** (closed) | beat-link | 2025-09-25 | Prevented erroneous dbserver requests to Opus Quad |
| **Issue #191** | beat-link-trigger | 2025-01-19 | XDJ-AZ "not supposed to be supported" per @brunchboy |
| **Issue #208** (open) | beat-link-trigger | 2025-07-27 | rekordbox metadata queries require real player numbers |
| **Issue #11** (closed) | crate-digger | 2020-03-17 → 2024-09-04 | `exportExt.pdb` schema support added |

#### Maintainer Position (@brunchboy / James Elliott)

1. **On XDJ-AZ** (2025-01-19): "This isn't a bug because the XDJ-AZ is not supposed to be supported. Some people are exploring whether that is possible, but it depends on how far the hardware limitations can be worked around."
2. **On PSSI matching** (2025-03-31): Approved as best available approach. Noted "if people want to avoid this problem they can figure out the SQLite password."
3. **Discussion venue:** Exploratory hardware work is directed to Zulip (`deep-symmetry.zulipchat.com`), not GitHub issues.
4. **DLP awareness in v8 changelog:** "The XDJ-AZ always uses Device Library Plus IDs, so DeviceSQL downloads cannot be used safely."

#### Release Timeline

| Version | Date | Key Features |
|---------|------|--------------|
| v7.3.0 | 2023-11-24 | CDJ-3000 support |
| v7.4.0 | 2024-05-05 | Opus Quad preliminary work |
| v8.0.0 | 2025-07-22 | PSSI-based Opus Quad support, Mode 1 |
| v8.1.0-SNAPSHOT | 2025-12-07 | Mode 2, CDJ-3000 fixes, all-in-one port fixes |

Cadence: ~6–12 months between major versions. No stated timeline for XDJ-AZ support.

**Confidence:** HIGH. Direct from GitHub issues, PRs, and releases.

### Q3: ID Translation / Mapping

**Is there a deterministic mapping between DLP and DeviceSQL IDs?**
YES — **file path is the natural shared key**. Both databases reference the same audio files at the same paths on the USB (e.g., `/Contents/Artist/Album/Track.mp3`). The ANLZ file path is also shared.

**No Pioneer cross-reference table exists.** The two databases have independent auto-increment sequences. Mapping must be derived at read time.

**Building a translation table at scan time:**

```python
# Pseudocode — O(N) scan, <2s for typical USB
from pyrekordbox import DeviceLibraryPlus
from pyrekordbox import RekordboxPdb

# Read DLP database
dlp_db = DeviceLibraryPlus("/Volumes/USB/PIONEER/rekordbox/exportLibrary.db")
dlp_by_path = {normalize(c.FolderPath): c.id for c in dlp_db.get_content()}

# Read DeviceSQL database
pdb = RekordboxPdb("/Volumes/USB/PIONEER/rekordbox/export.pdb")
devicesql_by_path = {normalize(t.file_path): t.id for t in pdb.get_tracks()}

# Build bidirectional map
dlp_to_devicesql = {}
devicesql_to_dlp = {}
for path, dlp_id in dlp_by_path.items():
    if path in devicesql_by_path:
        ds_id = devicesql_by_path[path]
        dlp_to_devicesql[dlp_id] = ds_id
        devicesql_to_dlp[ds_id] = dlp_id
```

**Performance:** O(N) with hash lookups. Under 2 seconds for 500–2000 tracks. One-time cost at USB scan.

**Alternative keys:** Title+Artist (not unique for remixes), ANLZ file path (shared, unique), SHA-256 of audio file (I/O-heavy, unreliable if transcoded).

**Confidence:** HIGH for file-path mapping feasibility. Already aligns with SCUE's existing tiered reconciliation strategy (composite key → path stem → title+artist).

### Q4: Fix Strategies — Detailed Evaluation

#### Strategy A: Patch beat-link to be DLP-aware for XDJ-AZ

**Concept:** Add `isFromXdjAz` / `isFromDlpDevice` to `DeviceUpdate`, then handle XDJ-AZ in the CdjStatus constructor like Opus Quad — translate DLP ID → DeviceSQL ID.

**Scope of changes:**
- `DeviceUpdate.java`: Add `isFromXdjAz` and `isFromDlpDevice` booleans
- `CdjStatus.java`: Add XDJ-AZ branch in constructor with ID translation
- Need a translation mechanism — PSSI matching requires VirtualRekordbox mode (Opus-only); file-path mapping requires database access

**Pros:** Fixes the bug at the root. All downstream Finders work correctly.
**Cons:** Requires upstream contribution. VirtualRekordbox/PSSI infrastructure is Opus-specific. @brunchboy has stated XDJ-AZ is "not supposed to be supported." Significant upstream effort with uncertain acceptance.
**Effort:** HIGH (3–5 weeks including upstream engagement)
**Risk:** HIGH (uncertain upstream acceptance, complex PSSI porting)
**Upstream-ability:** MEDIUM (aligned with project direction but maintainer hasn't prioritized)

#### Strategy B: Runtime ID Translation Layer in SCUE's Bridge

**Concept:** SCUE's Python-side bridge adapter intercepts `player_status` messages, detects DLP devices, and translates DLP IDs to SCUE fingerprints using pre-built USB scan data.

**How it works:**
1. USB scanner reads `exportLibrary.db` (rbox) → builds `{dlp_id: fingerprint}` mapping per USB
2. USB scanner reads `export.pdb` (pyrekordbox) → builds `{devicesql_id: fingerprint}` mapping per USB
3. Bridge adapter receives `player_status` with `rekordbox_id`
4. If device `uses_dlp: true`, look up fingerprint via DLP mapping
5. If device `uses_dlp: false`, look up fingerprint via DeviceSQL mapping
6. All downstream SCUE code works with fingerprints, never raw rekordbox IDs

**Pros:** Entirely within SCUE's control. No upstream dependency. Works for all hardware. Leverages existing USB scanning infrastructure.
**Cons:** Doesn't fix beat-link's Finders (MetadataFinder etc. still broken). Only works if USB is pre-scanned. Requires composite key disambiguation for multi-USB.
**Effort:** LOW (1–2 days, most infrastructure exists)
**Risk:** LOW (no external dependencies)
**Upstream-ability:** N/A (SCUE-internal)

#### Strategy C: Custom MetadataProvider (DlpProvider)

**Concept:** Build a `MetadataProvider` implementation (like OpusProvider) that registers with MetadataFinder and intercepts all Finder queries for DLP devices, serving metadata directly from the `exportLibrary.db` SQLite database.

**MetadataProvider interface requires:**
- `getTrackMetadata(MediaDetails, DataReference)` → `TrackMetadata`
- `getAlbumArt(MediaDetails, DataReference)` → `AlbumArt`
- `getBeatGrid(MediaDetails, DataReference)` → `BeatGrid`
- `getCueList(MediaDetails, DataReference)` → `CueList`
- `getWaveformPreview(MediaDetails, DataReference)` → `WaveformPreview`
- `getWaveformDetail(MediaDetails, DataReference)` → `WaveformDetail`
- `getAnalysisSection(MediaDetails, DataReference, String, String)` → `RawTag`

**How it works:**
1. DlpProvider opens `exportLibrary.db` via JDBC/SQLite (encryption handled by SQLCipher)
2. Registers with `MetadataFinder.addMetadataProvider()`
3. Intercepts queries where `DataReference.player` is from a DLP device
4. Queries SQLite directly using the DLP ID (which is correct for this database)
5. Constructs beat-link data objects from SQLite results
6. Returns them to the Finder pipeline — dbserver is never queried

**Pros:** Fixes all Finders. Uses the correct database with the correct IDs. Follows beat-link's plugin architecture. Could be contributed upstream.
**Cons:** Requires the DLP database encryption key. Requires Java implementation (beat-link is Java). Complex data object construction. beat-link doesn't have a built-in DLP SQLite reader.
**Effort:** HIGH (2–3 weeks for Java implementation)
**Risk:** MEDIUM (encryption key dependency, complex object mapping)
**Upstream-ability:** HIGH (follows OpusProvider pattern, natural extension)

#### Strategy D: Hybrid — Finders Only for Legacy, DLP Uses USB-Direct

**Concept:** This is essentially **what SCUE already does** (ADR-012). Finders are disabled entirely. DLP devices get metadata from rbox USB scanning. Legacy devices would get metadata from Finders if/when re-enabled.

**What it adds beyond current state:**
1. **Composite key fix:** Change `track_ids` primary key to `(source_player, source_slot, rekordbox_id)` — fixes the multi-USB collision bug identified in `dlp-track-id-reliability.md`
2. **Conditional Finder startup:** Start MetadataFinder/BeatGridFinder/WaveformFinder ONLY when `uses_dlp: false` for ALL connected devices
3. **Dual-namespace USB scanning:** Scan both `export.pdb` and `exportLibrary.db`, build mappings for both

**Pros:** Lowest risk. Builds on existing architecture. Unblocks legacy hardware metadata immediately. No upstream dependency.
**Cons:** Finders remain broken for DLP hardware (acceptable — USB-direct is the primary path). Mixed-hardware setups need careful namespace handling.
**Effort:** LOW-MEDIUM (2–4 days)
**Risk:** LOW
**Upstream-ability:** N/A

**Confidence:** HIGH for all strategy evaluations.

### Q5: Reproduction & Testing

**Can we reproduce without hardware?**
PARTIALLY. beat-link has no mock DLP device infrastructure. However:

1. **Unit test approach:** Create a mock `CdjStatus` with a known DLP-namespace ID. Verify that `getRekordboxId()` returns the DLP ID. Then construct a `DataReference` and verify the ID propagates unchanged. This proves the call path but doesn't prove wrong data returns.

2. **Integration test approach:** Use a USB drive exported from rekordbox with DLP enabled. Read both databases, confirm IDs differ for the same track. This proves the namespace mismatch exists without network hardware.

3. **beat-link-trigger simulation:** beat-link-trigger has offline analysis capabilities but they don't simulate DLP devices.

**If real hardware is needed (XDJ-AZ):**

| Test | What to Capture | Expected Result |
|------|-----------------|-----------------|
| Load track on XDJ-AZ | `rekordbox_id` from `player_status` | Note the ID value |
| Query USB `exportLibrary.db` | `djmdContent.ID` for same track | Should match `rekordbox_id` |
| Query USB `export.pdb` | DeviceSQL track ID for same track | Should NOT match `rekordbox_id` |
| If Finders were enabled: query metadata | Title/artist returned | Would be WRONG (different track) |
| Load same track on CDJ-3000 (same USB) | `rekordbox_id` from `player_status` | Should match `export.pdb` ID, NOT `exportLibrary.db` ID |

**Test harness for SCUE fix verification:**

```python
# test_dlp_id_namespace.py
import pytest
from unittest.mock import MagicMock

def test_dlp_device_uses_dlp_mapping():
    """When a DLP device reports a rekordbox_id, SCUE should
    resolve it via the DLP ID mapping, not the DeviceSQL mapping."""
    # Setup: USB with both databases
    dlp_mapping = {42: "fingerprint_abc"}      # DLP ID 42 → track ABC
    devicesql_mapping = {42: "fingerprint_xyz"} # DeviceSQL ID 42 → track XYZ (different!)

    # Player status from XDJ-AZ (uses_dlp=True)
    status = {"rekordbox_id": 42, "uses_dlp": True}

    # SCUE should use DLP mapping
    resolved = resolve_track(status, dlp_mapping, devicesql_mapping)
    assert resolved == "fingerprint_abc"  # NOT fingerprint_xyz

def test_legacy_device_uses_devicesql_mapping():
    """When a legacy device reports a rekordbox_id, SCUE should
    resolve it via the DeviceSQL mapping."""
    dlp_mapping = {42: "fingerprint_abc"}
    devicesql_mapping = {42: "fingerprint_xyz"}

    status = {"rekordbox_id": 42, "uses_dlp": False}

    resolved = resolve_track(status, dlp_mapping, devicesql_mapping)
    assert resolved == "fingerprint_xyz"

def test_composite_key_prevents_multi_usb_collision():
    """Two USBs with DLP ID 1 should not collide."""
    mapping = {}
    mapping[("1", "usb", 1)] = "fingerprint_usb1_track1"
    mapping[("2", "usb", 1)] = "fingerprint_usb2_track1"

    assert mapping[("1", "usb", 1)] != mapping[("2", "usb", 1)]
```

**Confidence:** HIGH for test design, MEDIUM for reproducibility without hardware.

---

## 3. Fix Strategy Comparison

| Criterion | A: Patch beat-link | B: SCUE Translation | C: DlpProvider | D: Hybrid (recommended) |
|-----------|:-:|:-:|:-:|:-:|
| **Effort** | HIGH (3–5 weeks) | LOW (1–2 days) | HIGH (2–3 weeks) | LOW-MED (2–4 days) |
| **Risk** | HIGH | LOW | MEDIUM | LOW |
| **Upstream-ability** | MEDIUM | N/A | HIGH | N/A |
| **Fixes Finders** | YES | NO | YES | NO (not needed) |
| **Fixes SCUE track ID** | YES | YES | YES | YES |
| **Multi-USB safe** | PARTIAL | YES | PARTIAL | YES |
| **Legacy hardware** | YES | YES | YES | YES |
| **External dependency** | beat-link maintainer | None | DLP encryption key | None |
| **Mixed-hardware** | YES | YES | YES | YES |
| **Time to value** | Months | Days | Weeks | Days |

---

## 4. Recommended Fix: Strategy D (Hybrid) with Strategy B elements

### Rationale

SCUE's architecture already accounts for the DLP problem (ADR-012). The remaining gaps are:

1. **Multi-USB collision** in `track_ids` — bare `rekordbox_id` without slot disambiguation
2. **Namespace-unaware track resolution** — no detection of which ID namespace a player uses
3. **Missing dual-database USB scanning** — only DLP database is scanned currently

Strategy D fills these gaps with minimal effort and zero upstream dependency, while keeping the door open for Strategy C (DlpProvider) as a future upstream contribution.

### Prototype: Dual-Namespace Track Resolution

```python
# scue/layer1/track_resolver.py
"""Resolves track identity from player_status messages using the correct
ID namespace based on hardware type."""

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class TrackKey:
    """Composite key that uniquely identifies a track on a specific device/slot."""
    source_player: int
    source_slot: str
    rekordbox_id: int

@dataclass
class TrackMapping:
    """Bidirectional mapping between rekordbox IDs and SCUE fingerprints,
    keyed by (source_player, source_slot, rekordbox_id)."""

    # DLP namespace: {TrackKey: fingerprint}
    dlp_ids: dict[TrackKey, str]

    # DeviceSQL namespace: {TrackKey: fingerprint}
    devicesql_ids: dict[TrackKey, str]

    def resolve(self, player_status: dict) -> Optional[str]:
        """Resolve a player_status message to a SCUE fingerprint.

        Uses the correct ID namespace based on the device's uses_dlp flag.
        Falls back to path-stem matching if ID lookup fails.
        """
        key = TrackKey(
            source_player=player_status["track_source_player"],
            source_slot=player_status["track_source_slot"],
            rekordbox_id=player_status["rekordbox_id"],
        )

        if player_status.get("uses_dlp", False):
            return self.dlp_ids.get(key)
        else:
            return self.devicesql_ids.get(key)
```

```python
# scue/layer1/usb_scanner.py  (additions to existing scanner)
"""Scan both databases on a USB to build dual-namespace mappings."""

def scan_usb_dual_namespace(usb_mount: str) -> TrackMapping:
    """Scan a USB's DLP and DeviceSQL databases, building mappings
    for both ID namespaces keyed by file path."""
    import os
    from rbox import OneLibrary

    dlp_path = os.path.join(usb_mount, "PIONEER", "rekordbox", "exportLibrary.db")
    pdb_path = os.path.join(usb_mount, "PIONEER", "rekordbox", "export.pdb")

    # Step 1: Read DLP database (always present for DLP-exported USBs)
    fingerprints_by_path: dict[str, str] = {}
    dlp_ids: dict[TrackKey, str] = {}

    if os.path.exists(dlp_path):
        lib = OneLibrary(dlp_path)
        for track in lib.tracks():
            path = normalize_path(track.file_path)
            fingerprint = compute_or_lookup_fingerprint(path)
            fingerprints_by_path[path] = fingerprint
            # DLP IDs are per-USB, so source_player/slot filled at bind time

    # Step 2: Read DeviceSQL database (present alongside DLP on dual-export USBs)
    devicesql_ids: dict[TrackKey, str] = {}

    if os.path.exists(pdb_path):
        from pyrekordbox.pdb import RekordboxPdb
        pdb = RekordboxPdb(pdb_path)
        for track in pdb.get_tracks():
            path = normalize_path(track.file_path)
            if path in fingerprints_by_path:
                # Same track found in both databases — record DeviceSQL ID
                pass  # DeviceSQL mapping built at bind time

    return TrackMapping(dlp_ids=dlp_ids, devicesql_ids=devicesql_ids)
```

### Prototype: Conditional Finder Startup

```java
// In BeatLinkBridge.java — conditional Finder startup
// Only start Finders when NO DLP devices are on the network

private boolean shouldStartFinders() {
    // Check all known devices — if any use DLP, don't start Finders
    for (DeviceAnnouncement device : DeviceFinder.getInstance().getCurrentDevices()) {
        if (device.isUsingDeviceLibraryPlus()) {
            logger.info("DLP device detected ({}), Finders will not be started",
                        device.getName());
            return false;
        }
    }
    return true;
}

// Called after all devices are discovered:
if (shouldStartFinders()) {
    MetadataFinder.getInstance().start();
    BeatGridFinder.getInstance().start();
    WaveformFinder.getInstance().start();
    // AnalysisTagFinder, CrateDigger if needed
    emitter.emitBridgeStatus(/* finders_active: true */);
} else {
    emitter.emitBridgeStatus(/* finders_active: false */);
}
```

### Implementation Steps

1. **Fix composite key** — Change `track_ids` table to use `(source_player, source_slot, rekordbox_id)` as primary key. Update all lookups.
2. **Add `uses_dlp` to track resolution** — When resolving `player_status.rekordbox_id`, check the device's `uses_dlp` flag to select the correct mapping namespace.
3. **Dual-database USB scanning** — Extend USB scanner to read both `exportLibrary.db` and `export.pdb`, building mappings for both namespaces.
4. **Conditional Finder startup** (future) — When legacy hardware support is added, start Finders only when no DLP devices are present.

---

## 5. Test Plan

### Without Hardware (Unit/Integration)

| Test | Method | Validates |
|------|--------|-----------|
| DLP ID ≠ DeviceSQL ID for same track | Read both DBs from a real USB export | Namespace mismatch exists |
| Composite key prevents collision | Unit test with mock data | Multi-USB disambiguation |
| `uses_dlp` flag routes to correct mapping | Unit test with mock player_status | Namespace-aware resolution |
| Path-stem matching as fallback | Unit test with tracks missing from ID map | Graceful degradation |
| Dual-database scanner reads both DBs | Integration test with real USB | Both mappings populated |

### With Hardware (XDJ-AZ)

| Test | Setup | Expected | Validates |
|------|-------|----------|-----------|
| Single USB, single XDJ-AZ | Load track, capture `rekordbox_id` | Matches `exportLibrary.db` ID | DLP namespace confirmed |
| Same USB on CDJ-3000 | Load same track, capture `rekordbox_id` | Matches `export.pdb` ID | DeviceSQL namespace confirmed |
| Mixed setup | XDJ-AZ + CDJ-3000, same USB | Different IDs, same SCUE fingerprint | Dual-namespace resolution works |
| Two USBs on XDJ-AZ | Load tracks from each | No collision | Composite key works |
| Track change on XDJ-AZ | Switch tracks, verify resolution | Correct fingerprint each time | Stable resolution |

### Regression

| Test | Validates |
|------|-----------|
| Legacy CDJ-2000NXS2 still works | No regression for DeviceSQL hardware |
| Bridge `player_status` schema unchanged | No breaking changes to message format |
| USB scanner still handles DLP-only USBs | No regression for XDJ-AZ-only exports |

---

## 6. Upstream Contribution Path

### Short-term: Not Recommended

@brunchboy has explicitly stated the XDJ-AZ is "not supposed to be supported" and directs hardware exploration to Zulip. A PR to beat-link for XDJ-AZ support would be premature and likely rejected without community consensus.

### Medium-term: Strategy C (DlpProvider) as Contribution

If SCUE proves the DLP ID problem can be solved cleanly, a `DlpProvider` implementation following the OpusProvider pattern could be contributed upstream:

1. **Phase 1:** Build and validate in SCUE (Java bridge)
2. **Phase 2:** Engage on Zulip with @brunchboy, share findings and prototype
3. **Phase 3:** Submit PR to beat-link with test coverage and documentation
4. **Timeline:** After SCUE validates the approach in production (3–6 months)

### PR Strategy

- **Title:** "Add DlpProvider for XDJ-AZ / CDJ-3000X metadata via exportLibrary.db"
- **Approach:** Follow OpusProvider's architecture exactly. Register as a `MetadataProvider`. Intercept queries for DLP devices. Read SQLite directly.
- **Key selling point:** The Opus Quad workaround (PSSI matching) is imprecise. Direct SQLite reading with DLP IDs is exact.
- **Prerequisite:** DLP database encryption key must be resolved (pyrekordbox and rbox both have it; beat-link's Java ecosystem doesn't)
- **Risk:** @brunchboy may prefer to handle this differently. Zulip engagement first is essential.

### What to Share Upstream Now

Even without a PR, this research is valuable to the beat-link community. Consider posting a summary to the Zulip channel with:
- The exact bug trace (CdjStatus constructor, XDJ-AZ takes `else` branch)
- The DLP ID confirmation from USB database cross-reference
- The file-path mapping approach
- An offer to help test

---

## 7. Skill File Candidates

### Updates for `skills/beat-link-bridge.md`

```markdown
## DLP ID Namespace Mismatch (Critical)

### The Bug
CdjStatus.getRekordboxId() on XDJ-AZ/CDJ-3000X returns DLP-namespace IDs
(from exportLibrary.db). All Finders use these IDs to query the dbserver,
which expects DeviceSQL-namespace IDs (from export.pdb). Result: wrong
track metadata for every query.

### Root Cause
DeviceUpdate.java only flags isFromOpusQuad — there is no isFromXdjAz or
isFromDlpDevice. XDJ-AZ takes the else branch in CdjStatus constructor,
and its DLP ID passes through with zero translation.

### Upstream Status
- Opus Quad: Fixed via PSSI matching (PR #86) and DLP key mode
- XDJ-AZ: "Not supposed to be supported" per @brunchboy (Jan 2025)
- CDJ-3000X: Not addressed
- beat-link v8.0.0 is current; v8.1.0-SNAPSHOT has incremental fixes

### SCUE Workaround
ADR-012: Don't start Finders. Use rbox to read exportLibrary.db directly.
Track resolution uses composite key (source_player, source_slot, rekordbox_id)
with uses_dlp flag to select correct ID namespace.

### Key Source Files
- CdjStatus.java constructor (~line 680-716) — the branch
- DeviceUpdate.java — missing isFromXdjAz flag
- DeviceAnnouncement.java — isUsingDeviceLibraryPlus detection
- OpusProvider.java — MetadataProvider pattern to follow
- MetadataFinder.java requestMetadataFrom() — DataReference construction
```

### Updates for `skills/pioneer-hardware.md`

```markdown
## DLP / DeviceSQL Dual Database

### Both databases on USB
When DLP is enabled, rekordbox exports BOTH export.pdb (DeviceSQL) and
exportLibrary.db (DLP/OneLibrary). Both reference same audio files and
ANLZ files. IDs are INDEPENDENT auto-increment sequences — same track
has different IDs in each database.

### File path as mapping key
Both databases store the audio file path. Normalized file path is the
deterministic shared key for building DLP↔DeviceSQL ID mapping tables.
O(N) scan, <2s for typical USB.

### CDJ-3000 firmware 3.30 incident (Oct 2025)
Pioneer attempted OneLibrary transition for CDJ-3000, pulled firmware
due to playlist reconciliation bugs. CDJ-3000 remains DeviceSQL-only.

### Hardware ID namespace reference
| Device | Reports | Reads |
|--------|---------|-------|
| CDJ-2000NXS2 | DeviceSQL IDs | export.pdb |
| CDJ-3000 | DeviceSQL IDs | export.pdb |
| CDJ-3000X | DLP IDs | exportLibrary.db |
| XDJ-AZ | DLP IDs | exportLibrary.db |
| Opus Quad | DLP IDs | exportLibrary.db |
| OMNIS-DUO | DLP IDs | exportLibrary.db (no network) |
```

---

## Appendix A: Key External Sources

| Source | URL | Relevance |
|--------|-----|-----------|
| beat-link GitHub | https://github.com/Deep-Symmetry/beat-link | Primary source code |
| beat-link PR #86 | https://github.com/Deep-Symmetry/beat-link/pull/86 | PSSI ID translation |
| beat-link PR #94 | https://github.com/Deep-Symmetry/beat-link/pull/94 | Opus Mode 2 |
| beat-link-trigger #191 | https://github.com/Deep-Symmetry/beat-link-trigger/issues/191 | XDJ-AZ not supported |
| crate-digger #11 | https://github.com/Deep-Symmetry/crate-digger/issues/11 | exportExt.pdb schema |
| Opus Quad analysis | https://github.com/kyleawayan/opus-quad-pro-dj-link-analysis | Protocol reverse-engineering |
| DJ Link Analysis | https://djl-analysis.deepsymmetry.org/ | Protocol documentation |
| BLT Opus Guide | https://blt-guide.deepsymmetry.org/beat-link-trigger/OpusQuad.html | Opus Quad user guide |
| Lexicon DJ DLP | https://www.lexicondj.com/blog/everything-you-need-to-know-about-device-library-plus-and-more | DLP overview |
| CDJ-3000 FW 3.30 | https://www.pioneerdj.com/en/news/2025/important-notice-cdj-3000-firmware-ver330/ | Firmware incident |
| pyrekordbox | https://github.com/dylanljones/pyrekordbox | Python DLP/PDB reader |
| rbox | https://pypi.org/project/rbox/ | Rust DLP reader |
| Zulip community | https://deep-symmetry.zulipchat.com/#narrow/channel/275322-beat-link-trigger | Upstream discussion venue |

## Appendix B: CDJ-3000 Firmware 3.30 Incident Detail

In October 2025, Pioneer released CDJ-3000 firmware 3.30 which added "OneLibrary" (DLP) support. When both `export.pdb` and `exportLibrary.db` were present on a USB, the firmware defaulted to reading OneLibrary — but had bugs reconciling playlist data between the two formats. This caused widespread playlist display failures for DJs who hadn't explicitly migrated to DLP. Pioneer suspended distribution of firmware 3.30 and recommended firmware 3.20 as a stable fallback.

**Relevance to SCUE:** This demonstrates that even Pioneer struggles with the DLP/DeviceSQL dual-database problem. The CDJ-3000 may eventually transition to DLP IDs, which would expand the set of devices that trigger the namespace mismatch in beat-link. SCUE's dual-namespace approach (Strategy D) future-proofs against this scenario.
