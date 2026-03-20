# Research: beat-link DLP Fix Investigation

Date: 2026-03-20
Status: COMPLETE — SUPERSEDES previous version (2026-03-19)

## Executive Summary

**The DLP ID namespace mismatch is already fixed in beat-link 8.1.0-SNAPSHOT.** SCUE's bridge uses beat-link 8.0.0, which cannot get correct metadata from the XDJ-AZ. beat-link-trigger (BLT) uses 8.1.0-SNAPSHOT, which treats the XDJ-AZ as a normal CDJ with a working dbserver — enabling live metadata, waveforms, beatgrids, phrase analysis, and cue points. Upgrading the bridge JAR from 8.0.0 to 8.1.0-SNAPSHOT and enabling Finders is the primary fix.

ADR-012's blanket disabling of all Finders was correct for 8.0.0 but is now unnecessarily restrictive. The XDJ-AZ has a working dbserver (unlike the Opus Quad which has none). CrateDigger downloads `exportLibrary.db` over NFS to provide ID translation.

---

## 1. Bug Trace: Full Call Path

### How CdjStatus gets the wrong ID (v8.0.0)

```
CdjStatus constructor (line ~680)
  → reads raw ID: Util.bytesToNumber(packetBytes, 0x2c, 4)  // DLP namespace ID
  → if (isFromOpusQuad && trackSourceByte < 16):
      → PSSI-based translation → DeviceSQL ID  ✓ (Opus Quad handled)
  → else:
      → raw ID used as-is  ✗ (XDJ-AZ falls here — DLP ID passes through)
  → rekordboxId = maybeRekordboxId  // DLP ID for XDJ-AZ

MetadataFinder.requestMetadataFrom(CdjStatus)
  → DataReference(status.getTrackSourcePlayer(), status.getTrackSourceSlot(),
                   status.getRekordboxId(),  // ← DLP namespace ID!
                   status.getTrackType())
  → requestMetadataInternal(DataReference, ...)
    → checks MetadataProviders (none registered for XDJ-AZ)
    → checks isOpusQuad? NO (XDJ-AZ is not Opus Quad) → proceeds to dbserver
    → ConnectionManager.invokeWithClientSession(track.player, ...)
      → sends REKORDBOX_METADATA_REQ with NumberField(track.rekordboxId)  // DLP ID
      → dbserver returns DeviceSQL record matching that number  // WRONG TRACK
```

Same pattern for WaveformFinder, BeatGridFinder, AnalysisTagFinder, CrateDigger.

### Key asymmetry in DeviceUpdate

```java
// DeviceAnnouncement.java — BOTH flags set correctly
isOpusQuad = name.equals("OPUS-QUAD");
isXdjAz = name.equals("XDJ-AZ");
isUsingDeviceLibraryPlus = isOpusQuad || isXdjAz;

// DeviceUpdate.java — ONLY Opus Quad flagged
isFromOpusQuad = deviceName.equals(OpusProvider.OPUS_NAME);
// NO isFromXdjAz, NO isUsingDeviceLibraryPlus
```

This is why the CdjStatus constructor only translates IDs for Opus Quad.

### How 8.1.0-SNAPSHOT fixes it

Post-v8.0.0 commits (Aug 2025):

| Date | Commit | Change |
|------|--------|--------|
| 2025-08-06 | 76e951e | "Starting work on XDJ-AZ four-deck support" |
| 2025-08-07 | b3144e9 | "Don't download DeviceSQL DBs for SQLite hardware" |
| 2025-08-08 | f0c65da | "Try supporting SQLite downloads" (NFS→exportLibrary.db) |
| 2025-08-09 | 4d7d060 | "Support SQLite connection listeners" |
| 2025-09-25 | 2a1c28d | "Don't try DBServer queries to Opus Quad" (guard) |

In 8.1.0-SNAPSHOT:
- `VirtualCdj.start()` only checks `device.isOpusQuad` for compatibility mode — XDJ-AZ gets normal CDJ path
- `inOpusQuadCompatibilityMode()` = false for XDJ-AZ → nothing blocked
- CrateDigger downloads `exportLibrary.db` via NFS → JDBC connection → ID translation layer
- MetadataFinder queries dbserver normally with translated IDs
- WaveformFinder, BeatGridFinder, AnalysisTagFinder all work

---

## 2. Q1: The XDJ-AZ's dbserver

**Answer: The XDJ-AZ has a functioning dbserver.** Confidence: HIGH.

- beat-link's `ConnectionManager` explicitly mentions XDJ-AZ: "players in compound devices like the XDJ-XZ and XDJ-AZ share a single dbserver instance"
- `inOpusQuadCompatibilityMode()` is false for XDJ-AZ, so ConnectionManager discovers and connects to its dbserver normally
- CrateDigger can download databases over NFS from the XDJ-AZ (not blocked)
- BLT's Player Status window shows correct metadata, waveforms, and phrase analysis from a live XDJ-AZ — confirmed via user screenshot

