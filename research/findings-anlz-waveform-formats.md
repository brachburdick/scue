# Research Findings: Pioneer ANLZ Waveform Data Formats

## Questions Addressed
1. What are the Pioneer ANLZ waveform-related tags (PWAV, PWV2, PWV3, PWV4, PWV5, PWV6, PWV7), their resolutions, byte layouts, color encodings, file locations, and hardware compatibility?
2. Does pyrekordbox support parsing all these waveform tags, and what API does it expose?
3. How do Pioneer ANLZ waveform resolutions compare to a custom 60fps RGB analysis waveform from librosa?

---

## Findings

### Question 1: Pioneer ANLZ Waveform Tag Specifications

**Answer:** There are 7 waveform tags across 3 file types (.DAT, .EXT, .2EX). They range from 100-entry tiny previews to variable-length detail waveforms at 150 entries/second. Color encoding progresses from monochrome blue/white (PWAV/PWV2/PWV3) to packed RGB (PWV4/PWV5) to 3-band frequency separation (PWV6/PWV7).

**Detail:**

#### Tag-by-Tag Specifications

##### PWAV -- Waveform Preview (Monochrome)
- **File:** .DAT
- **FourCC:** `0x50574156` ("PWAV")
- **Header length:** 20 bytes (0x14)
- **Resolution:** Fixed 400 entries (400 columns of waveform overview)
- **Bytes per entry:** 1
- **Total data size:** 400 bytes
- **Byte layout per entry:** Single byte, bit-packed:
  - Bits [4:0] (5 low-order bits): height (0-31 pixels)
  - Bits [7:5] (3 high-order bits): whiteness/intensity (0-7, higher = whiter/less saturated blue)
- **Color encoding:** Monochrome blue with variable white saturation. The 3-bit intensity value controls how washed-out the blue appears.
- **Hardware:** All Pioneer DJ hardware (CDJ-900 and later). This is the universal baseline waveform.
- **rekordbox versions:** All versions that produce ANLZ files.

##### PWV2 -- Tiny Waveform Preview (Monochrome)
- **File:** .DAT
- **FourCC:** `0x50575632` ("PWV2")
- **Header length:** 20 bytes (0x14)
- **Resolution:** Fixed 100 entries (100 columns)
- **Bytes per entry:** 1
- **Total data size:** 100 bytes
- **Byte layout per entry:** Single byte:
  - Bits [3:0] (4 low-order bits): height (0-15 pixels)
  - Remaining bits: unused
- **Color encoding:** Monochrome (height only, no intensity channel)
- **Hardware:** CDJ-900 and similar older/compact players
- **rekordbox versions:** All versions

##### PWV3 -- Waveform Detail (Monochrome, Scrolling)
- **File:** .EXT
- **FourCC:** `0x50575633` ("PWV3")
- **Header length:** 24 bytes (0x18)
- **Resolution:** Variable, track-length-dependent. **150 entries per second of audio** (one entry per half-frame at 75 frames/sec). A 5-minute track has ~45,000 entries.
- **Bytes per entry:** 1 (len_entry_bytes is always 1)
- **Total data size:** len_entries bytes
- **Byte layout per entry:** Same as PWAV:
  - Bits [4:0]: height (0-31)
  - Bits [7:5]: whiteness/intensity (0-7)
- **Color encoding:** Monochrome blue with variable white saturation (identical encoding to PWAV)
- **Header constant:** Bytes 0x14-0x17 always `0x00960000`
- **Hardware:** All NXS and later hardware. This is the scrolling detail waveform on the main display.
- **rekordbox versions:** All versions that produce .EXT files (rekordbox 3+)

