# Research Findings: WaveformFinder Hardware Compatibility

## Questions Addressed
1. Does `WaveformFinder.requestWaveformDetailFrom(player)` succeed on CDJ-2000 (original) and CDJ-2000NXS?
2. Does WaveformFinder work on XDJ-XZ? Which metadata path does it use?
3. For DLP-only hardware, can WaveformFinder be selectively re-enabled while keeping MetadataFinder off?
4. What does pyrekordbox expose for waveform data from ANLZ files? Could we read waveforms from USB as fallback?

## Compatibility Matrix

| Hardware | MetadataFinder | WaveformFinder (via dbserver) | WaveformFinder (via OpusProvider archive) | USB ANLZ Waveform (pyrekordbox) |
|---|---|---|---|---|
| CDJ-2000 (original) | WORKS | WORKS (blue only) | N/A | WORKS |
| CDJ-2000NXS | WORKS | WORKS (blue only) | N/A | WORKS |
| CDJ-2000NXS2 | WORKS | WORKS (blue + RGB) | N/A | WORKS |
| CDJ-3000 | WORKS | WORKS (blue + RGB + 3-band) | N/A | WORKS |
| XDJ-1000 / XDJ-1000MK2 | WORKS | WORKS | N/A | WORKS |
| XDJ-XZ | WORKS | WORKS | N/A | WORKS |
| Opus Quad | BROKEN (no dbserver) | BROKEN (no dbserver) | WORKS (with archive) | WORKS |
| XDJ-AZ | WORKS (v8.1.0-SNAPSHOT, dbserver) | WORKS (v8.1.0-SNAPSHOT, dbserver) | WORKS (v8.1.0-SNAPSHOT) | WORKS | **SEE: findings-xdj-az-blt-metadata-2026-03.md** |
| OMNIS-DUO | BROKEN (DLP ID mismatch) | BROKEN (DLP ID mismatch) | UNTESTED | WORKS |
| CDJ-3000X | BROKEN (DLP ID mismatch) | BROKEN (DLP ID mismatch) | UNTESTED | WORKS |

## Findings

### Question 1: CDJ-2000 (original) and CDJ-2000NXS

**Answer:** WaveformFinder works on both CDJ-2000 (original, non-NXS) and CDJ-2000NXS. These are legacy hardware that uses `export.pdb` (DeviceSQL) and supports the standard dbserver protocol. The only limitation is waveform style: pre-NXS2 hardware only supports blue-and-white waveforms (WaveformStyle.BLUE), not RGB or 3-band.

**Detail:**

WaveformFinder retrieves waveforms through one of two paths:

1. **MetadataProvider path** (e.g., OpusProvider with metadata archive): checks `MetadataFinder.getInstance().allMetadataProviders.getWaveformDetail()` first.
2. **dbserver protocol path** (direct query to player): sends `ANLZ_TAG_REQ` or `WAVE_DETAIL_REQ` messages to the player's dbserver, passing the `rekordboxId` from the `DataReference`.

For CDJ-2000 and CDJ-2000NXS, the dbserver path works correctly because:
- These devices expose a dbserver port
- They use DeviceSQL IDs, which match the `rekordboxId` reported in `CdjStatus`
- The ANLZ tag request uses the same rekordboxId that MetadataFinder uses; on legacy hardware, this ID is in the correct DeviceSQL namespace

WaveformFinder tries RGB waveform first (via `ANLZ_FILE_TAG_COLOR_WAVEFORM_DETAIL` in .EXT files), falls back to blue (via `WAVE_DETAIL_REQ` in .DAT files). Pre-NXS2 hardware returns `UNAVAILABLE` for RGB requests, so WaveformFinder falls back to blue automatically. This is correct and handled.

The beat-link CHANGELOG confirms CDJ-2000 support: version 0.3.2 added handling for "waveform (or waveform preview) being unavailable" for pre-nexus players (CDJ-900 or CDJ-2000).

**Sources:**
- beat-link `WaveformFinder.java` (v8.0.0 main branch), `getWaveformDetail()` method: shows the RGB-then-blue fallback logic. Relevance: HIGH
- beat-link `WaveformFinder.java`, `getWaveformPreview()` method: same fallback pattern for previews. Relevance: HIGH
- beat-link CHANGELOG.md, v0.3.2 entry: "handle the case of a waveform (or waveform preview) being unavailable. Also handle the case of the request having been sent by a pre-nexus player (CDJ-900 or CDJ-2000)." Relevance: HIGH

**Confidence:** HIGH — Source code confirms the mechanism. CDJ-2000 and NXS are well-established legacy hardware with known dbserver support. Beat-link has been tested with these devices for years.

---

### Question 2: XDJ-XZ behavior

