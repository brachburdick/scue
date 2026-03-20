# Research Findings: Waveform Sources & Track ID Reliability

## Questions Addressed
1. What waveform data formats are stored in Pioneer ANLZ files?
2. Can SCUE read Pioneer ANLZ waveform data directly as an alternative to analysis-generated waveforms?
3. Does beat-link expose waveform data via its Java API?
4. On DLP hardware, what is the actual reliability of `rekordbox_id` from `CdjStatus.getRekordboxId()`?
5. What alternative track identification strategies exist beyond `rekordbox_id`?
6. Is there a way to get the file path of the currently playing track from beat-link on DLP hardware?
7. Should SCUE adopt deck-first, analysis-first, or hybrid data flow?

---

## Findings

### Question 1: Pioneer ANLZ Waveform Data Formats

**Answer:** Pioneer ANLZ files contain up to 7 waveform tags across three file variants (.DAT, .EXT, .2EX). Tags range from 100-entry monochrome thumbnails to full-resolution 3-band color waveforms at 150 entries/second. The most useful for SCUE are PWV5 (color detail in .EXT) and PWV7 (3-band detail in .2EX).

**Detail:**

#### File Variants
| File | Extension | Description | Hardware |
|------|-----------|-------------|----------|
| DAT | `.DAT` | Original analysis — all hardware | All Pioneer |
| EXT | `.EXT` | Extended — color waveforms, phrases | NXS2+, rekordbox 5+ |
| 2EX | `.2EX` | Double-extended — 3-band waveforms | CDJ-3000, XDJ-AZ, Opus Quad |

#### Waveform Tags

| Tag | File | Entries | Bytes/Entry | Encoding | Purpose |
|-----|------|---------|-------------|----------|---------|
| **PWAV** | .DAT | 400 (fixed) | 1 | 5-bit height (0-31), 3-bit whiteness | Monochrome preview — touch strip |
| **PWV2** | .DAT | 100 (fixed) | 1 | 4-bit height (0-15) | Tiny preview — CDJ-900 |
| **PWV3** | .EXT | Variable (150/sec) | 1 | 5-bit height, 3-bit whiteness | Monochrome detail — scrolling |
| **PWV4** | .EXT | 1,200 (fixed) | 6 | RGB color preview — complex encoding | Color preview — NXS2 overview |
| **PWV5** | .EXT | Variable (150/sec) | 2 | 3-bit R, 3-bit G, 3-bit B, 5-bit height (16-bit packed big-endian) | Color detail — scrolling waveform |
| **PWV6** | .2EX | 1,200 (fixed) | 3 | 1 byte each: mid, high, low frequency heights | 3-band preview — CDJ-3000 style |
| **PWV7** | .2EX | Variable (150/sec) | 3 | 1 byte each: mid, high, low frequency heights | 3-band detail — CDJ-3000 style |

**PWV5 bit layout (2 bytes, big-endian):**
```
Bit:  15 14 13 | 12 11 10 | 9  8  7 | 6  5  4  3  2 | 1  0
       R  R  R |  G  G  G | B  B  B | H  H  H  H  H | unused
```
- Red, Green, Blue: 3 bits each (0-7)
- Height: 5 bits (0-31)
- 2 low-order bits unused

**PWV7 byte layout (3 bytes):**
```
Byte 0: mid-range frequency height (0-255, display scale ×0.3)
Byte 1: high frequency height (0-255, display scale ×0.06)
Byte 2: low frequency height (0-255, display scale ×0.4)
```
CDJ-3000 renders these stacked with fixed colors:
- Low: dark blue `rgb(32, 83, 217)`, scale ×0.4
- Mid: amber `rgb(242, 170, 60)`, scale ×0.3
- High: white `rgb(255, 255, 255)`, scale ×0.06
- Overlap (low+mid): brown `rgb(169, 107, 39)`

Non-linear scaling; colors overlap where bands overlap.

**Resolution at 150 entries/second:** A 5-minute track has ~45,000 detail entries for PWV3/PWV5/PWV7 tags. A 7-minute track has ~63,000.

**PWVC tag:** Present in .2EX files. Format not fully documented in public sources. Likely related to CDJ-3000 waveform color metadata.