##### PWV4 -- Waveform Color Preview
- **File:** .EXT
- **FourCC:** `0x50575634` ("PWV4")
- **Header length:** 24 bytes (0x18)
- **Resolution:** Fixed 1,200 entries (1,200 columns of waveform overview)
- **Bytes per entry:** 6
- **Total data size:** 7,200 bytes
- **Byte layout per entry (6 bytes):**
  - Byte 0: unknown (possibly reserved)
  - Byte 1: luminance boost / brightness modifier (0-127 range used for color scaling)
  - Byte 2: blue waveform inverse intensity (lower 7 bits, masked with 0x7F)
  - Byte 3: red channel (lower 7 bits, masked with 0x7F)
  - Byte 4: green channel (lower 7 bits, masked with 0x7F)
  - Byte 5: blue channel + front height (lower 7 bits, masked with 0x7F)
- **Color encoding:** Dual-layer waveform:
  - **Color waveform (back layer):** RGB derived from bytes 3/4/5, scaled by luminance (byte1 / 127)
  - **Blue waveform (front layer):** Monochrome blue derived from byte 2 (inverse intensity)
  - **Heights:** Front height = byte 5 value; back height = max(byte2, byte3, byte4)
- **Hardware:** CDJ-2000NXS2, CDJ-3000, XDJ-XZ, and later. Also used in rekordbox desktop.
- **rekordbox versions:** rekordbox 5+ (NXS2 era)

##### PWV5 -- Waveform Color Detail (Scrolling)
- **File:** .EXT
- **FourCC:** `0x50575635` ("PWV5")
- **Header length:** 24 bytes (0x18)
- **Resolution:** Variable, track-length-dependent. **150 entries per second of audio** (same as PWV3). A 5-minute track has ~45,000 entries.
- **Bytes per entry:** 2 (len_entry_bytes is always 2)
- **Total data size:** len_entries * 2 bytes
- **Byte layout per entry (2 bytes, big-endian u16):**
  ```
  Bit:  f  e  d  c  b  a  9  8  7  6  5  4  3  2  1  0
       |  red  |  green | blue  |    height    | 0 | 0 |
  ```
  - Bits [15:13] (3 bits): red (0-7)
  - Bits [12:10] (3 bits): green (0-7)
  - Bits [9:7] (3 bits): blue (0-7)
  - Bits [6:2] (5 bits): height (0-31)
  - Bits [1:0]: unused (always 0)
- **Bitmasks (from pyrekordbox source):**
  - Red:    `0xE000` >> 12 (actually >> 13 gives 0-7, pyrekordbox shifts >> 12 giving 0-14 range)
  - Green:  `0x1C00` >> 10
  - Blue:   `0x0380` >> 7
  - Height: `0x007C` >> 2
- **Color encoding:** 3-bit RGB per channel (8 levels each, 512 possible colors). Height normalized to 0.0-1.0 by dividing by 31.
- **Header constant:** Bytes 0x14-0x17 may always be `0x00960305`
- **Hardware:** CDJ-2000NXS2, CDJ-3000, XDJ-XZ, and later.
- **rekordbox versions:** rekordbox 5+

##### PWV6 -- Waveform 3-Band Preview
- **File:** .2EX
- **FourCC:** `0x50575636` ("PWV6")
- **Header length:** 20 bytes (0x14)
- **Resolution:** Fixed 1,200 entries (1,200 columns)
- **Bytes per entry:** 3
- **Total data size:** 3,600 bytes
- **Byte layout per entry (3 bytes):**
  - Byte 0: mid-range frequency height
  - Byte 1: high frequency height
  - Byte 2: low frequency height
- **Color encoding:** 3-band frequency separation. Display colors per Deep Symmetry:
  - Low: dark blue
  - Mid-range: amber
  - High: white
  - Drawn stacked (low on bottom, mid on top, high on top of that)
- **Hardware:** CDJ-3000, CDJ-3000X, and later. Also rekordbox desktop (v6+).
- **rekordbox versions:** rekordbox 6+

