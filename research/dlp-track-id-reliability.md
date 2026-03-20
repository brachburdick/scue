# Research Findings: DLP Track ID Reliability & Reconciliation Strategy

## Questions Addressed
1. How stable is the DLP ID (`content.id` in rbox's OneLibrary) across USB re-exports, different USBs, and firmware updates?
2. When two USBs are used simultaneously, can DLP IDs collide? How does beat-link report which USB/slot a track is loaded from?
3. What reconciliation strategy is best to match a DLP-identified track to offline TrackAnalysis files?
4. For legacy hardware, do `getRekordboxId()` IDs have the same stability characteristics as DLP IDs?

---

## Findings

### Question 1: DLP ID Stability Across Re-exports, USBs, and Firmware

**Answer:** DLP IDs (`content.id` in `exportLibrary.db`) are **volatile across USB re-exports** and are **per-USB, not globally unique**. They are assigned by rekordbox desktop during the export process and can change whenever the collection is re-exported. They are stable within a single USB's lifetime (until re-export), but the same track exported to two different USBs will almost certainly have different DLP IDs.

**Detail:**

The DLP `exportLibrary.db` is a SQLite database written by rekordbox desktop during USB export. The `content.id` field is an auto-increment primary key within that database. Three scenarios:

**(a) USB re-export from rekordbox desktop:** When a DJ re-exports their collection to the same USB (full re-export, not incremental sync), rekordbox rebuilds the `exportLibrary.db` from scratch. The `content.id` values are reassigned based on the order tracks are written. If the DJ has added, removed, or reordered tracks in their collection since the last export, IDs shift. Even if the track list is identical, rekordbox does not guarantee ID stability across exports -- it is an internal database key, not a stable identifier. **Verdict: VOLATILE.**

**(b) Same track on different USBs:** Each USB gets its own independent `exportLibrary.db`. Track #47 on USB-A and track #47 on USB-B are unrelated records. A DJ who exports the same collection to two USBs may get different IDs for the same track depending on export order. **Verdict: NOT STABLE across USBs.**

**(c) Firmware updates:** DLP IDs are stored on the USB, not on the hardware. Firmware updates do not modify USB contents. The hardware reads the database as-is. **Verdict: NO IMPACT from firmware.**

**Key implication for SCUE:** The `track_ids` table in `TrackCache` (which maps `rekordbox_id -> fingerprint`) is valid only for the specific USB that was scanned. If the DJ re-exports, the mapping is stale and must be rebuilt via a new USB scan.

**Sources:**
- beat-link-trigger CHANGELOG and documentation: confirms DLP uses a separate ID namespace from DeviceSQL (HIGH)
- SCUE project PITFALLS.md: documents DLP ID namespace mismatch (HIGH)
- rbox `OneLibrary` API: `content.id` is the SQLite row ID in `exportLibrary.db` (HIGH, verified in codebase)
- Pioneer rekordbox behavior: re-export rebuilds the database (MEDIUM, based on community knowledge and rekordbox architecture -- not officially documented by Pioneer)

**Confidence:** MEDIUM-HIGH. The volatility across re-exports is based on understanding of rekordbox's export mechanism (rebuild vs. delta sync) and SQLite auto-increment behavior. Not lab-verified with controlled re-export testing. The per-USB independence is HIGH confidence (each USB has its own DB file).

---

### Question 2: Multi-USB DLP ID Collision & Slot Reporting

**Answer:** Yes, DLP IDs from different USBs **will collide**. USB-A track #47 and USB-B track #47 are almost certainly different tracks. beat-link reports the source USB via `CdjStatus.getTrackSourcePlayer()` and `CdjStatus.getTrackSourceSlot()`, which together form a disambiguation key.

**Detail:**

**Collision is guaranteed.** Each USB has its own `exportLibrary.db` with auto-increment IDs starting from 1. If a DJ has 500 tracks on each USB, IDs 1-500 exist on both. They are completely unrelated.

**beat-link slot reporting:** The SCUE bridge already extracts and emits these fields (see `BeatLinkBridge.handleCdjStatus()`):

```java
int srcPlayer = status.getTrackSourcePlayer();      // Which player's media is being used
String srcSlot = status.getTrackSourceSlot().name(); // "USB_SLOT", "SD_SLOT", "COLLECTION"
```

These are emitted in the `player_status` message as `track_source_player` (int) and `track_source_slot` (string: "usb", "sd", "cd", "collection").

**How it works in practice:**
- A CDJ-3000 or XDJ-AZ with a USB in slot 1 of player 1: `track_source_player=1, track_source_slot="usb"`
- A CDJ loading a track from player 2's USB: `track_source_player=2, track_source_slot="usb"`
- Opus Quad (4-deck all-in-one): each deck can load from any of 2 USB slots. `track_source_player` identifies which physical USB.

**The composite key for track identification is: `(track_source_player, track_source_slot, rekordbox_id)`**, not just `rekordbox_id` alone.

**Current SCUE bug:** The `track_ids` table uses `rekordbox_id INTEGER PRIMARY KEY` without slot disambiguation. This means a scan of USB-A followed by a scan of USB-B would overwrite the mapping. During a live set with two USBs, lookups using bare `rekordbox_id` will return wrong results for whichever USB was scanned second.

**Sources:**
- SCUE bridge source `BeatLinkBridge.java` line 543-546: extracts `getTrackSourcePlayer()` and `getTrackSourceSlot()` (HIGH, verified)
- SCUE `messages.py` `PlayerStatusPayload`: `track_source_player: int`, `track_source_slot: str` (HIGH, verified)
- beat-link `CdjStatus` API: `getTrackSourcePlayer()` returns the device number of the player whose media is loaded, `getTrackSourceSlot()` returns the `CdjStatus.TrackSourceSlot` enum (HIGH, from beat-link API design)
- Pioneer CDJ behavior: tracks can be loaded from any connected player's media slots (HIGH, standard DJ workflow)

**Confidence:** HIGH. The slot reporting fields exist and are already flowing through the bridge. The collision risk is a mathematical certainty (auto-increment keys in independent databases).

---

### Question 3: Reconciliation Strategy Evaluation

**Answer:** Use a **tiered strategy**: (b) file-path-stem matching as primary (already implemented), (a) title+artist as secondary (already implemented), with SHA256 hash verification as a post-match confirmation step when the original audio file is accessible. Option (c) waveform fingerprinting is not recommended at this stage.

**Detail:**

#### Option (a): DLP ID -> rbox title/artist -> fuzzy match

| Aspect | Assessment |
|--------|------------|
| Reliability | MEDIUM. Title/artist matching works for most tracks but fails on: remixes with similar names, tracks with Unicode normalization differences, featuring/vs. naming variants, DJ edits with appended "(Edit)" or "(Extended)" |
| Performance | FAST. String comparison against in-memory index. O(n) scan of analysis DB. |
| Edge cases | Same title by different artists (uncommon but possible). Compilations where artist is "Various". Tracks with no metadata. |
| Already implemented | Yes, in `usb_scanner.match_usb_tracks()` as Pass 2 (`title_artist` method). |

#### Option (b): DLP ID -> rbox file path -> derive original file -> SHA256 hash match

| Aspect | Assessment |
|--------|------------|
| Reliability | HIGH when the audio file is accessible. The file path on the USB (`content.path`) contains the original filename. SHA256 of the audio file is the canonical SCUE fingerprint. |
| Performance | SLOW for hash computation (~0.5-2s per file depending on size), but the path-stem match (without hashing) is instant. |
| Edge cases | Pioneer truncates long filenames during USB export. The USB file may be a re-encoded copy (different bitrate/format than original) -- SHA256 would NOT match even though it is the same track. |
| Already implemented | Partially. `usb_scanner.match_usb_tracks()` uses file path stem matching (Pass 1) but does NOT compute SHA256 hashes. |

**Critical caveat about SHA256:** The SCUE fingerprint is SHA256 of the *original audio file* on the DJ's computer. The file on the Pioneer USB may be a different format/bitrate (rekordbox can transcode during export). SHA256 of the USB copy will not match the original. This makes SHA256 a **verification tool only when the original file is still accessible**, not a primary match strategy from USB data.

#### Option (c): DLP ID -> ANLZ waveform fingerprint -> match

| Aspect | Assessment |
|--------|------------|
| Reliability | MEDIUM-HIGH in theory (waveform shape is content-dependent). But SCUE does not currently store ANLZ waveform data in TrackAnalysis, so there is nothing to match against. |
| Performance | Requires extracting waveform data from ANLZ files (already partially implemented), computing a similarity metric, and comparing against all stored analyses. Expensive and complex. |
| Edge cases | Different ANLZ file versions (DAT vs 2EX) may produce different waveform representations. No established standard for waveform-based matching. |
| Already implemented | No. Would require new infrastructure. |

#### Recommended Tiered Strategy

```
RECONCILIATION ALGORITHM (per USB scan):

For each track in exportLibrary.db:
  1. COMPOSITE KEY LOOKUP (instant):
     key = (source_player, source_slot, rekordbox_id)
     if key exists in track_ids table:
       return cached fingerprint  # Already linked from previous scan

  2. PATH STEM MATCH (instant):
     usb_stem = stem(content.path)  # e.g., "My Track Name"
     for each analysis in SCUE DB:
       if stem(analysis.audio_path) == usb_stem:
         LINK and return fingerprint
       if prefix_match(usb_stem, stem(analysis.audio_path)):
         LINK and return fingerprint  # Pioneer truncation case

  3. TITLE+ARTIST MATCH (instant):
     normalized_key = normalize(content.title) + "|" + normalize(artist.name)
     for each analysis in SCUE DB:
       if normalize(title) + "|" + normalize(artist) == normalized_key:
         LINK and return fingerprint

  4. UNMATCHED:
     Log as unmatched. Will require manual linking or on-demand
     analysis when the track is loaded on a deck.
```

```
LIVE RECONCILIATION (when track loads on deck):

  Input: player_status message with
    (track_source_player, track_source_slot, rekordbox_id)

  1. COMPOSITE KEY LOOKUP:
     key = (source_player, source_slot, rekordbox_id)
     fingerprint = track_ids.lookup(key)
     if found:
       return fingerprint  # Pre-scanned and linked

  2. USB DATABASE LOOKUP (if USB mounted):
     track_meta = rbox.get_content_by_id(rekordbox_id)
     Run PATH STEM MATCH and TITLE+ARTIST MATCH as above
     If matched, LINK the composite key for future lookups

  3. UNMATCHED:
     Fire "unknown_track" event. UI can display title/artist
     from rbox but SCUE analysis features are unavailable.
     Optionally trigger on-demand analysis if audio file
     is accessible.
```

**Sources:**
- SCUE `usb_scanner.py`: current implementation of path-stem and title+artist matching (HIGH, verified in codebase)
- SCUE `storage.py` `TrackCache.lookup_fingerprint()`: current single-key lookup (HIGH, verified)
- SCUE `fingerprint.py`: SHA256 of original audio file (HIGH, verified)

**Confidence:** HIGH for the tiered strategy recommendation. The path-stem and title+artist matching are already proven in the codebase. The composite key extension is a straightforward schema change.

---

### Question 4: Legacy DeviceSQL ID Stability vs DLP ID Stability

**Answer:** Legacy DeviceSQL IDs (from `export.pdb` on older Pioneer hardware) have **similar volatility characteristics** to DLP IDs -- they are per-USB auto-increment keys that can change on re-export. However, legacy hardware has an additional property: beat-link's `MetadataFinder` works correctly on legacy devices, meaning the bridge can directly provide title/artist/key metadata, removing the need for rbox-based USB scanning on those devices.

**Detail:**

**Legacy export format:** Older hardware (CDJ-2000NXS2, CDJ-3000, XDJ-1000MK2) uses the DeviceSQL format (`export.pdb`). The rekordbox ID in this format is also an auto-increment primary key, assigned during USB export. It has the same instability properties:
- Changes on full re-export
- Per-USB (not globally unique)
- Not affected by firmware updates

**Key difference:** On legacy hardware, beat-link's `MetadataFinder` and `CrateDigger` can query the device directly over Pro DJ Link and get correct metadata. The IDs are in the same namespace on both sides (DeviceSQL). This means:
- The bridge CAN provide title, artist, key, beatgrid, waveform, cue points, and phrase analysis
- rbox/pyrekordbox USB scanning is not required for metadata (though still useful for pre-scan matching)
- Track reconciliation can use metadata received via the bridge directly

**For SCUE's reconciliation:** The same tiered algorithm works for both legacy and DLP hardware. The difference is the *data source* for title/artist/path, not the algorithm:
- DLP hardware: metadata from rbox reading USB's `exportLibrary.db`
- Legacy hardware: metadata from beat-link `MetadataFinder` via the bridge, OR rbox reading USB's `export.pdb` (pyrekordbox supports both formats)

**Impact on `getRekordboxId()` in CdjStatus packets:** The value comes from the same byte offset in the Pro DJ Link status packet regardless of hardware generation. On DLP hardware it is a DLP-namespace ID; on legacy hardware it is a DeviceSQL-namespace ID. In both cases, it is the ID the device uses to reference the track in its database. The instability is in the database, not the packet.

**Sources:**
- SCUE PITFALLS.md: MetadataFinder works on legacy, fails on DLP (HIGH, documented)
- SCUE ADR-012: DLP path vs legacy path design (HIGH, project decision)
- beat-link architecture: `CdjStatus.getRekordboxId()` reads a fixed offset in the CDJ status packet, the value is whatever the player firmware puts there (HIGH, from beat-link source and SCUE bridge code)
- Pioneer export behavior: `export.pdb` uses a similar auto-increment key scheme to `exportLibrary.db` (MEDIUM, inferred from database format analysis)

**Confidence:** MEDIUM-HIGH. The packet-level behavior is well understood from the bridge implementation. The legacy ID volatility is inferred from the database format (auto-increment SQLite keys in `export.pdb`) rather than controlled testing.

---

## Stability Classification Summary

| ID / Field | Stable Within USB | Stable Across USBs | Stable Across Re-exports | Stable Across Firmware |
|------------|:-:|:-:|:-:|:-:|
| DLP `content.id` (rekordbox_id) | YES | NO | NO | YES |
| Legacy DeviceSQL rekordbox ID | YES | NO | NO | YES |
| `track_source_player` + `track_source_slot` | YES (per session) | N/A | N/A | YES |
| File path on USB (`content.path`) | YES | USUALLY* | NO** | YES |
| Title + Artist | YES | YES | YES | YES |
| SHA256 of original audio file | YES | YES | YES | YES |
| SHA256 of USB audio file | YES | YES | NO*** | YES |

\* Same if exported from same rekordbox library. Different if DJ reorganizes folders.
\** Path may change if DJ renames/moves files in rekordbox before re-export.
\*** rekordbox may transcode on export; even without transcoding, AAC container metadata may differ.

---

## Recommended Next Steps

1. **Schema change: composite key for `track_ids` table.** Replace `rekordbox_id INTEGER PRIMARY KEY` with `(source_player INTEGER, source_slot TEXT, rekordbox_id INTEGER)` as composite primary key. Update `TrackCache.lookup_fingerprint()` and `TrackCache.link_rekordbox_id()` to accept the composite key. This unblocks multi-USB support.

2. **Add USB identity tracking.** When scanning a USB, compute a lightweight identity (e.g., hash of the first N track IDs + titles, or the `exportLibrary.db` file modification timestamp). Store this alongside the scan results. On live deck load, compare the mounted USB identity against the last scan to detect stale mappings from re-exports.

3. **Add stale-scan detection.** When a live `player_status` arrives with a `rekordbox_id` that maps to a fingerprint, but the rbox metadata (title/artist) for that ID does not match the stored analysis metadata, flag it as a potential stale mapping. Log a warning and fall back to title+artist matching.

4. **Bridge enhancement for legacy hardware.** When the bridge detects non-DLP hardware, consider enabling `MetadataFinder` (currently disabled for all hardware per ADR-012). This would provide title/artist/key directly via the bridge, enabling reconciliation without USB scanning for legacy setups. This is a separate design decision (needs ADR amendment).

5. **Defer waveform fingerprinting (option c).** The tiered path-stem + title+artist strategy with composite keys is sufficient for the current milestone. Waveform fingerprinting adds complexity without clear benefit over the existing approach. Revisit if the match rate on real USB scans drops below ~90%.

6. **Test with controlled re-export.** Validate DLP ID volatility by exporting the same collection twice and comparing `content.id` values. This would upgrade the confidence level from MEDIUM-HIGH to HIGH.

## Skill File Candidates

The following findings should be added to `skills/pioneer-hardware.md`:

- DLP IDs and legacy DeviceSQL IDs are per-USB auto-increment keys, volatile across re-exports
- Multi-USB requires composite key: `(source_player, source_slot, rekordbox_id)`
- `CdjStatus.getTrackSourcePlayer()` and `getTrackSourceSlot()` disambiguate which USB a track is loaded from
- SHA256 of USB audio file may not match SHA256 of original (transcoding during export)
- Title+artist is the most stable metadata field for cross-USB matching

The composite key requirement and stale-scan detection should also be noted in `skills/beat-link-bridge.md` under Known Gotchas.