**Sources:**
- Deep Symmetry djl-analysis ANLZ specification: https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html (HIGH, primary reference)
- pyrekordbox ANLZ format docs: https://pyrekordbox.readthedocs.io/en/latest/formats/anlz.html (HIGH)
- Deep Symmetry crate-digger Kaitai Struct definition: https://github.com/Deep-Symmetry/crate-digger/blob/main/src/main/kaitai/rekordbox_anlz.ksy (HIGH)

**Confidence:** HIGH for PWAV, PWV2, PWV3, PWV5, PWV6, PWV7. MEDIUM for PWV4 (complex encoding not fully specified in public docs). LOW for PWVC (undocumented).

---

### Question 2: Can SCUE Read Pioneer ANLZ Waveforms Directly?

**Answer:** Yes. pyrekordbox can parse all documented waveform tags from .DAT, .EXT, and .2EX files. SCUE's existing `_try_pyrekordbox()` in `usb_scanner.py` already parses ANLZ files — extending it to read waveform tags is straightforward. The Pioneer waveform data is lower resolution than SCUE's current 60 FPS analysis-generated RGB waveform, but it provides instant availability without re-analysis.

**Detail:**

#### Resolution Comparison

| Source | Resolution | Color | Data Size (5-min track) | Generation Time |
|--------|-----------|-------|------------------------|-----------------|
| **SCUE analysis (librosa)** | 60 entries/sec (60 FPS) | RGB float (3×32-bit) per entry | ~18,000 entries × 12 bytes = ~216 KB | 3-8 seconds |
| **Pioneer PWV5 (.EXT)** | 150 entries/sec | 3-bit R/G/B + 5-bit height (2 bytes) | ~45,000 entries × 2 bytes = ~90 KB | 0 (pre-computed) |
| **Pioneer PWV7 (.2EX)** | 150 entries/sec | 3×8-bit frequency bands (3 bytes) | ~45,000 entries × 3 bytes = ~135 KB | 0 (pre-computed) |
| **Pioneer PWAV (.DAT)** | 400 entries total | Monochrome (1 byte) | 400 bytes | 0 (pre-computed) |

**Key observations:**
- Pioneer detail waveforms (PWV5/PWV7) are actually **higher temporal resolution** (150/sec) than SCUE's current analysis (60/sec).
- SCUE's RGB waveform has **higher color depth** (full RGB float per entry) vs Pioneer's 3-bit-per-channel encoding.
- Pioneer PWV7 (3-band) is the closest to what the Analysis Viewer renders — it separates low/mid/high frequency energy, which maps naturally to the RGB 3-band waveform SCUE already uses.
- **PWV7 is only available in .2EX files**, which are only generated by CDJ-3000, XDJ-AZ, Opus Quad, and recent rekordbox versions. Older hardware/exports only have PWV5 (color detail) or PWV3 (monochrome detail).

#### pyrekordbox API for waveform access

pyrekordbox's `AnlzFile` class can parse all waveform tags. The API:
```python
from pyrekordbox.anlz import AnlzFile

# Parse .EXT file for color waveforms
anlz_ext = AnlzFile.parse_file("ANLZ0000.EXT")
pwv5_tag = anlz_ext.get("color_waveform_detail")  # PWV5

# Parse .2EX file for 3-band waveforms
anlz_2ex = AnlzFile.parse_file("ANLZ0000.2EX")
pwv7_tag = anlz_2ex.get("waveform_3band_detail")  # PWV7
```

The tag names in pyrekordbox use descriptive strings:
- `"wf_preview"` → PWAV
- `"wf_detail"` → PWV3
- `"wf_color_preview"` → PWV4
- `"wf_color_detail"` → PWV5

**PWV6/PWV7 caveat:** pyrekordbox v0.4.4 parses PWV6/PWV7 at the binary level but does NOT have decoded `get()` methods for them. Raw bytes are available; decoding requires minimal numpy:
```python
import numpy as np
raw = pwv7_tag.content.entries  # raw bytes
data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)  # (N, 3) = mid/high/low
```

#### Feasibility for SCUE

SCUE could adopt a two-source waveform strategy:
1. **Pioneer ANLZ waveform** (instant, from USB scan): Available immediately when USB is scanned. Lower color depth but higher temporal resolution. Sufficient for Live Deck Monitor cursor tracking.
2. **SCUE analysis waveform** (3-8s latency, richer): Full RGB float precision. Better for the Analysis Viewer's inspection workflow. Generated on-demand or during batch analysis.

The Pioneer waveform is sufficient for display purposes. The SCUE analysis waveform adds value for frequency-aware visualization beyond what Pioneer's 3-bit color encoding can provide.