##### PWV7 -- Waveform 3-Band Detail (Scrolling)
- **File:** .2EX
- **FourCC:** `0x50575637` ("PWV7")
- **Header length:** 24 bytes (0x18)
- **Resolution:** Variable, track-length-dependent. **150 entries per second of audio**. A 5-minute track has ~45,000 entries.
- **Bytes per entry:** 3
- **Total data size:** len_entries * 3 bytes
- **Byte layout per entry (3 bytes):** Same as PWV6:
  - Byte 0: mid-range frequency height
  - Byte 1: high frequency height
  - Byte 2: low frequency height
- **Color encoding:** Same 3-band scheme as PWV6, but drawn overlapping on same axis (not stacked):
  - Low: dark blue
  - Mid-range: amber
  - High: white
  - Where low and mid overlap: brown
  - Non-linear scaling is used (exact formula not yet fully reverse-engineered)
- **Header constant:** Bytes 0x14-0x17 may always be `0x00960000`
- **Hardware:** CDJ-3000, CDJ-3000X
- **rekordbox versions:** rekordbox 6+

##### PWVC -- Waveform Color Configuration (undocumented)
- **File:** .2EX
- **Header length:** 14 bytes
- **Structure:** 2-byte unknown + 3 x u16 values
- **Purpose:** Unknown. Possibly color palette or scaling configuration for 3-band waveforms.

#### Summary Table

| Tag  | Name                  | File | Entries      | Bytes/Entry | Color         | Hardware Era     |
|------|-----------------------|------|-------------|-------------|---------------|------------------|
| PWAV | Waveform Preview      | .DAT | 400 fixed   | 1           | Mono blue     | CDJ-900+         |
| PWV2 | Tiny Preview          | .DAT | 100 fixed   | 1           | Mono (height) | CDJ-900          |
| PWV3 | Waveform Detail       | .EXT | 150/sec     | 1           | Mono blue     | NXS+             |
| PWV4 | Color Preview         | .EXT | 1200 fixed  | 6           | RGB + blue    | NXS2+            |
| PWV5 | Color Detail          | .EXT | 150/sec     | 2           | 3-bit RGB     | NXS2+            |
| PWV6 | 3-Band Preview        | .2EX | 1200 fixed  | 3           | 3-band freq   | CDJ-3000+        |
| PWV7 | 3-Band Detail         | .2EX | 150/sec     | 3           | 3-band freq   | CDJ-3000+        |

**Sources:**
- Deep Symmetry djl-analysis `anlz.adoc` documentation (crate-digger repo, `doc/modules/ROOT/pages/anlz.adoc`): authoritative reverse-engineered format spec. Relevance: HIGH
- Deep Symmetry Kaitai Struct definition `rekordbox_anlz.ksy` (crate-digger repo, `src/main/kaitai/rekordbox_anlz.ksy`): machine-readable format definitions. Relevance: HIGH
- pyrekordbox v0.4.4 source (`anlz/structs.py`, `anlz/tags.py`): working parser implementations with bit-level extraction code. Relevance: HIGH

**Confidence:** HIGH for PWAV/PWV2/PWV3/PWV4/PWV5 (fully documented by Deep Symmetry, implemented in pyrekordbox with working parsers). MEDIUM-HIGH for PWV6/PWV7 (documented by Deep Symmetry, pyrekordbox parses the raw bytes but does not decode the individual frequency band values in its tag handler -- the `get()` method is not implemented for PWV6/PWV7). LOW for PWVC (undocumented purpose, minimal struct).

---

### Question 2: pyrekordbox Waveform Parsing Support

**Answer:** pyrekordbox v0.4.4 supports parsing all 7 waveform tags plus PWVC. It provides fully decoded output for PWAV/PWV2/PWV3 (height + intensity arrays), PWV4 (heights + RGB color + blue arrays), and PWV5 (normalized heights + RGB color array). PWV6/PWV7 are parsed at the binary level (raw bytes extracted) but lack decoded `get()` methods. PWV6/PWV7 would need 3 additional lines of numpy code to decode.

**Detail:**

