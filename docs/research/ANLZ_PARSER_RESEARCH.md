# ANLZ Parser Research — Findings & Recommendations

## The Problem

rbox v0.1.7's Rust-backed ANLZ parser panics (process kill, not catchable) on some ANLZ files from XDJ-AZ USB exports. The panic occurs in the BeatGrid section parser where an assertion (`u2 == 0x80000`) fails. This is a Rust `panic!()` — it terminates the Python process immediately.

## Root Cause

The XDJ-AZ exports ANLZ files with slightly different section layouts than legacy hardware. Specifically, the BeatGrid section (`PQTZ` tag, `0x5051545A`) has a field value that doesn't match rbox's expected constant. The rbox parser treats this as a hard assertion failure rather than returning an error. This is a bug in rbox — it should return `Err`, not `panic!()`.

The ANLZ file format itself is tag-length-value based and well-documented by Deep Symmetry. The sections are self-describing: each has a 4-byte tag, 4-byte header length, 4-byte total length. A parser that doesn't recognize a section variant can safely skip it by advancing `total_length` bytes. rbox doesn't do this — it panics instead.

## Options Evaluated

### Option 1: pyrekordbox (RECOMMENDED — Primary)

**What it is:** Pure Python ANLZ parser. Mature project (v0.4.4, actively maintained). Parses .DAT, .EXT, and .2EX files. Extracts beat grids, cue points, memory points, hot cues, waveforms, and song structure (phrase analysis).

**API:**
```python
from pyrekordbox.anlz import AnlzFile

anlz = AnlzFile.parse_file("ANLZ0000.DAT")

# Beat grid
beat_grid = anlz.get("beat_grid")  # or anlz.get_tag("PQTZ")

# Cue points
cues = anlz.getall_tags("PCOB")  # returns list of cue list sections

# Song structure (phrase analysis)
structure = anlz.get("song_structure")  # PSSI tag, in .EXT files
```

**Why it's the best option:**
- Pure Python. No Rust panics. If it encounters an unknown section, it raises a Python exception you can catch — or skips it gracefully depending on the parse mode.
- Well-documented: full format specification at pyrekordbox.readthedocs.io with every tag type explained.
- Same underlying format knowledge as crate-digger (Deep Symmetry). The format spec documentation in pyrekordbox explicitly credits the Deep Symmetry reverse engineering work.
- Has been tested with rekordbox 5, 6, and 7 exports.
- Supports Device Library Plus databases (`exportLibrary.db`) as well as ANLZ files — so it could replace rbox for BOTH database reading and ANLZ parsing.
- pip installable: `pip install pyrekordbox`
- MIT licensed.

**Risk:** pyrekordbox may also fail on the same files if the format variant is truly unknown. But the failure mode is a Python exception, not a process kill. You can catch it, log it, and skip that file while continuing to process the rest of the library.

**Difficulty:** Low. Drop-in replacement for the ANLZ parsing code. The API is different from rbox but straightforward.

### Option 2: Minimal Custom Parser (RECOMMENDED — Fallback)

**What it is:** A small (~100 line) Python parser that reads only the PQTZ (beat grid) and PCOB (cue list) sections from ANLZ files, skipping everything else.

**Why this is worth having as a fallback:**
- The ANLZ format is simple: tag-length-value. You can iterate sections by reading the 4-byte tag and 4-byte total length, then either parse or skip.
- The beat grid format is documented: each entry is 16 bytes (beat number as u16, tempo as u16 in BPM×100, time as u32 in milliseconds, plus padding).
- If pyrekordbox also chokes on the XDJ-AZ variant, a custom parser can be more lenient — it can try to parse the beat grid with relaxed assertions and fall back to skipping if the structure doesn't match.
- Zero dependencies. Ships with SCUE.

**Reference for implementation:** Deep Symmetry's Kaitai Struct definition at `crate-digger/src/main/kaitai/rekordbox_anlz.ksy` has the complete byte-level format for every section type. The beat grid section specifically:
- Tag: `PQTZ` (0x5051545A)
- Header length: typically 0x18 (24 bytes)
- After the header: `entry_count` (u32) followed by `entry_count` entries
- Each beat grid entry: 2 bytes (beat number, 1-indexed), 2 bytes (tempo as BPM×100), 4 bytes (time in milliseconds from start of track)

**Difficulty:** Low-medium. ~2 hours to implement beat grid extraction only. Cue points add maybe another hour. Phrase analysis (PSSI) is more complex.

### Option 3: Subprocess Isolation for rbox

**What it is:** Run rbox's ANLZ parser in a subprocess so the Rust panic doesn't kill the main SCUE process.

```python
import subprocess, json

result = subprocess.run(
    ["python", "-c", """
import json, sys
from rbox import Anlz
try:
    anlz = Anlz(sys.argv[1])
    grid = anlz.get_beat_grid()
    print(json.dumps([{"beat": b.beat_number, "tempo": b.tempo, "time": b.time} for b in grid]))
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
""", path],
    capture_output=True, text=True, timeout=30
)
if result.returncode != 0:
    # rbox panicked or errored — skip this file
    log.warning(f"rbox failed on {path}: {result.stderr}")
else:
    beats = json.loads(result.stdout)
```