**The XDJ-AZ's USB contains BOTH databases:**
- `exportLibrary.db` (DLP/OneLibrary SQLite) — primary database the XDJ-AZ uses
- `export.pdb` (DeviceSQL) — written by rekordbox for backwards compatibility

**Database key requirement:** `OpusProvider.usingDeviceLibraryPlus()` requires a `databaseKey` to decrypt `exportLibrary.db`. BLT has UI for this. Our bridge needs a `--database-key` CLI argument.

---

## 3. Q2: Upstream Status

**beat-link 8.1.0-SNAPSHOT is the upstream fix.** Not yet released as stable.

| Version | Date | XDJ-AZ Status |
|---------|------|---------------|
| 8.0.0 | 2025-07-22 | Broken (DLP ID mismatch) |
| 8.1.0-SNAPSHOT | 2025-08+, ongoing | Works (dbserver + NFS + SQLite) |

**Maintainer stance:** @brunchboy (Jan 2025): "XDJ-AZ is not supposed to be supported. Some people are exploring whether that is possible." By Aug 2025, he merged XDJ-AZ support commits, indicating the stance evolved.

**Key PRs:**
- PR #86 (merged 2025-04-05): PSSI-based ID matching for Opus Quad — by @kyleawayan
- PR #94 (merged 2025-08-03): Opus Quad Mode 2 (absolute packets)
- Issue #90 (closed 2025-07-14): Fix dbserver port search for all-in-one devices

**Release cadence:** ~6-12 months between major releases. 8.1.0 stable likely by mid-2026.

**CDJ-3000 firmware 3.30 incident (Oct 2025):** Pioneer released firmware adding OneLibrary support, defaulting to DLP when both databases present. Caused playlist issues. Pioneer suspended distribution. Demonstrates real-world DLP/DeviceSQL collision risk beyond just beat-link.

---

## 4. Q3: ID Translation / Mapping

**In 8.1.0-SNAPSHOT, CrateDigger handles translation automatically.**

For our USB-side mapping (ADR-016 Strategy D), the shared key between databases is **file path**:
- `export.pdb`: track table contains file path
- `exportLibrary.db`: `djmdContent` table contains file path
- Same audio files referenced by both → deterministic join

Building the mapping is O(N), completes in <2 seconds for typical USB sizes (~2000 tracks).

---

## 5. Q4: Fix Strategy Comparison

| Strategy | Effort | Risk | Upstream-able | Completeness | Recommended? |
|----------|--------|------|---------------|-------------|--------------|
| **A: Upgrade beat-link to 8.1.0-SNAPSHOT** | 2-3 days | LOW | N/A (uses upstream) | Full (metadata, waveforms, beatgrid, phrases, cues) | **YES** |
| B: SCUE translation layer (ADR-016) | 2-4 days | LOW | No | Partial (correct track ID only, no live waveforms) | Fallback |
| C: Custom DlpProvider | 2-3 weeks | MEDIUM | Yes | Full (but reinvents what upstream did) | No |
| D: Patch beat-link source | 3-5 weeks | HIGH | Full | No (upstream already fixed it) | No |

### Recommended Fix: Strategy A — Upgrade beat-link

1. BLT already proves it works with the XDJ-AZ using 8.1.0-SNAPSHOT
2. Zero custom code for ID translation — CrateDigger handles it
3. Enables ALL Finders: metadata, waveforms, beatgrids, phrase analysis, cue points
4. When 8.1.0 releases as stable, we're already on the right version
5. 2-3 days of work vs 2-3 weeks for alternatives

---

## 6. Q5: Reproduction & Testing

**Real hardware needed for full verification.** beat-link has no XDJ-AZ simulator.

### Test plan with XDJ-AZ hardware:
1. Build bridge JAR with beat-link 8.1.0-SNAPSHOT
2. Connect XDJ-AZ, load a track
3. Verify `device_found` message has `uses_dlp: true`
4. Verify `track_metadata` arrives with correct title/artist
5. Verify `waveform_detail` arrives (non-empty base64 data)
6. Verify `beat_grid` matches Pioneer-analyzed grid
7. Verify `phrase_analysis` contains PSSI data
8. Verify `cue_points` match rekordbox-set cues
9. Change tracks — verify metadata updates correctly
10. Multi-USB test: two USBs, verify composite key disambiguates

### Without hardware:
- `tools/mock_bridge.py` can be extended with new message types for frontend development
- Unit tests for Python adapter handlers (already have test infrastructure)
- Build verification: bridge JAR compiles and starts without hardware

