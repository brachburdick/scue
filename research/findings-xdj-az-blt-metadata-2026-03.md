# Research Findings: XDJ-AZ Metadata in Beat-Link-Trigger (March 2026)

## Context
BLT was observed showing correct metadata, color waveforms, and phrase analysis from
an XDJ-AZ in real-time. This contradicts earlier assumptions (based on beat-link v8.0.0)
that DLP hardware couldn't provide metadata without pre-built archives.

## Key Discovery: beat-link 8.1.0-SNAPSHOT Has XDJ-AZ Support

beat-link-trigger's `project.clj` declares `[org.deepsymmetry/beat-link "8.1.0-SNAPSHOT"]`.
The v8.1.0-SNAPSHOT branch (main) contains significant work since v8.0.0 (released 2025-07-21)
that changes the XDJ-AZ story completely.

### Timeline of relevant commits (post v8.0.0):

| Date | SHA | Description |
|---|---|---|
| 2025-08-06 | 76e951e | "Starting work on XDJ-AZ four-deck support" |
| 2025-08-07 | b3144e9 | "Don't download DeviceSQL DBs for SQLite hardware" |
| 2025-08-08 | f0c65da | "Try supporting SQLite downloads" (NFS download of exportLibrary.db) |
| 2025-08-09 | 4d7d060 | "Support SQLite connection listeners" |
| 2025-09-24 | c33b0e6 | "Fix VirtualCdj toString with Opus Quad" |
| 2025-09-25 | 2a1c28d | "Don't try DBServer queries to Opus Quad" (explicit guard) |

---

## Question 1: How does BLT get waveform and metadata from the XDJ-AZ?

### Answer: The XDJ-AZ is treated as a NORMAL CDJ (not Opus Quad mode), and beat-link queries its dbserver directly.

**Critical architectural difference from Opus Quad:**

| Aspect | Opus Quad | XDJ-AZ |
|---|---|---|
| dbserver port | NONE | HAS ONE |
| `VirtualCdj.start()` behavior | Enters Opus Quad compat mode | Normal CDJ startup |
| `inOpusQuadCompatibilityMode()` | true | false |
| Metadata source | OpusProvider archive only | dbserver queries (live) |
| NFS database download | BLOCKED | ALLOWED |
| `isUsingDeviceLibraryPlus` | true | true |

**The XDJ-AZ has a working dbserver.** This is the fundamental difference from the Opus
Quad. When `VirtualCdj.start()` runs, it only checks `device.isOpusQuad` to enter
compatibility mode. `device.isXdjAz` is NOT checked. The XDJ-AZ falls through to the
normal `createVirtualCdj()` path.

**How metadata flows for XDJ-AZ (v8.1.0-SNAPSHOT):**

1. **Device detection:** `DeviceAnnouncement` sets `isXdjAz = true` and
   `isUsingDeviceLibraryPlus = true` based on device name "XDJ-AZ".

2. **ConnectionManager:** Not blocked for XDJ-AZ (the `inOpusQuadCompatibilityMode()`
   guard doesn't apply). ConnectionManager discovers the dbserver port on the XDJ-AZ
   and opens connections normally.

3. **MetadataFinder:** The v8.0.0 "DLP ID mismatch" problem appears to have been
   addressed. The commit "Starting work on XDJ-AZ four-deck support" modified
   `OpusProvider.java` to extend its track-matching logic. The subsequent SQLite
   download commits allow CrateDigger to download `exportLibrary.db` over NFS and
   open JDBC connections, providing an ID translation layer.

4. **CrateDigger NFS path:** For XDJ-AZ, `inOpusQuadCompatibilityMode()` is false,
   so NFS downloads are NOT blocked. `canUseDatabase()` returns true when
   `OpusProvider.usingDeviceLibraryPlus()` is true (requires database key set).
   CrateDigger downloads `exportLibrary.db` (SQLite) over NFS, opens a JDBC
   connection, and delivers it via `SQLiteConnectionListener`.

5. **WaveformFinder:** Gets waveforms via the registered MetadataProvider
   (OpusProvider) or via direct dbserver queries. Since the XDJ-AZ has a dbserver,
   both paths can work.

6. **AnalysisTagFinder (phrase analysis):** The explicit Opus Quad guard
   (`if isOpusQuad return null`) does NOT apply to XDJ-AZ. Phrase analysis (PSSI)
   can be queried from the XDJ-AZ's dbserver.

### Previous research correction

The `waveform-finder-hardware-compatibility.md` matrix listed XDJ-AZ as "BROKEN (DLP ID
mismatch)". This was accurate for beat-link v8.0.0 but is OUTDATED for v8.1.0-SNAPSHOT.
The XDJ-AZ commit series (Aug 2025) specifically addressed this.

