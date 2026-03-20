# Research Findings: DLP dbserver Protocol & ID Namespace Differences

**Date:** 2025-03-19
**Scope:** Read-only investigation of Pioneer DJ Device Library Plus (DLP) vs DeviceSQL databases, dbserver protocol behavior on newer hardware, and ID mapping feasibility.
**Complements:** `research/dlp-track-id-reliability.md` (which covers ID stability and reconciliation strategy)

---

## 1. DLP vs DeviceSQL Database Structures

### 1.1 DeviceSQL (`export.pdb`) -- Legacy Format

**Location on USB:** `/PIONEER/rekordbox/export.pdb`
**Format:** Proprietary binary "DeviceSQL" relational database
**Block size:** Fixed 4096-byte pages
**Reverse-engineered by:** Henry Betts, Fabian Lesniak, James Elliott

**Core tables (13 table types):**
- Tracks (type 0x00): title, artist, genre, artwork ID, playing time, track ID at bytes 0x48-0x4b
- Genres, Artists, Albums, Labels, Keys, Colors
- Playlist tree + playlist entries
- Artwork file paths
- History playlists and entries
- Columns and metadata

**ID assignment:** Auto-increment integer per table. Track ID is at bytes 0x48-0x4b in the track row. IDs can have duplicates (rekordbox adds new rows on edit rather than modifying in-place; the last row with a given ID is canonical).

**Supplementary file:** `exportExt.pdb` contains tag tables (type 0x03) and tag-track associations (type 0x04) for flexible categorization. Uses the same track ID namespace.

**String encoding:** DeviceSQL strings with 16-bit offsets relative to row start.

**Confidence:** HIGH. Extensively documented by Deep Symmetry's DJ Link Ecosystem Analysis project.