**Sources:**
- pyrekordbox docs: https://pyrekordbox.readthedocs.io/en/latest/formats/anlz.html (HIGH)
- pyrekordbox GitHub: https://github.com/dylanljones/pyrekordbox (HIGH)
- SCUE codebase `scue/layer1/usb_scanner.py` — existing ANLZ parsing infrastructure (HIGH, verified)

**Confidence:** HIGH for parsing feasibility. MEDIUM for exact pyrekordbox API method names (documentation is sparse on code examples; verify in source).

---

### Question 3: Beat-Link Waveform API

**Answer:** Beat-link has a full waveform API (`WaveformFinder`, `WaveformDetail`, `WaveformPreview`), but it **does not work on DLP hardware** (XDJ-AZ, Opus Quad, CDJ-3000X) because it depends on MetadataFinder/CrateDigger which use the wrong ID namespace on DLP devices. SCUE's bridge (v1.2.0) has already stripped all metadata finders per ADR-012. Beat-link's waveform API is effectively unusable for SCUE's target hardware.

**Detail:**

#### Beat-link Waveform Classes

| Class | Purpose | Data Format |
|-------|---------|-------------|
| `WaveformPreview` | Fixed-width overview | 400 segments, 0-31 height per segment, monochrome or NXS2 color |
| `WaveformDetail` | Scrolling detail view | Variable segments, similar encoding to ANLZ PWV3/PWV5 |
| `WaveformFinder` | Monitors track loads, fetches waveforms | Orchestrator — depends on MetadataFinder |
| `WaveformPreviewComponent` | Swing UI component | Java Swing — not useful for SCUE's React frontend |

#### Why it won't work on DLP

The dependency chain:
```
WaveformFinder
  → MetadataFinder (to know which track is loaded)
    → CrateDigger (to query the device's database)
      → DeviceSQL queries (BROKEN on DLP — wrong ID namespace)
```

On DLP hardware, CrateDigger sends DeviceSQL queries but the device responds with DLP-format data. The IDs don't match, so MetadataFinder returns wrong metadata, and WaveformFinder fetches waveforms for the wrong track.

This is the same root cause documented in LEARNINGS.md ("beat-link MetadataFinder returns wrong metadata on XDJ-AZ"). ADR-012 already addressed this by stripping all metadata finders from the bridge JAR.

#### Beat-link Playback Position

Beat-link provides two mechanisms for playback position:

1. **`CdjStatus.getBeatNumber()`** — returns the absolute beat count within the track. Available on ALL hardware including DLP. This is a raw packet field at bytes `a0-a3` in the CDJ status packet.

2. **`TimeFinder.getTimeFor(player)`** — returns interpolated millisecond position. **Depends on BeatGridFinder and MetadataFinder**, so it does NOT work on DLP hardware.

3. **CDJ-3000 precise position packets** — CDJ-3000 (and likely XDJ-AZ) send additional high-precision position data in 200-byte status packets. Beat-link 7.3+ can use these for "rock-solid tracking." However, accessing this data still goes through TimeFinder, which has the MetadataFinder dependency.

**TimeFinder position interpolation (for reference):**
TimeFinder works by: (1) on each beat packet, looking up exact ms position from beatgrid, (2) between beats, interpolating using wall-clock elapsed time × pitch × direction. CDJ-3000 sends "precise position packets" (~5 Hz) that give exact ms position even when paused/looping/scratching. `TrackPositionUpdate.precise = true` for these. All of this is DLP-blocked.

**SCUE's path for playback position on DLP:**
- Use `CdjStatus.getBeatNumber()` (reliable on all hardware) + SCUE's own beatgrid (from USB ANLZ parsing via pyrekordbox) to compute `playback_position_ms` on the Python side.
- Beat packets arrive at ~2.1 Hz at 128 BPM. Between beats, interpolate using `beat_time_ms + (elapsed_wall_time × effective_tempo / original_tempo)`.
- This avoids the MetadataFinder dependency entirely.
- The bridge already emits `beat_number` in `player_status` messages.
- Resolution: exact at each beat (~470ms intervals at 128 BPM), interpolated between beats. Sufficient for waveform cursor at debugging fidelity.