**Answer:** WaveformFinder works on XDJ-XZ. The XDJ-XZ uses the legacy `export.pdb` (DeviceSQL) metadata path despite being a newer device. beat-link does NOT classify it as `isUsingDeviceLibraryPlus`. It has a standard dbserver, and WaveformFinder queries succeed.

**Detail:**

Key evidence from the beat-link source code:

1. **`DeviceAnnouncement.java`** (line 61): `isUsingDeviceLibraryPlus = isOpusQuad || isXdjAz;` — the XDJ-XZ is NOT in this list. Only Opus Quad and XDJ-AZ are flagged as DLP devices. The XDJ-XZ reports a different device name and is treated as standard Pro DJ Link hardware.

2. **`OpusProvider.java`**: only defines `OPUS_NAME = "OPUS-QUAD"` and `XDJ_AZ_NAME = "XDJ-AZ"` as recognized DLP device names. The XDJ-XZ is not recognized as a DLP device.

3. **beat-link CHANGELOG**: Version 0.5.0 added "Support for the XDJ-XZ, which reports multiple devices on a single [IP address]" and issue #39 confirms the XDJ-XZ works as a multi-device Pro DJ Link participant (it reports as 2 CDJs + 1 mixer from one IP). The fix was handling multiple devices per IP, not any DLP-specific issue.

4. **XDJ-XZ metadata path**: While the XDJ-XZ hardware may support both `export.pdb` and `exportLibrary.db` on its USB drives, it implements the standard Pro DJ Link dbserver protocol. When beat-link queries it, it responds to DeviceSQL-style requests normally. This is because the XDJ-XZ's firmware uses the legacy protocol stack for network communication, regardless of which database format the USB uses internally.

5. **beat-link-trigger issue #91** ("Loading a track on a player doesn't work for XDJ-XZ") was about player loading, not metadata retrieval — and was resolved.

The XDJ-XZ is effectively treated identically to a CDJ-2000NXS2 pair + DJM mixer from beat-link's perspective.

**Sources:**
- beat-link `DeviceAnnouncement.java` line 61: DLP flag only set for Opus Quad and XDJ-AZ. Relevance: HIGH
- beat-link `OpusProvider.java` lines 46-56: only two DLP device names defined. Relevance: HIGH
- beat-link issue #39: XDJ-XZ support added as standard multi-device handling. Relevance: HIGH
- beat-link CHANGELOG v0.5.0: XDJ-XZ treated as standard Pro DJ Link. Relevance: HIGH

**Confidence:** HIGH — Source code directly confirms the XDJ-XZ is not treated as a DLP device. Multiple beat-link users have used XDJ-XZ with beat-link-trigger successfully.

---

### Question 3: Selectively re-enabling WaveformFinder on DLP hardware

**Answer:** No, WaveformFinder CANNOT be selectively re-enabled for DLP-only hardware (XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X) while keeping MetadataFinder off. WaveformFinder has a hard dependency on MetadataFinder and uses the same rekordboxId for dbserver queries, so it suffers from the exact same DLP ID namespace mismatch.

**Detail:**

There are two distinct problems for DLP hardware, and they affect WaveformFinder differently:

**Problem A: Opus Quad has no dbserver at all.**
The Opus Quad does not implement the dbserver protocol. `MetadataFinder.requestMetadataInternal()` explicitly checks `DeviceAnnouncement.isOpusQuad` and returns null. `WaveformFinder` would similarly fail because `ConnectionManager.invokeWithClientSession()` would throw when trying to connect to a nonexistent dbserver. beat-link's workaround is the `OpusProvider` with metadata archives — this provides waveforms from pre-created archive files, not live from the device.

**Problem B: XDJ-AZ (and CDJ-3000X, OMNIS-DUO) has a dbserver but uses DLP IDs.**
These devices have a functioning dbserver, but `CdjStatus.getRekordboxId()` returns a DLP-namespace ID. When this ID is used in a dbserver query (which operates in the DeviceSQL namespace), the query retrieves the **wrong record** — a different track's waveform.

WaveformFinder is affected by Problem B because:

1. **WaveformFinder.start() explicitly starts MetadataFinder**: Line 1098 of `WaveformFinder.java`: `MetadataFinder.getInstance().start();`. WaveformFinder cannot run without MetadataFinder.

2. **WaveformFinder is driven by MetadataFinder updates**: The `metadataListener` receives `TrackMetadataUpdate` events from MetadataFinder. Without MetadataFinder running, WaveformFinder's `pendingUpdates` queue never gets populated, so no automatic waveform fetching occurs.