#### API Surface

```python
from pyrekordbox.anlz import AnlzFile

# Parse any ANLZ file (.DAT, .EXT, or .2EX)
anlz = AnlzFile.parse_file("ANLZ0000.EXT")

# Access tags by semantic name
wf_preview = anlz.get("wf_preview")        # PWAV -> (heights, intensities) numpy arrays
wf_tiny    = anlz.get("wf_tiny_preview")    # PWV2 -> (heights, intensities) numpy arrays
wf_detail  = anlz.get("wf_detail")          # PWV3 -> (heights, intensities) numpy arrays
wf_color   = anlz.get("wf_color")           # PWV4 -> (heights, colors, blues) numpy arrays
wf_cdetail = anlz.get("wf_color_detail")    # PWV5 -> (heights, colors) numpy arrays

# Access tags by tag type string
tag = anlz.get_tag("PWV5")                  # Returns PWV5AnlzTag object
data = tag.get()                            # Calls the decode method

# Access raw tag content (for PWV6/PWV7 where get() is not implemented)
tag6 = anlz.get_tag("PWV6")
raw_bytes = tag6.content.entries            # Raw bytes, 3 per entry
num_entries = tag6.content.len_entries
```

#### Return Value Formats

**PWAV / PWV2 / PWV3** (monochrome tags):
```python
heights, intensities = anlz.get("wf_preview")
# heights: np.ndarray[int8], shape (N,), values 0-31 (PWAV/PWV3) or 0-15 (PWV2)
# intensities: np.ndarray[int8], shape (N,), values 0-7 (whiteness)
```

**PWV4** (color preview):
```python
heights, col_color, col_blues = anlz.get("wf_color")
# heights: np.ndarray[int64], shape (1200, 2) — [front_height, back_height]
# col_color: np.ndarray[int64], shape (1200, 2, 3) — [base_rgb, bright_rgb]
# col_blues: np.ndarray[int64], shape (1200, 2, 3) — [base_blue, bright_blue]
```

**PWV5** (color detail):
```python
heights, colors = anlz.get("wf_color_detail")
# heights: np.ndarray[float64], shape (N,), values 0.0-1.0 (normalized by /31)
# colors: np.ndarray[int64], shape (N, 3) — [red, green, blue], each 0-7
```

**PWV6 / PWV7** (3-band): No `get()` decoder. Raw bytes only. To decode:
```python
tag = anlz.get_tag("PWV6")  # or PWV7
data = tag.content.entries  # raw bytes
n = tag.content.len_entries
# Manual decoding (3 bytes per entry):
import numpy as np
entries = np.frombuffer(data, dtype=np.uint8).reshape(n, 3)
mid  = entries[:, 0]  # mid-range frequency height
high = entries[:, 1]  # high frequency height
low  = entries[:, 2]  # low frequency height
```

#### Tag Support Status

| Tag  | Struct parsing | `get()` decoder | Output quality |
|------|:-:|:-:|---|
| PWAV | YES | YES | Full (height + intensity) |
| PWV2 | YES | YES | Full (height + intensity) |
| PWV3 | YES | YES | Full (height + intensity) |
| PWV4 | YES | YES | Full (heights + RGB + blue, dual-layer) |
| PWV5 | YES | YES | Full (normalized heights + 3-bit RGB) |
| PWV6 | YES | NO (raw bytes) | Trivial to add (~3 lines numpy) |
| PWV7 | YES | NO (raw bytes) | Trivial to add (~3 lines numpy) |
| PWVC | YES | NO | Unknown purpose |

**Sources:**
- pyrekordbox v0.4.4 source `anlz/tags.py`: Tag handler classes with `get()` implementations. Relevance: HIGH (directly inspected source code)
- pyrekordbox v0.4.4 source `anlz/structs.py`: Binary struct definitions with Construct library. Relevance: HIGH (directly inspected source code)
- pyrekordbox v0.4.4 source `anlz/file.py`: `AnlzFile.parse_file()` and `get()`/`get_tag()` API. Relevance: HIGH