---

## 7. BLT Player Status — Architecture Reference

BLT's Player Status window uses pre-built **Java Swing components from beat-link itself**:

### `WaveformPreviewComponent` (~1190 lines)
- Full-track color waveform overview
- Playback position marker (red=playing, white=stopped)
- Phrase color bars overlaid (from PSSI data)
- Minute markers, cue point triangles
- 30fps animation via `TimeFinder.getTimeFor(player)`

### `WaveformDetailComponent` (~1257 lines)
- Zoomed, auto-scrolling waveform centered on playback position
- Beat markers, cue labels, loop regions
- Phrase labels that stick to left edge during scroll
- Scale 1-32x zoom, 30fps animation

### Per-player data sources:
| Data | API | Class |
|------|-----|-------|
| Title/artist | `MetadataFinder.getLatestMetadataFor(n)` | `TrackMetadata` |
| Album art | `ArtFinder.getLatestArtFor(n)` | `AlbumArt` |
| Waveform preview | `WaveformPreviewComponent(n)` | Swing JComponent |
| Waveform detail | `WaveformDetailComponent(n)` | Swing JComponent |
| Phrase analysis | `AnalysisTagFinder.getLatestTrackAnalysisFor(n, ".EXT", "PSSI")` | `SongStructureTag` |
| Playback position | `TimeFinder.getTimeFor(n)` | interpolated ms |
| Beat position | `TimeFinder.getLatestPositionFor(n).getBeatWithinBar()` | 1-4 |
| On-air/playing | `VirtualCdj.getLatestStatusFor(n)` | `CdjStatus` |
| Tempo/pitch | `TimeFinder.getLatestUpdateFor(n)` | `TrackPositionUpdate` |

### BLT capabilities beyond Player Status:
- **`MenuLoader`**: Full playlist/artist/album browsing via dbserver protocol
- **`VirtualCdj.sendLoadTrackCommand()`**: Load tracks to players remotely

---

## 8. ADR-012 Reassessment

ADR-012 states: "MetadataFinder, BeatGridFinder, WaveformFinder, CrateDigger, AnalysisTagFinder [...] are incompatible with Device Library Plus hardware."

**This was true for beat-link 8.0.0. It is false for 8.1.0-SNAPSHOT.**

| Component | 8.0.0 (current) | 8.1.0-SNAPSHOT | Action |
|-----------|-----------------|----------------|--------|
| MetadataFinder | Broken on XDJ-AZ | Works | Enable |
| WaveformFinder | Broken on XDJ-AZ | Works | Enable |
| BeatGridFinder | Broken on XDJ-AZ | Works | Enable |
| AnalysisTagFinder | Broken on XDJ-AZ | Works | Enable |
| CrateDigger | Broken on XDJ-AZ | Works (downloads SQLite) | Enable |
| OpusProvider | Works (Opus Quad only) | Extended for XDJ-AZ | Enable |

ADR-012 should be superseded by a new ADR that:
1. Upgrades beat-link to 8.1.0-SNAPSHOT
2. Enables all Finders for XDJ-AZ (and legacy hardware)
3. Retains Opus Quad archive-based path (still has no dbserver)
4. Retains rbox/pyrekordbox USB scanning as supplementary data source
5. Documents the database key requirement

---

## 9. Skill File Update Candidates

### `skills/beat-link-bridge.md`:
- "beat-link 8.1.0-SNAPSHOT supports XDJ-AZ via normal CDJ path (not Opus Quad mode)"
- "Finders (Metadata, Waveform, BeatGrid, AnalysisTag) work on XDJ-AZ with 8.1.0+"
- "CrateDigger downloads exportLibrary.db via NFS for DLP devices"
- "--database-key CLI argument required for DLP database decryption"
- Gotcha about MetadataFinder wrong records — now version-conditional

### `skills/pioneer-hardware.md`:
- XDJ-AZ: "Has working dbserver. Full beat-link support in 8.1.0-SNAPSHOT."
- CDJ-3000X: "Likely same as XDJ-AZ. Untested."
- OMNIS-DUO: "No Ethernet. Cannot use beat-link."

---

## Sources

All findings from direct source code inspection and GitHub research:
- beat-link main branch (31 commits ahead of v8.0.0 tag)
- beat-link-trigger main branch (depends on beat-link 8.1.0-SNAPSHOT)
- beat-link PR #86, #94; Issues #68, #90, #97
- beat-link-trigger Issues #173, #191, #208
- crate-digger Issue #11
- kyleawayan/opus-quad-pro-dj-link-analysis
- BLT Opus Quad User Guide
- CDJ-3000 Firmware 3.30 suspension notice

Confidence: HIGH — corroborated by user's live BLT screenshot showing correct XDJ-AZ data.