3. **The rekordboxId used for waveform queries comes from the same CdjStatus**: `MetadataFinder` constructs a `DataReference` using `update.getRekordboxId()` (line 1038). `WaveformFinder` uses the `trackReference` from the metadata update, which carries the same `rekordboxId`. The `getWaveformDetail()` method sends `new NumberField(rekordboxId)` to the dbserver — the same ID that causes wrong metadata lookups also causes wrong waveform lookups.

4. **Even manual `requestWaveformDetailFrom()` calls would fail**: If you construct a `DataReference` manually with the DLP ID and call `requestWaveformDetailFrom()`, the dbserver would return the waveform for whatever DeviceSQL track happens to have that numeric ID — which is NOT the currently playing track.

In summary: WaveformFinder and MetadataFinder share the same fundamental problem on DLP hardware. The ID namespace mismatch corrupts waveform lookups identically to metadata lookups. ADR-012's decision to disable WaveformFinder alongside MetadataFinder was correct, not collateral damage.

**The one exception** is the `OpusProvider` path: if a metadata archive is attached (as documented in beat-link-trigger's OpusQuad.adoc), the `allMetadataProviders.getWaveformDetail()` call in `requestDetailInternal()` can serve waveforms from the archive. But this requires:
- A pre-created metadata archive file
- The archive to be mounted/attached before use
- For DLP devices with encrypted `exportLibrary.db`, the database key must be provided

This archive approach is what beat-link-trigger uses for Opus Quad. It has NOT been tested/documented for XDJ-AZ, OMNIS-DUO, or CDJ-3000X, though the mechanism should work if the archive can be created and the PSSI-based or DLP-ID-based track matching succeeds.

**Sources:**
- beat-link `WaveformFinder.java` line 1098: `MetadataFinder.getInstance().start()` — hard dependency. Relevance: HIGH
- beat-link `WaveformFinder.java` `metadataListener` field: waveforms only fetched in response to metadata updates. Relevance: HIGH
- beat-link `WaveformFinder.java` `getWaveformDetail()`: uses `rekordboxId` for dbserver ANLZ_TAG_REQ. Relevance: HIGH
- beat-link `MetadataFinder.java` line 1038: `DataReference` constructed from `update.getRekordboxId()`. Relevance: HIGH
- beat-link `WaveformFinder.java` `requestDetailInternal()`: checks MetadataProvider first (archive path), then falls through to dbserver. Relevance: HIGH
- beat-link-trigger `OpusQuad.adoc`: documents metadata archive approach as workaround for devices without dbserver or with DLP IDs. Relevance: HIGH
- beat-link `DeviceAnnouncement.java`: `isUsingDeviceLibraryPlus` flag set for Opus Quad and XDJ-AZ. Relevance: HIGH

**Confidence:** HIGH — Direct source code analysis of both WaveformFinder and MetadataFinder confirms they share the same ID path. The DLP ID mismatch affects all dbserver queries equally.

---

### Question 4: pyrekordbox waveform data from ANLZ files

**Answer:** pyrekordbox fully supports reading waveform data from ANLZ files on USB drives. It handles 7 waveform tag types (PWAV, PWV2, PWV3, PWV4, PWV5, PWV6, PWV7) plus PWVC. This provides a complete USB-based fallback path for all hardware, including DLP devices.

**Detail:**

pyrekordbox's `AnlzFile.parse_file()` supports the following waveform tags:

| Tag | Name | File | Description | Data Format |
|---|---|---|---|---|
| PWAV | wf_preview | .DAT | Blue waveform preview (small overview) | height + intensity arrays |
| PWV2 | wf_tiny_preview | .DAT | Tiny waveform preview | height + intensity arrays |
| PWV3 | wf_detail | .EXT | Blue waveform detail (full scrollable) | height + intensity arrays |
| PWV4 | wf_color | .EXT | Color (RGB) waveform preview | heights + color + blue arrays |
| PWV5 | wf_color_detail | .EXT | Color (RGB) waveform detail | heights + RGB color arrays |
| PWV6 | (unnamed) | .2EX | 3-band waveform (CDJ-3000 style) | Structure TBD |
| PWV7 | (unnamed) | .2EX | 3-band waveform detail | Structure TBD |

**Usage for SCUE's fallback path:**

```python
from pyrekordbox.anlz import AnlzFile

# Parse the ANLZ file from USB
anlz = AnlzFile.parse_file("/path/to/PIONEER/USBANLZ/P016/0000875E/ANLZ0000.EXT")

# Get color waveform detail (PWV5) — NXS2+ hardware
wf_detail = anlz.get("wf_color_detail")  # Returns (heights, colors) numpy arrays
# heights: shape (N,), normalized 0-1
# colors: shape (N, 3), RGB values

# Get blue waveform detail (PWV3) — all hardware
wf_detail_blue = anlz.get("wf_detail")  # Returns (heights, intensities) numpy arrays

# Get waveform preview (PWAV) — all hardware
wf_preview = anlz.get("wf_preview")  # Returns (heights, intensities) numpy arrays
```

**ANLZ file location on USB:** The path to each track's ANLZ files is stored in the database:
- **Legacy (export.pdb):** `content.path` in the track's ANLZ path field
- **DLP (exportLibrary.db):** `content.analysis_data_file_path` via rbox's `OneLibrary`

The ANLZ files on a USB drive contain the identical waveform data that the dbserver would serve over the network. Reading from USB is a complete replacement for the dbserver waveform path.

**Coverage for DLP hardware:** DLP devices (XDJ-AZ, Opus Quad) create ANLZ files in the same format. pyrekordbox can parse them (with the 4/2022 caveat about ~0.2% failure rate on some DLP ANLZ files, handled by the custom fallback parser per ADR-013). The waveform tags specifically (PWAV/PWV3/PWV4/PWV5) have not been reported to have parsing issues — the ADR-013 failures were in the PQTZ beat grid section.

**Sources:**
- pyrekordbox `anlz/tags.py` (v0.4.4+): PWAV, PWV2, PWV3, PWV4, PWV5, PWV6, PWV7, PWVC tag implementations with parsing logic. Relevance: HIGH
- pyrekordbox `anlz/tags.py` TAGS dict (line 530-534): all waveform tags registered. Relevance: HIGH
- ADR-013 in project DECISIONS.md: pyrekordbox is already the primary ANLZ parser for SCUE. Relevance: HIGH
- ANLZ_PARSER_RESEARCH.md: documents pyrekordbox's ANLZ support and the ~0.2% failure rate. Relevance: HIGH

**Confidence:** HIGH — pyrekordbox source code directly confirms waveform tag support. SCUE already uses pyrekordbox for ANLZ parsing (ADR-013). The waveform tags use the same parsing infrastructure.

---

## Summary of Key Architectural Insight

**WaveformFinder and MetadataFinder share the same ID vulnerability.** Both use the `rekordboxId` from `CdjStatus` to query the dbserver. On DLP hardware, this ID is in the wrong namespace. ADR-012's blanket disabling of all Finder classes for DLP hardware was architecturally correct.

The correct path for waveforms on DLP hardware is the same path SCUE already uses for other ANLZ data: **read ANLZ files directly from USB via pyrekordbox**. This provides all waveform formats (blue, RGB, 3-band) without any dependency on the dbserver or MetadataFinder.

For legacy hardware (CDJ-2000, NXS, NXS2, CDJ-3000, XDJ-XZ), WaveformFinder works correctly via the dbserver. However, reading from USB via pyrekordbox is equally viable and more consistent — it provides a single code path for all hardware types.

## Recommended Next Steps

1. **Do NOT re-enable WaveformFinder for DLP hardware.** The ID mismatch would return wrong waveforms. ADR-012 was correct.

2. **Add USB ANLZ waveform reading to the USB scanner.** Extend the existing pyrekordbox ANLZ parsing (which already reads PQTZ beat grids and PCOB cues) to also extract waveform data from PWAV, PWV3, PWV4, and PWV5 tags. Store alongside other enrichment data in the track analysis JSON.

3. **Use the USB waveform path for ALL hardware.** Rather than maintaining two waveform paths (dbserver for legacy, USB for DLP), use USB ANLZ reading as the universal waveform source. This eliminates the need to ever enable WaveformFinder in the bridge and simplifies the architecture.

4. **If live waveform streaming is needed later** (e.g., for tracks not on USB), consider enabling WaveformFinder in the bridge ONLY for legacy hardware (when `uses_dlp: false` in the device_found message). This would be an optimization, not a requirement.

5. **Update ADR-012** to document why WaveformFinder specifically cannot be re-enabled for DLP hardware, referencing this research.

## Skill File Candidates

The finding that WaveformFinder depends on MetadataFinder and shares its ID vulnerability should be added to `skills/beat-link-bridge.md` under Known Gotchas:

```
### WaveformFinder has the same DLP ID mismatch as MetadataFinder
WaveformFinder.start() explicitly starts MetadataFinder and is driven by MetadataFinder
updates. Waveform dbserver queries use the same rekordboxId that causes wrong metadata
lookups on DLP hardware. WaveformFinder CANNOT be selectively re-enabled for DLP devices.
Use USB ANLZ waveform reading (pyrekordbox PWAV/PWV3/PWV4/PWV5 tags) instead.
```

The pyrekordbox waveform tag inventory (PWAV through PWV7) should be added to a pyrekordbox skill file or to `docs/bridge/PITFALLS.md` under the pyrekordbox section.