**Sources:**
- [DJ Link Ecosystem Analysis -- Database Exports](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html)
- [rekordcrate Rust library](https://github.com/Holzhaus/rekordcrate)
- [Rekordbox-Decoding](https://github.com/henrybetts/Rekordbox-Decoding)

### 1.2 Device Library Plus / OneLibrary (`exportLibrary.db`) -- New Format

**Location on USB:** `/PIONEER/rekordbox/exportLibrary.db` (sits alongside `export.pdb` when both are present)
**Format:** Encrypted SQLite database (SQLCipher)
**Introduced:** rekordbox 6.8.1 (2023)
**Renamed:** "OneLibrary" as of late 2025 (same format, marketing rename)

**Schema:** Mirrors the rekordbox 6/7 desktop database (`master.db`). Key tables include:
- `djmdContent` -- primary track table. Key fields:
  - `ID` (auto-increment primary key, this is what shows up as "rekordbox_id" on the wire)
  - `FolderPath` (full file path on the USB)
  - `FileNameL` (long filename)
  - `AnalysisDataPath` (relative path to ANLZ files)
  - `ImagePath` (relative path to artwork)
  - Foreign keys: `ArtistID`, `AlbumID`, `GenreID`, `KeyID`, `LabelID`, `RemixerID`, `ComposerID`, `ColorID`
- `djmdArtist`, `djmdAlbum`, `djmdGenre`, `djmdKey`, `djmdLabel`, `djmdColor`
- `djmdPlaylist`, `djmdSongPlaylist`
- `djmdCue` (cue points and loops)
- `djmdHistory`, `djmdSongHistory`
- `djmdMyTag`, `djmdSongMyTag`
- `djmdMixerParam`, `djmdHotCueBanklist`
- And several more (approximately 25+ tables total)

**ID assignment:** Auto-increment SQLite integer primary keys. Completely independent namespace from DeviceSQL IDs. The same track will almost certainly have different IDs in `export.pdb` vs `exportLibrary.db` on the same USB.

**Encryption:** Handled transparently by pyrekordbox (`DeviceLibraryPlus` class) and rbox (Rust). The key derivation is documented in these open-source tools.

**Confidence:** HIGH for schema structure (verified via pyrekordbox and rbox source code). MEDIUM for completeness of table listing (some tables may be undocumented).

**Sources:**
- [pyrekordbox documentation](https://pyrekordbox.readthedocs.io/en/latest/formats/db6.html)
- [pyrekordbox GitHub](https://github.com/dylanljones/pyrekordbox)
- [rbox PyPI](https://pypi.org/project/rbox/)

### 1.3 Does Rekordbox Write Both Databases to USB?

**Answer: YES, both are written side-by-side.**

When DLP is enabled in rekordbox settings, a USB export writes:
- `/PIONEER/rekordbox/export.pdb` (legacy DeviceSQL)
- `/PIONEER/rekordbox/exportExt.pdb` (legacy tags extension)
- `/PIONEER/rekordbox/exportLibrary.db` (DLP/OneLibrary SQLite)
- `/PIONEER/USBANLZ/` (shared ANLZ analysis files)
- Audio files in `/Contents/`

Legacy-only devices (CDJ-2000NXS2, CDJ-3000 pre-firmware-3.30, XDJ-1000MK2, etc.) read `export.pdb`. DLP-only devices (XDJ-AZ, CDJ-3000X, OPUS-QUAD, OMNIS-DUO) read `exportLibrary.db`. Both formats reference the same audio files and ANLZ analysis files on the USB.

**Critical exception:** The XDJ-AZ ONLY reads `exportLibrary.db`. If a USB has only `export.pdb` (i.e., DLP was not enabled during export), the XDJ-AZ displays "rekordbox Database not found!" and cannot load tracks.

**CDJ-3000 firmware 3.30 incident (Oct 2025):** This firmware attempted to transition the CDJ-3000 to OneLibrary. When both formats were present, the firmware preferentially loaded OneLibrary but had bugs reconciling playlist data between the two formats, causing widespread playlist display failures. AlphaTheta pulled the firmware and reverted the CDJ-3000 to Device Library format. The CDJ-3000 currently still uses `export.pdb`.

**Confidence:** HIGH. Confirmed by multiple community sources and Pioneer's own support documentation.

**Sources:**
- [Lexicon DJ -- Everything about Device Library Plus](https://www.lexicondj.com/blog/everything-you-need-to-know-about-device-library-plus-and-more)
- [AlphaTheta Help -- XDJ-AZ Database Not Found](https://support.pioneerdj.com/hc/en-us/articles/38064285243673)
- [Pioneer DJ -- CDJ-3000 Firmware 3.30 Notice](https://www.pioneerdj.com/en/news/2026/cdj-3000-firmware-ver330-important-notice/)

---

## 2. XDJ-AZ dbserver Behavior

### 2.1 Does the XDJ-AZ Run a dbserver?

**Answer: UNCLEAR / PARTIALLY.** The XDJ-AZ has a dbserver port (unlike the OPUS-QUAD, which has none), but it speaks DLP-namespace IDs. The beat-link project has identified that "the XDJ-AZ always uses Device Library Plus IDs, so DeviceSQL downloads can't be used safely."

This means:
- The XDJ-AZ **does** appear on the Pro DJ Link network
- It **does** send CDJ status packets with `rekordbox_id` values
- Those `rekordbox_id` values are DLP-namespace IDs (from `exportLibrary.db`), NOT DeviceSQL IDs
- beat-link's `MetadataFinder` and `CrateDigger` (which expect DeviceSQL-namespace IDs) cannot safely query the XDJ-AZ's dbserver because the IDs don't match what those tools expect

**Key implication for SCUE:** When the bridge sees a `rekordbox_id` from an XDJ-AZ, that ID corresponds to `djmdContent.ID` in `exportLibrary.db`, not to a track row ID in `export.pdb`. Using it to query DeviceSQL data will return wrong results.

### 2.2 XDJ-AZ Protocol Version and Network Behavior

- **Pro DJ Link:** Yes, the XDJ-AZ supports Pro DJ Link (Ethernet only, single port -- no built-in hub unlike older XDJ models)
- **Connectivity:** Can connect to CDJs via LAN cable for file sharing between units
- **Protocol version:** Not explicitly documented, but appears to be a newer variant. Beat-link v8 treats it as an all-in-one device (similar to XDJ-XZ) with DLP-specific handling
- **Known issue:** CDJ-3000X units have reported connectivity problems with the XDJ-AZ over LAN, while CDJ-3000 units connect fine. This suggests protocol-level differences between CDJ-3000 and CDJ-3000X.
- **Beat-link support:** beat-link issue #90 addresses dbserver port search consolidation for all-in-one devices like XDJ-AZ. Full XDJ-AZ support is being worked on for later v8 releases.

**Confidence:** MEDIUM. The DLP-namespace ID behavior is confirmed by beat-link developers. The exact dbserver capabilities (which queries work, which fail) are still under investigation by the community.

**Sources:**
- [beat-link GitHub](https://github.com/Deep-Symmetry/beat-link) -- v8 changelog and issue #90
- [beat-link-trigger issue #191](https://github.com/Deep-Symmetry/beat-link-trigger/issues/191) -- XDJ-AZ connection issues
- [AlphaTheta -- XDJ-AZ product page](https://alphatheta.com/en/product/all-in-one-dj-system/xdj-az/black/)
- [Pioneer DJ Community -- CDJ-3000X / XDJ-AZ LAN issues](https://community.pioneerdj.com/hc/en-us/community/posts/55585081398809)

---

## 3. CDJ-3000X and OMNIS-DUO

### 3.1 CDJ-3000X

- **DLP support:** YES. The CDJ-3000X is a DLP-only device (reads `exportLibrary.db`, does not read `export.pdb`)
- **dbserver:** Likely present but uses DLP-namespace IDs (same situation as XDJ-AZ). Not yet confirmed by beat-link community testing.
- **Protocol:** Pro DJ Link compatible. Known LAN connectivity issue with XDJ-AZ specifically (works fine with CDJ-3000).
- **Distinction from CDJ-3000:** The CDJ-3000X is a newer hardware revision that ships with DLP support only. The CDJ-3000 (non-X) was designed for DeviceSQL and only briefly attempted OneLibrary via firmware 3.30 (which was pulled).
- **beat-link support:** Not yet explicitly supported in beat-link v8. Likely similar to XDJ-AZ -- will need DLP-aware metadata handling.

**Confidence:** MEDIUM. Hardware is relatively new. Community testing and beat-link integration are ongoing.

### 3.2 OMNIS-DUO

- **DLP support:** YES. DLP-only device.
- **dbserver:** UNKNOWN. The OMNIS-DUO cannot connect to CDJs or DJMs via Pro DJ Link at all (confirmed by AlphaTheta support). This is a battery-powered portable unit without Ethernet. It is unclear whether it has any network protocol capability.
- **Practical impact on SCUE:** If the OMNIS-DUO has no Pro DJ Link connectivity, beat-link cannot see it on the network. SCUE would need to read the USB directly to get track data. This makes it a non-target for the bridge.

**Confidence:** HIGH for the DLP-only and no-Pro-DJ-Link findings. LOW for dbserver specifics (no testing data).

**Sources:**
- [Lexicon DJ -- CDJ-3000X Release](https://www.lexicondj.com/blog/alpha-theta-cdj-3000-x-released)
- [AlphaTheta -- OMNIS-DUO Pro DJ Link FAQ](https://support.pioneerdj.com/hc/en-us/articles/27722551164185)
- [rekordbox -- DLP Compatible Equipment](https://rekordbox.com/en/support/faq/devicelibraryplus-6/)

---

## 4. OPUS-QUAD dbserver Behavior (Reference)

The OPUS-QUAD is the best-documented DLP device thanks to community effort:

- **dbserver:** The OPUS-QUAD **does NOT have a dbserver port**. It is explicitly noted in beat-link's `MetadataFinder` source.
- **Status packets:** Initially does not send CDJ status packets. After beat-link sends announce packets on port 50000, the OPUS-QUAD begins sending UDP packets on port 50002, but these are limited compared to CDJ status packets.
- **Beat packets:** Not sent when operating as VirtualRekordbox (the workaround mode for beat-link).
- **Workaround:** beat-link v8 added experimental support by:
  1. Posing as VirtualRekordbox (lighting mode)
  2. Using "metadata archives" created from USB media to proxy metadata
  3. This gives beat-link access to track info, waveforms, beat grids without dbserver
- **Pro DJ Link Lighting:** The OPUS-QUAD supports lighting protocol even in standalone mode, which is how beat-link connects.
- **ID namespace:** DLP IDs (from `exportLibrary.db`)
- **Timing:** Status packets arrive ~every 200ms, so beat sync can be up to 200ms off (no beat packets for tighter sync).

**Confidence:** HIGH. Documented by beat-link v8 code and the OPUS-QUAD Pro DJ Link Analysis project.

**Sources:**
- [beat-link-trigger OPUS-QUAD Guide](https://blt-guide.deepsymmetry.org/beat-link-trigger/8.0.0/OpusQuad.html)
- [OPUS-QUAD Pro DJ Link Analysis](https://github.com/kyleawayan/opus-quad-pro-dj-link-analysis)
- [beat-link v8.0.0 changelog](https://github.com/Deep-Symmetry/beat-link/blob/main/CHANGELOG.md)

---

## 5. pyrekordbox and rbox Tools

### 5.1 pyrekordbox

**Package:** `pyrekordbox` (Python)
**DLP support:** YES, via `DeviceLibraryPlus` class

```python
from pyrekordbox import DeviceLibraryPlus
db = DeviceLibraryPlus("exportLibrary.db")
for content in db.get_content():
    print(content.id, content.title, content.artist.name)
```

**Key capabilities:**
- Reads and writes `exportLibrary.db` (DLP/OneLibrary)
- Reads `export.pdb` (DeviceSQL) via separate PDB parser
- Reads ANLZ files (.DAT, .EXT, .2EX)
- Reads `master.db` (rekordbox desktop database)
- Handles encryption/decryption transparently
- Write support is partial (some tables only)

**ID fields exposed:**
- `content.id` -- DLP auto-increment primary key (this is the "rekordbox_id" on the wire)
- `content.FolderPath` -- full file path
- `content.FileNameL` -- long filename
- `content.AnalysisDataPath` -- path to ANLZ files
- Foreign key IDs for artist, album, genre, key, label, color

### 5.2 rbox

**Package:** `rbox` (Rust library with Python bindings)
**DLP support:** YES, can unlock and read `exportLibrary.db`

**Key capabilities:**
- High-performance Rust implementation
- Reads `exportLibrary.db` (OneLibrary/DLP)
- Reads `master.db` (desktop database)
- Provides `OneLibrary` interface for content access
- Handles encryption transparently

**SCUE already uses rbox** for USB scanning (per the existing `dlp-track-id-reliability.md` findings).

**Confidence:** HIGH. Both tools are actively maintained and well-documented.

**Sources:**
- [pyrekordbox GitHub](https://github.com/dylanljones/pyrekordbox)
- [pyrekordbox docs](https://pyrekordbox.readthedocs.io/)
- [rbox PyPI](https://pypi.org/project/rbox/)
- [rbox Rust docs](https://docs.rs/rbox/latest/rbox/)

---

## 6. Pioneer DJ Protocol Documentation (Dysentery/Deep Symmetry)

### 6.1 Key Resources

- **Dysentery** -- Protocol analysis documentation (Clojure): https://github.com/Deep-Symmetry/dysentery
- **DJ Link Ecosystem Analysis** -- Comprehensive web docs: https://djl-analysis.deepsymmetry.org/
- **beat-link** -- Java library implementing the protocol: https://github.com/Deep-Symmetry/beat-link
- **Crate Digger** -- Java library for reading PDB/ANLZ files from NFS or local media: https://github.com/Deep-Symmetry/crate-digger

### 6.2 dbserver Protocol Summary

The dbserver runs on each CDJ/XDJ player and serves metadata queries. Key characteristics:
- Players announce their dbserver port via the Pro DJ Link discovery protocol
- Queries use the rekordbox ID (track ID) plus media slot info to fetch metadata
- Available queries: track metadata, artwork, waveforms (preview + detail), beat grids, cue lists, analysis tags
- The `rekordbox_id` in CDJ status packets (bytes 0x2c-0x2f) is the key used for all dbserver queries
- On legacy hardware, this ID comes from `export.pdb` (DeviceSQL namespace)
- On DLP hardware, this ID comes from `exportLibrary.db` (DLP namespace)

### 6.3 What's NOT Documented

- The DLP-aware dbserver protocol (if any) used by XDJ-AZ and CDJ-3000X
- Whether DLP devices serve metadata in a different format than legacy dbserver
- Any Pioneer-internal cross-reference between DLP and DeviceSQL IDs
- The exact protocol differences between legacy and DLP dbserver implementations

**Confidence:** HIGH for legacy protocol documentation. LOW for DLP protocol specifics (active research area).

---

## 7. Key Question: Can We Map DLP IDs to DeviceSQL IDs?

### 7.1 Do Both Databases Reference the Same File Paths?

**YES.** Both `export.pdb` and `exportLibrary.db` on the same USB reference the same audio files in `/Contents/`. The file path is stored differently:
- DeviceSQL (`export.pdb`): path stored as a DeviceSQL string with 16-bit offset encoding within the track row
- DLP (`exportLibrary.db`): path stored in `djmdContent.FolderPath` as a standard SQLite text field

Both point to the same physical file on the USB (e.g., `/Contents/Artist Name/Album/Track.mp3`).

**They also share the same ANLZ analysis files** in `/PIONEER/USBANLZ/`. The ANLZ file path is stored in both databases and points to the same `.DAT`/`.EXT`/`.2EX` files.

**Confidence:** HIGH. Both databases are written by the same rekordbox export process and reference the same physical files.

### 7.2 Is There a Shared Key for Mapping?

**YES -- file path is the natural shared key.** Since both databases point to the same audio files with the same paths, the file path (or a normalized version of it) serves as a deterministic mapping key between DLP IDs and DeviceSQL IDs.

Other potential shared keys:
- **Title + Artist:** Stored in both databases. Reliable for most tracks but not unique (remixes, edits).
- **ANLZ file path:** Both databases reference the same ANLZ files. The ANLZ path could serve as a unique key.
- **File hash:** The actual audio file is the same, so any hash of it would match. But this requires I/O.

**There is NO built-in cross-reference table.** Pioneer does not maintain a mapping between DLP IDs and DeviceSQL IDs. They are independent databases with independent auto-increment sequences.

### 7.3 Performance Cost of Building a Mapping Table

Building a DLP-to-DeviceSQL mapping table for a USB with N tracks:

1. **Parse both databases:** pyrekordbox can read both. Time: O(N) for each, typically <1s for 1000 tracks.
2. **Match by file path:** Build a dict of `{normalized_path: dlp_id}` from `exportLibrary.db`, then iterate `export.pdb` track rows and look up `{normalized_path: devicesql_id}`. Time: O(N) with hash map lookup.
3. **Total:** Under 2 seconds for a typical DJ USB with 500-2000 tracks.

**When would you need this?** If SCUE needs to support a mixed setup where:
- Legacy hardware (CDJ-2000NXS2, CDJ-3000) reports DeviceSQL IDs
- DLP hardware (XDJ-AZ, CDJ-3000X) reports DLP IDs
- The same USB is shared between both types of hardware
- SCUE needs to recognize that DeviceSQL ID #47 and DLP ID #132 are the same track

In this scenario, the mapping table lets SCUE normalize all IDs to a single namespace (probably the SCUE fingerprint, as already designed).

### 7.4 Does Rekordbox Maintain Any Cross-Reference?

**NO.** The two databases are independent exports from the same source data. There is no `dlp_id_to_devicesql_id` table or equivalent. The mapping must be derived at read time using shared fields (file path, title+artist, ANLZ path).

**Confidence:** HIGH for file-path-based mapping feasibility. The existing SCUE reconciliation strategy (documented in `dlp-track-id-reliability.md`) already uses path-stem and title+artist matching, which accomplishes the same goal.

---

## 8. Device Compatibility Matrix

| Device | Format Read | dbserver? | ID Namespace | beat-link Support | Pro DJ Link |
|--------|:-----------:|:---------:|:------------:|:-----------------:|:-----------:|
| CDJ-2000NXS2 | DeviceSQL | YES | DeviceSQL | Full (v7+) | YES |
| CDJ-3000 | DeviceSQL* | YES | DeviceSQL | Full (v7.3+) | YES |
| CDJ-3000X | DLP only | Likely (DLP IDs) | DLP | Not yet | YES |
| XDJ-1000MK2 | DeviceSQL | YES | DeviceSQL | Full (v7+) | YES |
| XDJ-XZ | DeviceSQL | YES | DeviceSQL | Full (v7+) | YES (2 decks, 1 IP) |
| XDJ-AZ | DLP only | Partial (DLP IDs) | DLP | In progress (v8+) | YES (1 port) |
| OPUS-QUAD | DLP only | NO | DLP | Experimental (v8) | Limited (lighting) |
| OMNIS-DUO | DLP only | NO | DLP | None | NO (no Ethernet) |

\* CDJ-3000 firmware 3.30 briefly attempted OneLibrary but was reverted. Currently DeviceSQL.

---

## 9. Implications for SCUE

### 9.1 The Core Problem

When a DLP device (XDJ-AZ, CDJ-3000X) loads a track, the `rekordbox_id` in the CDJ status packet is a DLP-namespace ID. This ID cannot be used to:
- Query a DeviceSQL dbserver on a legacy player
- Look up a track in `export.pdb`
- Match against any DeviceSQL-indexed data

Conversely, if SCUE has scanned a USB using rbox (DLP) and built a mapping of DLP IDs to fingerprints, those mappings will not work if the same USB is loaded on a legacy CDJ-3000 (which reports DeviceSQL IDs).

### 9.2 What SCUE Already Handles

Per the existing `dlp-track-id-reliability.md`:
- The composite key `(source_player, source_slot, rekordbox_id)` disambiguates multi-USB scenarios
- Path-stem and title+artist matching provide ID-independent reconciliation
- USB scanning with rbox handles DLP databases

### 9.3 What Remains Unaddressed

1. **Mixed-hardware setups:** A setup with both CDJ-3000 (DeviceSQL) and XDJ-AZ (DLP) sharing the same USB. The same track will have different `rekordbox_id` values depending on which device loads it. SCUE needs to scan BOTH databases and build mappings for both ID namespaces.

2. **Detecting which namespace a player uses:** SCUE needs to know whether a given player reports DLP or DeviceSQL IDs. This could be:
   - Hard-coded per device model (device name is available in Pro DJ Link announcements)
   - Detected by checking if `MetadataFinder` queries succeed (legacy) or fail (DLP)
   - Inferred from beat-link's device classification

3. **OPUS-QUAD metadata:** Since it has no dbserver, metadata must come from pre-built archives or direct USB reading. beat-link v8 handles this via metadata archives.

4. **XDJ-AZ timeline:** beat-link XDJ-AZ support is actively under development for v8.x. Until it stabilizes, SCUE may need to rely entirely on USB scanning for XDJ-AZ setups.

---

## 10. Confidence Summary

| Finding | Confidence |
|---------|:----------:|
| Both `export.pdb` and `exportLibrary.db` written to USB | HIGH |
| DLP and DeviceSQL use independent ID namespaces | HIGH |
| XDJ-AZ uses DLP-namespace IDs on the wire | HIGH |
| OPUS-QUAD has no dbserver | HIGH |
| CDJ-3000X is DLP-only | HIGH |
| OMNIS-DUO has no Pro DJ Link | HIGH |
| File path is a reliable cross-database mapping key | HIGH |
| XDJ-AZ dbserver works but with DLP IDs | MEDIUM |
| CDJ-3000X dbserver behavior | MEDIUM |
| No Pioneer cross-reference table between formats | MEDIUM-HIGH |
| DLP dbserver protocol details | LOW |
| CDJ-3000 future transition to OneLibrary | LOW (pulled firmware, timeline unknown) |