---

## Question 2: Can BLT browse playlists and load tracks remotely?

### Answer: YES to both. beat-link has full playlist browsing and track loading via the dbserver protocol.

**Playlist browsing:**
- `MenuLoader` class provides full menu navigation: `requestRootMenuFrom()`,
  `requestPlaylistMenuFrom()`, `requestArtistMenuFrom()`, `requestSearchResultsFrom()`, etc.
- These query the player's dbserver for menu items (playlists, artists, albums, genres, etc.)
- BLT's `track_loader.clj` builds a UI on top of this, letting users browse the full
  media library on any connected player.

**Track loading to player:**
- `VirtualCdj.sendLoadTrackCommand(targetPlayer, rekordboxId, sourcePlayer, sourceSlot, sourceType)`
  sends a Pro DJ Link packet that tells a player to load a specific track.
- The track can come from any source player/slot on the network.
- This is how one could "queue songs on the deck from a computer without having a local copy"
  -- BLT browses Player 1's SD card via dbserver, then sends a load command telling Player 2
  to load a track from Player 1's SD slot.
- Special handling exists for XDJ-XZ (different packet format required).

**CrateDigger NFS access:**
- CrateDigger downloads the full database (`export.pdb` or `exportLibrary.db`) from
  any player's USB/SD via NFS.
- This gives access to the complete track listing, playlist structure, and metadata.
- For the XDJ-AZ specifically, it downloads `exportLibrary.db` (SQLite).

**Limitations:**
- CDJ-3000 cannot load "unanalyzed" (filesystem-only) tracks remotely.
- XDJ-XZ requires rekordbox on the network for load commands to work.
- No explicit limitation mentioned for XDJ-AZ, but this is new/experimental code.

---

## Question 3: BLT Player Status window implementation

### Answer: The Player Status window uses a comprehensive set of beat-link APIs.

**Source file:** `src/beat_link_trigger/players.clj`

**APIs used for each data element:**

| Data Element | beat-link API | Class |
|---|---|---|
| Waveform preview | `WaveformPreviewComponent(n)` | Swing component |
| Waveform detail (scrolling) | `WaveformDetailComponent(n)`, `.setScale()` | Swing component |
| Playback position | `TimeFinder.getInstance().getLatestPositionFor(n)` | `TrackPositionUpdate` |
| Beat position | `.getBeatWithinBar()` on `TrackPositionUpdate` | |
| Track metadata | `MetadataFinder.getInstance().getLatestMetadataFor(n)` | `TrackMetadata` |
| Album artwork | `ArtFinder.getInstance().getLatestArtFor(n)` | `AlbumArt` |
| Phrase analysis | `AnalysisTagFinder.getInstance().getLatestTrackAnalysisFor(n, ".EXT", "PSSI")` | `TaggedSection` |
| On-air status | `VirtualCdj.getInstance().getLatestStatusFor(n).isOnAir()` | `CdjStatus` |
| Playing state | `.isPlaying()` on `CdjStatus` | |
| Tempo/pitch | `.getEffectiveTempo()`, pitch from `DeviceUpdate` | |
| Sync status | `.isSynced()`, `.isBpmOnlySynced()` | |
| Tempo master | `.isTempoMaster()` | |

**Waveform rendering:**
- `WaveformDetailComponent` is a Swing component provided by beat-link that handles
  scrolling waveform display with current position indicator.
- Supports zoom via `.setScale(value)` (range 1-32).
- Mouse movement triggers cue/loop marker tooltips via `.toolTipText(Point)`.
- Phrase structure (mood/bank labels like "Intro 2", "Chorus 1") is overlaid from
  the PSSI analysis tag data.

**XDJ-AZ-specific handling in Player Status:**
- `(.isXdjAz device)` is checked for updating slot labels ("USB 1:", "USB 2:" etc.)
- Line 484: `(not (#{"CDJ-3000" "XDJ-AZ"} (.getDeviceName status)))` -- XDJ-AZ is
  explicitly excluded from "limited metadata" warnings, meaning BLT expects full
  metadata to be available from the XDJ-AZ.

**Opus Quad handling:**
- When `opus-quad?` is true, the UI shows metadata archive mount/unmount buttons
  instead of the normal dbserver-based metadata display.
- `OpusProvider.getInstance().attachMetadataArchive(file, slotNumber)` mounts archives.