**Why you might want it:** rbox successfully parses *some* files. For the files it handles, it may be faster than pyrekordbox (Rust vs Python). Subprocess isolation makes the panic non-fatal.

**Why it's not ideal:** Subprocess per file is slow (~200ms overhead per invocation). You have 2,022 tracks — that's ~7 minutes of subprocess overhead alone. Also doesn't solve the problem: you still don't get beat grids for the files that panic.

**Difficulty:** Low. But poor UX for the common case.

### Option 4: Wait for rbox Fix

**What it is:** Report the bug to rbox's GitHub, provide the failing ANLZ file, and wait for a fix.

**Why it's not sufficient on its own:** Unknown timeline. rbox is a relatively small project. And even if fixed, the underlying issue (Rust panic instead of error return) means any future unknown variant will crash the process again.

**Recommendation:** File the bug regardless (with the hex offset and assertion details), but don't block on it.

## Recommended Strategy

**Use pyrekordbox as primary ANLZ parser, with the custom minimal parser as a fallback.**

```
ANLZ file
  │
  ├──→ Try pyrekordbox.anlz.AnlzFile.parse_file()
  │      ├── Success → extract beat grid, cues, phrase analysis
  │      └── Exception → log warning, try fallback
  │
  └──→ Fallback: custom minimal PQTZ parser
         ├── Success → extract beat grid only (no cues, no phrases)
         └── Exception → log error, skip file. Enrichment will use librosa grid.
```

This gives you:
- pyrekordbox handles the vast majority of files, including unknown section variants (it skips them rather than crashing)
- The custom parser handles edge cases where even pyrekordbox fails, extracting the minimum useful data (beat grid)
- No process crashes under any circumstance
- rbox is removed from the ANLZ parsing path entirely (keep it for `exportLibrary.db` reading if it works there, or switch to pyrekordbox for that too)

## Bonus: pyrekordbox Can Replace rbox Entirely

pyrekordbox also supports reading `exportLibrary.db` (Device Library Plus databases):

```python
from pyrekordbox import Rekordbox6Database
# For One Library / Device Library Plus on USB:
# pyrekordbox can read these too, though the API may differ
```

If pyrekordbox handles both the database AND the ANLZ files reliably on your XDJ-AZ USB, you could drop rbox as a dependency entirely. This simplifies the dependency tree (no Rust compilation, no SQLCipher native builds) and gives you a single library for all Pioneer data access. Worth testing.

## Action Items

1. **Immediate:** `pip install pyrekordbox` and test against the same ANLZ file that crashes rbox. If it parses successfully, it's your new primary parser.
2. **Immediate:** Test pyrekordbox against `exportLibrary.db` from the XDJ-AZ USB. If it reads the database correctly, consider replacing rbox for database access too.
3. **Short-term:** Implement the custom minimal PQTZ parser as a fallback for any ANLZ file that pyrekordbox also can't handle.
4. **Short-term:** File a bug on rbox's GitHub with the panic details, hex offset, and assertion failure message. Attach the failing ANLZ file if possible.
5. **Documentation:** Update LEARNINGS.md with the rbox panic issue and the pyrekordbox workaround. Update ADR-012 if rbox is being replaced by pyrekordbox.

## Dependencies

| Library | Purpose | Status |
|---|---|---|
| `rbox` | exportLibrary.db reading + ANLZ parsing | ANLZ parsing broken on DLP files. DB reading works. May be replaceable by pyrekordbox. |
| `pyrekordbox` | ANLZ parsing (primary). Possibly exportLibrary.db too. | Not yet tested on XDJ-AZ files. Needs validation. |
| Custom parser | ANLZ beat grid extraction (fallback) | Not yet built. ~100 lines Python, zero deps. |

## LEARNINGS.md Entry

```markdown
### rbox Rust ANLZ parser panics on XDJ-AZ exported files (process kill)
Date: 2025-03-16
Context: Reading ANLZ files from XDJ-AZ USB export to extract Pioneer beatgrids for enrichment.
Problem: rbox v0.1.7's Rust-backed parser calls panic!() when it encounters a BeatGrid section variant with an unexpected field value (u2 != 0x80000). This kills the entire Python process — it's not a catchable exception. Affects some (not all) ANLZ files from DLP hardware.
Fix: Use pyrekordbox (pure Python) as the primary ANLZ parser. It raises Python exceptions on unknown sections instead of killing the process. Implement a minimal custom PQTZ parser as a fallback for files that neither library handles.
Prevention: Never use a Rust-backed parser for untrusted/variable file formats without subprocess isolation. Prefer pure Python parsers for formats where the spec is still being reverse-engineered and new variants appear with hardware releases.
```