**Confidence:** HIGH -- based on direct source code inspection of pyrekordbox v0.4.4 installed from PyPI.

---

### Question 3: Resolution Comparison -- Pioneer ANLZ vs Custom 60fps librosa Waveform

**Answer:** Pioneer ANLZ detail waveforms (PWV3/PWV5/PWV7) provide 150 data points per second with 3-bit color depth (8 levels per RGB channel, 512 total colors in PWV5). A custom 60fps RGB waveform computed from librosa would provide 60 data points per second but with full floating-point color resolution per band. Pioneer has 2.5x higher temporal resolution but dramatically lower color/amplitude precision.

**Detail:**

#### Temporal Resolution

| Source | Data points/sec | 5-min track | Basis |
|--------|:-:|:-:|---|
| Pioneer PWV3/PWV5/PWV7 (detail) | 150 | ~45,000 | 1 per half-frame (75 fps x 2) |
| Pioneer PWAV (preview) | ~1.33* | 400 | Fixed 400 for entire track |
| Pioneer PWV4/PWV6 (color preview) | ~4* | 1,200 | Fixed 1,200 for entire track |
| Custom librosa @ 60fps | 60 | 18,000 | 1 per frame at target fps |
| Custom librosa @ 150/sec | 150 | 45,000 | Matching Pioneer rate |

\* Preview rates are approximate and depend on track length.

Pioneer detail waveforms have **2.5x the temporal resolution** of a 60fps analysis. However, generating a librosa waveform at 150 samples/sec to match Pioneer would be trivial (just change the hop_length parameter).

#### Amplitude/Height Resolution

| Source | Bits | Range | Precision |
|--------|:-:|:-:|---|
| Pioneer PWAV/PWV3 | 5 | 0-31 | 32 levels |
| Pioneer PWV2 | 4 | 0-15 | 16 levels |
| Pioneer PWV4 | 7 | 0-127 | 128 levels (per color channel) |
| Pioneer PWV5 | 5 | 0-31 | 32 levels (height), normalized to float |
| Pioneer PWV6/PWV7 | 8 | 0-255 | 256 levels per band |
| librosa (float32) | 32 | 0.0-1.0 | ~16M levels |

librosa provides effectively unlimited amplitude resolution compared to Pioneer's 5-8 bit quantization.

#### Color / Spectral Resolution

| Source | Color model | Depth | Total colors |
|--------|---|:-:|:-:|
| Pioneer PWAV/PWV2/PWV3 | Monochrome + intensity | 3-bit intensity | 8 shades of blue |
| Pioneer PWV4 | RGB (7-bit channels) + luminance | 7+7+7+7 bits | Complex dual-layer |
| Pioneer PWV5 | Packed RGB | 3+3+3 bits | 512 colors |
| Pioneer PWV6/PWV7 | 3-band (low/mid/high) | 8+8+8 bits | 3 independent bands, 256 levels each |
| librosa STFT | Full spectrum | float32 per bin | Continuous, thousands of frequency bins |

A librosa-based 3-band waveform (splitting into low/mid/high via bandpass filtering or mel bands) would provide:
- **float32 per band** vs Pioneer's 3-8 bit integer per band
- **Configurable band boundaries** vs Pioneer's fixed (undocumented) crossover frequencies
- **Additional derived features** (spectral centroid, spectral flux, onset strength) unavailable from ANLZ data

#### Practical Comparison for SCUE

For **visual rendering** (Analysis Viewer, Live Deck Monitor), Pioneer's resolution is sufficient. The CDJ displays themselves only show 5-bit height at ~150 samples/sec, so matching this provides a native look.

For **cue generation and effect triggering** (SCUE Layers 2-3), librosa's floating-point precision and configurable spectral decomposition are far superior. Pioneer waveform data was designed for display, not for music analysis.