---

## Implications for SCUE

### Bridge architecture reassessment needed

Our bridge (ADR-005) was designed around beat-link v8.0.0 assumptions. The v8.1.0-SNAPSHOT
changes significantly affect the DLP hardware story:

1. **XDJ-AZ dbserver works.** Unlike Opus Quad, the XDJ-AZ has a functioning dbserver.
   beat-link can query metadata, waveforms, and phrase analysis directly. Our bridge
   should be able to get all this data live, no metadata archives needed.

2. **NFS database download works for XDJ-AZ.** CrateDigger can download the full
   `exportLibrary.db` from the XDJ-AZ over NFS. This provides the ID translation
   layer needed to resolve the DLP ID mismatch.

3. **The DLP ID mismatch may be solved.** The v8.1.0-SNAPSHOT code downloads the
   SQLite database and uses it for track identification. The `canUseDatabase()` check
   requires `OpusProvider.usingDeviceLibraryPlus()` to be true, which requires a
   database key to be configured.

### What we should track

- **beat-link 8.1.0 release.** This is still a SNAPSHOT. When it releases, we should
  update our bridge JAR.
- **Database key requirement.** `OpusProvider.usingDeviceLibraryPlus()` returns true
  only when `databaseKey` is set (stored in Java Preferences). This key is needed to
  decrypt `exportLibrary.db`. BLT has a UI for entering this key. Our bridge would
  need equivalent configuration.
- **XDJ-AZ four-deck mode.** The commit message says "Starting work on XDJ-AZ
  four-deck support." The XDJ-AZ in four-deck mode may report as a single device with
  4 virtual decks (like the Opus Quad), or it may report differently. The
  `canSeeXdjAzInProDJLinkMode()` method in `BeatFinder` checks for channels-on-air
  packets, suggesting the XDJ-AZ has a non-Pro-DJ-Link mode too.

### Updated compatibility matrix

| Hardware | beat-link version | MetadataFinder | WaveformFinder | Phrase Analysis | Notes |
|---|---|---|---|---|---|
| CDJ-2000 / NXS | v8.0.0+ | WORKS | WORKS (blue) | N/A | Legacy, solid |
| CDJ-2000NXS2 | v8.0.0+ | WORKS | WORKS (RGB) | N/A | Legacy, solid |
| CDJ-3000 | v8.0.0+ | WORKS | WORKS (RGB+3band) | WORKS | Legacy, solid |
| XDJ-XZ | v8.0.0+ | WORKS | WORKS | WORKS | Treated as legacy CDJ pair |
| Opus Quad | v8.0.0+ | ARCHIVE ONLY | ARCHIVE ONLY | ARCHIVE ONLY | No dbserver at all |
| **XDJ-AZ** | **v8.1.0-SNAPSHOT** | **WORKS (dbserver)** | **WORKS (dbserver)** | **WORKS (dbserver)** | **Requires database key config** |
| OMNIS-DUO | unknown | UNTESTED | UNTESTED | UNTESTED | Likely similar to XDJ-AZ |
| CDJ-3000X | unknown | UNTESTED | UNTESTED | UNTESTED | Likely similar to XDJ-AZ |

---

## Sources

All findings are from direct source code inspection of the latest `main` branches:

- `beat-link` main branch (ahead of v8.0.0 by 31 commits)
- `beat-link-trigger` main branch (depends on beat-link 8.1.0-SNAPSHOT)
- GitHub API commit search and diff inspection

Key files examined:
- `VirtualCdj.java` lines 1155-1190: device detection, Opus Quad only
- `DeviceAnnouncement.java`: `isXdjAz`, `isUsingDeviceLibraryPlus` fields
- `OpusProvider.java`: `XDJ_AZ_NAME`, `usingDeviceLibraryPlus()`, `databaseKey`
- `CrateDigger.java`: `canUseDatabase()`, NFS download path, SQLite JDBC
- `BeatFinder.java`: `canSeeXdjAzInProDJLinkMode()`, channels-on-air detection
- `MetadataFinder.java`: Opus Quad guard (does NOT guard XDJ-AZ)
- `AnalysisTagFinder.java`: Opus Quad guard (does NOT guard XDJ-AZ)
- `dbserver/ConnectionManager.java`: port discovery, no XDJ-AZ block
- `beat_link_trigger/players.clj`: Player Status window, XDJ-AZ label handling
- `beat_link_trigger/track_loader.clj`: playlist browsing, track loading

Confidence: HIGH -- direct source code analysis of latest main branches.