**Note on beat-link RGB encoding:** beat-link source code for `WaveformDetail.segmentColor()` returns `new Color(red, blue, green)` — red and blue may be swapped relative to the ANLZ spec. If SCUE parses PWV5 directly from ANLZ files (bypassing beat-link), use the ANLZ spec ordering: bits [15:13]=R, [12:10]=G, [9:7]=B.

**Sources:**
- beat-link WaveformPreview API: https://deepsymmetry.org/beatlink/apidocs/org/deepsymmetry/beatlink/data/WaveformPreview.html (HIGH)
- beat-link TimeFinder API: https://deepsymmetry.org/beatlink/apidocs/org/deepsymmetry/beatlink/data/TimeFinder.html (HIGH)
- beat-link CdjStatus API: https://deepsymmetry.org/beatlink/apidocs/org/deepsymmetry/beatlink/CdjStatus.html (HIGH)
- DJ Link packet analysis: https://djl-analysis.deepsymmetry.org/djl-analysis/vcdj.html (HIGH)
- SCUE LEARNINGS.md — MetadataFinder DLP failure (HIGH, verified)
- SCUE ADR-012 — bridge stripped of metadata finders (HIGH, verified)

**Confidence:** HIGH. The MetadataFinder dependency chain is confirmed in beat-link's API docs and SCUE's own experience. The beat number approach is verified in the SCUE bridge codebase.

---

### Question 4: `rekordbox_id` Reliability on DLP Hardware

**Answer:** `rekordbox_id` from `CdjStatus.getRekordboxId()` correlates with `exportLibrary.db` row IDs (`content.id`) on DLP hardware. It is **stable within a single USB's lifetime** (until re-export) but **volatile across re-exports** and **not unique across USBs**. It is stable within a performance session. This question was previously researched in `research/dlp-track-id-reliability.md` — this section summarizes and adds new findings.

**Detail:**

#### ID Namespace

| Hardware Type | Database Format | ID Source | ID in CdjStatus |
|--------------|----------------|-----------|-----------------|
| DLP (XDJ-AZ, Opus Quad, CDJ-3000X) | `exportLibrary.db` (SQLite) | `content.id` (auto-increment) | DLP namespace |
| Legacy (CDJ-2000NXS2, CDJ-3000) | `export.pdb` (DeviceSQL) | Row ID (auto-increment) | DeviceSQL namespace |

The value in `CdjStatus.getRekordboxId()` is read from bytes `2c-2f` of the CDJ status packet. The hardware writes whatever ID it uses internally — on DLP devices, this is the `exportLibrary.db` `content.id`.

#### Stability Matrix (from prior research, confirmed)

| Scenario | Stable? | Notes |
|----------|---------|-------|
| Within a single set (same USB, no re-export) | **YES** | ID never changes during a session |
| Across multiple sets (same USB, no re-export) | **YES** | USB database is read-only during playback |
| After USB re-export from rekordbox | **NO** | rekordbox rebuilds the database; IDs reassigned |
| Same track on different USBs | **NO** | Each USB has independent auto-increment IDs |
| After firmware update | **YES** | IDs are on USB, not hardware |

#### New Finding: XDJ-AZ Track Change Behavior

Per LEARNINGS.md, on XDJ-AZ, `trackType` does NOT transition through `NO_TRACK` when swapping tracks on the same deck. However, `rekordbox_id` DOES change reliably when a new track is loaded. This makes `rekordbox_id` change detection the primary track-change signal on DLP hardware.

#### Multi-USB Collision

Collision is guaranteed. Two USBs with 500 tracks each both have IDs 1-500. The composite key `(track_source_player, track_source_slot, rekordbox_id)` is required. The Live Deck Monitor spec already specifies this. The `track_ids` table migration to composite PK is a prerequisite.

**Sources:**
- SCUE `research/dlp-track-id-reliability.md` — comprehensive prior research (HIGH, verified)
- SCUE LEARNINGS.md — XDJ-AZ track change behavior (HIGH, verified)
- beat-link CdjStatus API: bytes 2c-2f for rekordbox_id (HIGH)
- DJ Link packet analysis: https://djl-analysis.deepsymmetry.org/djl-analysis/vcdj.html (HIGH)

**Confidence:** HIGH. Confirmed by prior SCUE research, bridge implementation, and beat-link documentation.

---

### Question 5: Alternative Track Identification Strategies

**Answer:** Five strategies evaluated below. The tiered approach already implemented in SCUE (composite key → path stem → title+artist) is the correct design. Audio fingerprinting (Chromaprint) is a viable future fallback but adds significant complexity and latency.