**Recommended hybrid approach:**
- **Display:** Use Pioneer ANLZ waveforms (PWV4/PWV5 for NXS2+ hardware, PWV6/PWV7 for CDJ-3000+) for the visual waveform display. This ensures visual consistency with what DJs see on their hardware.
- **Analysis:** Use librosa-derived data for all cue generation, onset detection, and spectral analysis. The temporal resolution can be set to any value (150/sec to match Pioneer, or higher).
- **Fallback:** If ANLZ waveforms are unavailable (track not from Pioneer, or ANLZ parse failure), render from librosa data with a Pioneer-like color mapping.

**Sources:**
- Deep Symmetry ANLZ documentation: 150 entries/sec is one per half-frame, 75 frames/sec. Relevance: HIGH
- Pioneer CDJ-3000 display specifications (community knowledge): waveform display resolution matches ANLZ data. Relevance: MEDIUM
- librosa documentation: hop_length parameter controls temporal resolution of STFT and derived features. Relevance: HIGH

**Confidence:** HIGH for Pioneer resolution numbers (verified from format spec and pyrekordbox source). HIGH for librosa capabilities (well-documented library). MEDIUM for the "hybrid approach" recommendation (architectural opinion, not a factual finding).

---

## File Location Summary

| File extension | Tags present | Created by |
|---|---|---|
| `.DAT` | PWAV, PWV2, PQTZ, PCOB, PPTH, PVBR | All rekordbox versions |
| `.EXT` | PWV3, PWV4, PWV5, PCO2, PSSI | rekordbox 3+ (NXS era, expanded in NXS2) |
| `.2EX` | PWV6, PWV7, PWVC | rekordbox 6+ (CDJ-3000 era) |

All three files share the same base path structure on USB: `PIONEER/USBANLZ/Pnnn/xxxxxxxx/ANLZ0000.{DAT,EXT,2EX}`

---

## Recommended Next Steps

1. **For Analysis Viewer waveform display:** Parse PWV5 (color detail) from .EXT files via pyrekordbox as the primary waveform data source. Fall back to PWV3 (monochrome detail) if PWV5 is absent. This covers NXS2+ and NXS hardware respectively.

2. **For CDJ-3000 users:** Add PWV7 (3-band detail) parsing from .2EX files. This requires ~3 lines of numpy to decode the raw bytes from pyrekordbox into mid/high/low arrays.

3. **For cue generation (Layer 2):** Continue using librosa-derived spectral data. Pioneer ANLZ waveforms lack the precision needed for onset detection or spectral analysis.

4. **Store Pioneer waveform data in TrackAnalysis JSON** alongside librosa-derived data, keyed by tag type. This enables the frontend to render native Pioneer-style waveforms while the backend uses librosa for analysis.

5. **Extend USB scanner** to extract waveform data from ANLZ files during the scan pass (pyrekordbox already parses these files for beat grids and cue points -- adding waveform extraction is incremental).

---

## Skill File Candidates

The following should be added to a `skills/pioneer-anlz-waveforms.md` skill file:

- Complete tag inventory (PWAV through PWV7 + PWVC) with file locations and hardware compatibility
- PWV5 bit-packing layout (the 3-3-3-5-2 bit field diagram) -- this is the most commonly needed format for color waveform rendering
- PWV4's 6-byte dual-layer encoding (complex, easy to get wrong)
- PWV6/PWV7 byte order: mid, high, low (not the intuitive low, mid, high)
- Resolution constant: 150 data points per second for all detail tags (PWV3/PWV5/PWV7)
- pyrekordbox API: `AnlzFile.parse_file()` then `.get("wf_color_detail")` for PWV5
- PWV6/PWV7 lack decoded `get()` in pyrekordbox -- must decode manually from raw bytes
- Preview tags are fixed-width (400 for PWAV, 100 for PWV2, 1200 for PWV4/PWV6) regardless of track length
