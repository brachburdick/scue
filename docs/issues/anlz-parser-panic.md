# Issue: rbox ANLZ Parser Panics on XDJ-AZ Exported Files

## Status
**Resolved** (2026-03-17) — replaced with pyrekordbox + custom parser. See ADR-013.

## What We Were Trying to Do

SCUE's USB scanner reads Pioneer's `exportLibrary.db` via the `rbox` Python library to extract track metadata (title, artist, BPM, key) before a DJ set. This works perfectly — we successfully read all 2,022 tracks from Brach's XDJ-AZ USB backup.

Beyond the database metadata, Pioneer USBs also contain **ANLZ files** (`PIONEER/USBANLZ/.../*.DAT` and `*.EXT`) — per-track binary analysis files that store:

- **Beatgrids** — precise beat timestamps for every beat in the track (Pioneer-verified, hand-corrected in rekordbox)
- **Hot cues** — named markers with timestamps and colors
- **Memory cues** — saved loop/cue points
- **Phrase analysis** — song structure segments (intro, verse, drop, etc.)
- **Waveform data** — colored waveform for display

We need the **beatgrid** most urgently. SCUE's Pioneer enrichment pass (`scue/layer1/enrichment.py`) can swap librosa's estimated beatgrid with Pioneer's verified one, dramatically improving section alignment and cue timing. The enrichment function already accepts a `pioneer_beatgrid` parameter — it just needs data.

## What Happens

When calling `rbox.Anlz(path)` on certain ANLZ files from the XDJ-AZ USB export, the Rust-backed parser **panics** (a Rust `panic!()` that aborts the entire Python process). This is not a catchable Python exception — it kills the process immediately.

### Error Output
```
thread '<unnamed>' panicked at rbox/src/anlz/anlz.rs:1427:46:
Can't read ANLZ:
  Error: no variants matched at 0x722
    While parsing field 'self_0' in Content::BeatGrid
      Error: assertion failed: `u2 == 0x80000` at 0x722
    While parsing field 'content' in Section
  While parsing field 'sections' in AnlzData
```

The parser encounters an ANLZ section at offset `0x722` where the BeatGrid variant's assertion (`u2 == 0x80000`) fails, and no other variant matches either. Instead of returning an error, the Rust code panics.

### Why It Happens

The XDJ-AZ uses the **Device Library Plus (DLP)** format, which is a newer Pioneer export format. The ANLZ files produced by DLP hardware may have slightly different section layouts or version flags compared to legacy hardware (CDJ-2000NXS2, CDJ-3000). rbox v0.1.7's parser was likely tested against legacy ANLZ files and doesn't handle all DLP variants.

Key details:
- **rbox version**: 0.1.7 (latest as of 2026-03-16)
- **Hardware**: XDJ-AZ (DLP hardware)
- **rekordbox version**: Unknown (whatever version exported to the USB)
- **Not all files fail**: The panic happens on *some* ANLZ files, not all. The parser successfully opened at least one file during testing before hitting the problematic one.

## What We Need

A way to read **beatgrids** and **cue points** from XDJ-AZ ANLZ files. Options to investigate:

### 1. rbox Fix (Upstream)
- Is this a known issue in rbox? Check their GitHub issues.
- Has it been fixed in a newer version or dev branch?
- Can we report the bug with our specific file?
- The fix would likely be: return `Err` instead of `panic!()` for unknown ANLZ section variants.

### 2. pyrekordbox as Alternative
- `pyrekordbox` (pure Python) also reads ANLZ files: `pyrekordbox.anlz.AnlzFile(path)`
- It may handle DLP ANLZ variants better since it's pure Python (no panics, just exceptions).
- Check if `pyrekordbox` can read the same files that crash rbox.
- API: `pyrekordbox.anlz.AnlzFile(path)` → sections with beat grids, cue lists, etc.

### 3. Pure Python ANLZ Parser
- The ANLZ format is documented: https://djl-analysis.deepsymmetry.org/djl-analysis/anlz.html
- We could write a minimal parser that only extracts beatgrids and cue points.
- The format is tag-length-value based — each section has a 4-byte tag, 4-byte header length, 4-byte total length, then content.
- BeatGrid section tag: `PQTZ` (0x5051545A)
- Cue list section tag: `PCOB` (0x50434F42)

### 4. Subprocess Isolation
- If we can't avoid the panic, run ANLZ parsing in a **subprocess** so the panic doesn't kill the main SCUE process.
- Parse each file in isolation: `python -c "from rbox import Anlz; ..."` as a subprocess, capture stdout.
- Slow but safe.

## Files Involved

- `scue/layer1/usb_scanner.py` — `_read_anlz_data()` function (currently calls `rbox.Anlz`)
- `scue/layer1/enrichment.py` — `run_enrichment_pass()` accepts `pioneer_beatgrid: list[float] | None`
- USB backup: `~/Documents/skald usb backup 3.16.26/PIONEER/USBANLZ/`
- Specific failing file (first encountered): a file under `PIONEER/USBANLZ/` with a section at offset 0x722 that triggers the panic

## Current Workaround

ANLZ reading is disabled in the USB scanner. We read only `exportLibrary.db` metadata (title, artist, BPM, key). Enrichment uses the live BPM from the bridge's `player_status` message but has no beatgrid or cue point data from Pioneer. This means:
- BPM enrichment works (from live bridge data)
- Key enrichment works (from exportLibrary.db)
- Beatgrid enrichment does NOT work (no Pioneer beatgrid available)
- Cue point data NOT available (no ANLZ access)

## Resolution

Implemented ADR-013: two-tier pure-Python ANLZ parsing.

- **Tier 1: pyrekordbox** (`AnlzFile.parse_file()`) — full ANLZ support, handles DLP files without panics.
- **Tier 2: custom `anlz_parser.py`** — zero-dependency fallback for beat grid (PQTZ) and cues (PCOB) only.
- rbox retained for `exportLibrary.db` database reading (works, no panics).
- ANLZ reading re-enabled in USB scanner.

Files changed:
- `scue/layer1/anlz_parser.py` — NEW custom minimal parser
- `scue/layer1/usb_scanner.py` — `_read_anlz_data()` replaced with two-tier strategy
- `pyproject.toml` — added `pyrekordbox>=0.4.4` to `[usb]` deps
- `tests/test_layer1/test_anlz_parser.py` — 13 tests for custom parser
- `tests/test_layer1/test_usb_scanner.py` — 8 tests for two-tier fallback

## Priority (historical)

Medium-high. Beatgrid enrichment is important for accurate section alignment, but the system works without it using librosa's estimated beatgrid.