**Detail:**

#### (a) File Path from USB Metadata

| Aspect | Assessment |
|--------|------------|
| **How to obtain** | `content.path` field in `exportLibrary.db` via rbox `OneLibrary`. Already read in `usb_scanner.py`. |
| **Reliability** | HIGH for stem matching within one USB. Pioneer may truncate long filenames. Path changes if DJ reorganizes folders in rekordbox before re-export. |
| **Latency** | Instant (pre-scanned during USB scan step). |
| **Complexity** | LOW — already implemented as Pass 1 in `match_usb_tracks()`. |
| **Edge cases** | Pioneer truncates filenames >63 chars on some exports. Same filename in different folders. DJ renames file in rekordbox. Prefix matching (already implemented) handles truncation. |

**Confidence:** HIGH (verified in SCUE codebase).

#### (b) Title + Artist String Matching

| Aspect | Assessment |
|--------|------------|
| **How to obtain** | `content.title` and `artist.name` from `exportLibrary.db` via rbox. Already read in `usb_scanner.py`. |
| **Reliability** | MEDIUM-HIGH. Fails on: remixes with similar names, Unicode normalization differences, "feat." vs "ft." variants, "(Extended Mix)" vs "(Original Mix)" suffixes, compilation albums with "Various Artists". |
| **Latency** | Instant (pre-scanned). |
| **Complexity** | LOW — already implemented as Pass 2 in `match_usb_tracks()`. |
| **Edge cases** | Same title by different artists on same USB. Missing metadata. DJ edits with appended suffixes not in SCUE's analysis. |

**Confidence:** HIGH (verified in SCUE codebase).

#### (c) Audio Fingerprinting (Chromaprint / AcoustID)

| Aspect | Assessment |
|--------|------------|
| **How it works** | Chromaprint generates a compact fingerprint from audio's spectral characteristics. Matching is done locally against a pre-built fingerprint database (no internet required for local matching). |
| **Reliability** | HIGH for identifying the same recording regardless of format, bitrate, or minor processing. Robust against EQ, compression, format changes. |
| **Latency** | **Fingerprint generation:** ~0.5-2s per track (needs audio decoding first). Chromaprint typically processes 120 seconds of audio. **Matching:** Sub-millisecond against a local database. |
| **Complexity** | MEDIUM-HIGH. Requires: (1) `chromaprint` C library + `pyacoustid` Python bindings, (2) audio decoding pipeline (ffmpeg or audioread), (3) fingerprint database built during analysis, (4) query pipeline during live playback. |
| **Tempo handling** | Chromaprint does NOT handle tempo-shifted audio natively. A track played at +4% pitch will produce a different fingerprint. Workaround: normalize query audio to original tempo using pitch data from bridge (available even in degraded mode). |
| **When it adds value** | Guest DJ with unknown USB. Tracks not in SCUE's database. Degraded bridge mode (no metadata). |
| **Python libraries** | `pyacoustid` (wrapper around `chromaprint` + AcoustID web service), `chromaprint` (C lib, needs compilation or binary). |

**Comparison with Shazam-style constellation maps** (from `docs/FUTURE_AUDIO_FINGERPRINTING (1).md`):

| Feature | Chromaprint (chroma-based) | Constellation Map (Shazam-style) |
|---------|---------------------------|----------------------------------|
| Algorithm | 12-bin pitch class profiles over time | Spectrogram peak pairs with time deltas |
| Time-offset matching | NO — recording-level match only | YES — knows *where* in the track |
| Tempo robustness | Moderate (chroma preserved under key lock) | Poor without normalization |
| External deps | C library (libchromaprint) | None beyond numpy/scipy |
| SCUE fit | Simpler but no time-offset | Better long-term — time-offset matching is valuable for live position verification |

- Chromaprint identifies *which* recording is playing but not *where* in it. Constellation maps can determine both identity and playback offset from a short capture.
- For SCUE's current use case (matching USB file against pre-analyzed audio file), Chromaprint is simpler and sufficient.
- For future use cases (live audio capture → position verification when bridge position is unavailable), constellation maps are superior.

**Confidence:** MEDIUM-HIGH. Chromaprint capabilities are well-documented. Latency estimates are based on general community reports, not SCUE-specific benchmarks.

#### (d) ANLZ File Hash

| Aspect | Assessment |
|--------|------------|
| **How it works** | Hash the ANLZ .DAT file content (or specific waveform tag data) and match against hashes generated during analysis. |
| **Reliability** | LOW-MEDIUM. ANLZ files are generated by rekordbox during export and may differ between exports (different rekordbox versions, re-analysis). The waveform data within a tag SHOULD be deterministic for the same audio, but this is unverified. |
| **Latency** | Instant (file read + hash during USB scan). |
| **Complexity** | LOW — hash computation is trivial. |
| **Edge cases** | ANLZ files may not exist for all tracks (unanalyzed tracks). Different ANLZ versions across hardware may produce different data. No ANLZ file to compare against during offline SCUE analysis (SCUE doesn't generate ANLZ files). |
| **Fundamental problem** | SCUE's offline analysis doesn't produce ANLZ files, so there's nothing to match against. This strategy only works if SCUE stores Pioneer ANLZ waveform hashes during USB scan AND during prior scans — it becomes a "have I seen this exact USB data before?" check, not a "is this the same track?" check. |

**Confidence:** MEDIUM. The approach is sound in theory but has a fundamental bootstrapping problem.

#### Recommended Tiered Strategy (unchanged from prior research)

```
1. Composite key lookup: (source_player, source_slot, rekordbox_id) → fingerprint
2. Path stem match: USB file stem → analysis file stem
3. Title + artist match: normalized string comparison
4. [Future] Chromaprint match: audio fingerprint comparison
5. Unmatched: fire unknown_track event, offer on-demand analysis
```

**Sources:**
- SCUE `research/dlp-track-id-reliability.md` — prior reconciliation strategy evaluation (HIGH)
- SCUE `scue/layer1/usb_scanner.py` — existing matching implementation (HIGH, verified)
- Chromaprint: https://acoustid.org/chromaprint (HIGH)
- pyacoustid: https://github.com/beetbox/pyacoustid (HIGH)
- SCUE `docs/FUTURE_AUDIO_FINGERPRINTING (1).md` — Shazam-style design doc (HIGH)

**Confidence:** HIGH for the tiered strategy. MEDIUM-HIGH for Chromaprint performance estimates.

---

### Question 6: File Path Retrieval from Beat-Link on DLP Hardware

**Answer:** Beat-link's MetadataFinder CAN return file path metadata, but on DLP hardware it returns the **wrong track's metadata** (same root cause as title/artist). The file path CANNOT be reliably obtained from beat-link on DLP. However, it CAN be obtained by reading the USB's `exportLibrary.db` using the `rekordbox_id` from CdjStatus.

**Detail:**

#### Via beat-link (NOT viable on DLP)

`MetadataFinder.getLatestMetadataFor(player)` returns a `TrackMetadata` object that includes the file path. On DLP hardware, this returns metadata for the wrong track because the ID namespace mismatch causes CrateDigger to look up the wrong record. This is the same failure mode documented in LEARNINGS.md.

#### Via rbox + exportLibrary.db (VIABLE)

The `content.path` field in `exportLibrary.db` contains the file path on the USB. Given a `rekordbox_id` from `CdjStatus.getRekordboxId()`:

```python
from rbox import OneLibrary

db = OneLibrary("/path/to/PIONEER/exportLibrary.db")
content = db.get_content_by_id(rekordbox_id)
file_path = content.path  # e.g., "/Contents/Music/Artist/Track.mp3"
```

This requires the USB to be mounted on the SCUE computer. The path is relative to the USB root.

#### Via pyrekordbox (alternative)

pyrekordbox can also read `exportLibrary.db` and provides similar access to file paths. However, SCUE currently uses rbox for database reading (per ADR-013: rbox for DB, pyrekordbox for ANLZ).

#### Timing Consideration

The USB database lookup is instant (SQLite query). The constraint is that the USB must be mounted and scanned before the live set. If SCUE has already scanned the USB (via `usb_scanner.py`), the file path is cached in the `pioneer_metadata` table and available without re-reading the USB.

**Sources:**
- SCUE LEARNINGS.md — MetadataFinder DLP failure (HIGH, verified)
- SCUE `scue/layer1/usb_scanner.py` — already reads `content.path` (HIGH, verified)
- SCUE `scue/layer1/storage.py` — `pioneer_metadata` table stores `file_path` (HIGH, verified)
- rbox `OneLibrary` API (HIGH, used in SCUE codebase)

**Confidence:** HIGH. Both the failure mode (beat-link) and the workaround (rbox) are verified in the SCUE codebase.

---

### Question 7: Deck-First vs Analysis-First Data Flow

**Answer:** Three approaches exist with distinct tradeoff profiles. The SCUE codebase already implements a hybrid approach that combines the strengths of both. The key architectural question is whether to add on-demand analysis (deck-first fallback) for unknown tracks.

**Detail:**

#### Option A: Analysis-First (pre-analyze all tracks from USB)

```
USB mounted → scan exportLibrary.db → analyze every track → store TrackAnalysis JSONs
At showtime: deck loads track → composite key lookup → instant waveform + analysis
```

| Dimension | Assessment |
|-----------|------------|
| **Prep time** | HIGH. 500 tracks × 5s avg = ~42 minutes. Must be done before the set. |
| **Live latency** | ZERO. All data is pre-computed and cached. |
| **Completeness** | 100% — every track on the USB has analysis data. |
| **Wasted work** | HIGH. DJ may play only 20-40 tracks from a 500-track USB. ~92-96% of analysis is unused. |
| **UX** | Requires a "preparation" step. DJ must plug USB into SCUE computer first. |
| **Failure modes** | If the DJ brings a track not on the pre-scanned USB (Spotify, streaming), no analysis available. |

#### Option B: Deck-First (analyze on demand when track loads)

```
At showtime: deck loads track → resolve ID → check if analysis exists
  If yes: instant waveform + analysis
  If no: trigger on-demand analysis (3-8s delay)
```

| Dimension | Assessment |
|-----------|------------|
| **Prep time** | ZERO. No preparation step required. |
| **Live latency** | 3-8 seconds for first load of each track. Subsequent loads are instant (cached). |
| **Completeness** | Only analyzed tracks have data. First play of each track has a gap. |
| **Wasted work** | ZERO. Only played tracks are analyzed. |
| **UX** | Seamless for pre-analyzed tracks. Brief loading state for new tracks. |
| **Failure modes** | On-demand analysis requires audio file access. If the original audio isn't accessible (USB-only copy, different format), analysis fails. |
| **Gap coverage** | Layer 2 can use beat-reactive defaults (strobe on downbeat, color cycle per bar) during the 3-8s analysis window. Pioneer waveform data from ANLZ files provides instant visual even without SCUE analysis. |

#### Option C: Hybrid (pre-link + on-demand analysis)

```
Pre-set: USB scan → link rekordbox_id → fingerprint (but DON'T re-analyze)
  Tracks with existing analysis: instant availability
  Tracks without analysis: flagged as "linkable but unanalyzed"

At showtime: deck loads track → composite key lookup
  If linked + analyzed: instant waveform + analysis
  If linked + NOT analyzed: show Pioneer ANLZ waveform immediately, trigger on-demand analysis in background
  If NOT linked: attempt title+artist match, then on-demand analysis if audio accessible
```

| Dimension | Assessment |
|-----------|------------|
| **Prep time** | LOW. USB scan + linking takes ~10-30 seconds for 500 tracks (no audio analysis). |
| **Live latency** | Zero for pre-analyzed tracks. 3-8s for unanalyzed tracks, with Pioneer waveform as immediate fallback. |
| **Completeness** | Grows over time. Each set adds analyses for newly played tracks. |
| **Wasted work** | MINIMAL. Only analyzes tracks that are actually played. |
| **UX** | Best of both worlds. Pre-scanned tracks resolve instantly. Unknown tracks get Pioneer ANLZ waveform immediately and SCUE analysis after a brief delay. |
| **Pioneer ANLZ waveform as bridge** | During the 3-8s analysis window, the Live Deck Monitor can display the PWV7 (3-band) or PWV5 (color) waveform from the USB ANLZ files. This gives the DJ immediate visual feedback without waiting for SCUE analysis. |

#### Tradeoff Matrix

| Dimension | Analysis-First | Deck-First | Hybrid |
|-----------|---------------|------------|--------|
| Prep time | 42+ min | 0 | ~30 sec |
| Live latency (pre-analyzed) | 0 | 0 | 0 |
| Live latency (new track) | 0 | 3-8s | 3-8s (with Pioneer waveform fallback) |
| Wasted computation | ~95% | 0% | ~0% |
| Coverage | 100% USB | Played only | Played + pre-linked |
| Requires audio file access | During prep | During set | During set (for new tracks) |
| Pioneer waveform fallback | Not needed | Useful | Useful |

#### What the SCUE codebase already implements

The current architecture is closest to **Hybrid**:
- `usb_scanner.py` scans the USB and links `rekordbox_id` → `fingerprint` (pre-set step)
- `storage.py` caches Pioneer metadata including beatgrid and cues
- Analysis pipeline generates `TrackAnalysis` JSONs (can be run batch or on-demand)
- The Live Deck Monitor spec includes "Analyzing track..." empty state for on-demand analysis

What's **NOT yet implemented**:
- On-demand analysis triggered by deck load event
- Pioneer ANLZ waveform rendering as a fallback during analysis
- The 3-8s gap coverage using beat-reactive defaults

**Sources:**
- SCUE `scue/layer1/usb_scanner.py` — current USB scan + linking (HIGH, verified)
- SCUE `specs/feat-FE-live-deck-monitor/spec.md` — "Analyzing track..." state, hybrid data flow (HIGH, verified)
- SCUE `docs/ARCHITECTURE.md` — Layer 1A/1B architecture (HIGH, verified)

**Confidence:** HIGH for tradeoff analysis. The hybrid approach is already partially implemented and validated by the existing architecture.

---

## Recommended Next Steps

1. **Extend USB scanner to read Pioneer waveform data.** Add PWV5 (color detail) and PWV7 (3-band detail) parsing to `_try_pyrekordbox()` in `usb_scanner.py`. Store the raw waveform bytes in `pioneer_metadata` or a new `pioneer_waveforms` table. This provides instant waveform data for the Live Deck Monitor without waiting for SCUE analysis.

2. **Implement Python-side playback position computation.** Use `beat_number` from `player_status` messages + SCUE's beatgrid (from Pioneer ANLZ via USB scan) to compute `playback_position_ms`. This avoids dependency on beat-link's TimeFinder (which doesn't work on DLP). Add this to the bridge adapter or a new Layer 1B module.

3. **Complete `track_ids` table migration to composite primary key.** Already specified in the Live Deck Monitor spec. This is a prerequisite for multi-USB support and should be prioritized.

4. **Add Pioneer waveform rendering path to WaveformCanvas.** The `WaveformCanvas` component should accept either SCUE analysis waveform data OR Pioneer ANLZ waveform data. When SCUE analysis is unavailable but Pioneer data exists, render the Pioneer waveform as a fallback.

5. **Defer Chromaprint integration.** The tiered strategy (composite key → path stem → title+artist) is sufficient for the current milestone. Chromaprint adds value only for guest-DJ / unknown-USB scenarios, which are post-M11.

6. **Verify pyrekordbox waveform tag API names.** The exact method signatures for accessing PWV5/PWV7 data through pyrekordbox need verification against the library source code (documentation is sparse).

7. **Benchmark on-demand analysis latency.** If the hybrid data flow is adopted, measure actual analysis time on the target Mac hardware to validate the 3-8s estimate and determine if Pioneer waveform fallback provides adequate coverage.

## Skill File Candidates

The following findings should be distilled into permanent skill files:

### `skills/pioneer-anlz-waveforms.md` (NEW)
- ANLZ file variants (.DAT, .EXT, .2EX) and which hardware generates each
- Complete waveform tag reference (PWAV through PWV7): resolution, encoding, byte layout
- pyrekordbox API for reading waveform tags
- Resolution comparison: Pioneer ANLZ vs SCUE analysis waveforms
- PWV5 bit-packing format (16-bit: 3R/3G/3B/5H/2unused)
- PWV7 byte layout (mid/high/low frequency heights)

### `skills/beat-link-bridge.md` (UPDATE — add Known Gotchas)
- WaveformFinder/TimeFinder do NOT work on DLP hardware (same MetadataFinder dependency)
- `CdjStatus.getBeatNumber()` works on ALL hardware — use for playback position computation
- CDJ-3000 precise position packets exist but are accessed via TimeFinder (DLP-blocked)
- Playback position on DLP must be computed Python-side from beat_number + beatgrid

### `skills/pioneer-hardware.md` (UPDATE — add waveform section)
- Which ANLZ file variants (.DAT, .EXT, .2EX) each hardware generation produces
- CDJ-3000/XDJ-AZ/Opus Quad generate .2EX files with PWV7 3-band waveforms
- Older NXS2 hardware generates .EXT files with PWV5 color waveforms only
