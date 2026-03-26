"""Minimal ANLZ file parser — fallback for when pyrekordbox cannot handle a file.

Reads Pioneer ANLZ binary files (.DAT, .EXT, .2EX) using the tag-length-value
structure documented by Deep Symmetry. Extracts PQTZ (beat grid), PCOB (cue list),
PSSI (phrase/song structure), and PPTH (original file path) sections.

Zero external dependencies. All struct unpack failures raise AnlzParseError
(a normal Python exception, never a process-killing panic).

Reference: https://djl-analysis.deepsymmetry.org/djl-analysis/anlz.html
"""

import logging
import struct
from pathlib import Path

logger = logging.getLogger(__name__)


class AnlzParseError(Exception):
    """Raised when an ANLZ file cannot be parsed."""


def _read_sections(data: bytes) -> list[tuple[str, bytes]]:
    """Iterate ANLZ sections, returning (tag, section_bytes) pairs.

    Each section has a 12-byte header minimum:
      - 4 bytes: tag (ASCII, e.g. 'PQTZ')
      - 4 bytes: header length (big-endian u32)
      - 4 bytes: total section length (big-endian u32)

    Unknown sections are returned as-is (tag + raw bytes). The caller
    decides whether to parse or skip each section.
    """
    sections: list[tuple[str, bytes]] = []
    offset = 0

    # ANLZ files start with a file header (tag 'PMAI', typically 28 bytes)
    if len(data) < 12:
        raise AnlzParseError("File too small to contain ANLZ header")

    file_tag = data[0:4]
    if file_tag != b"PMAI":
        raise AnlzParseError(f"Not an ANLZ file (expected PMAI, got {file_tag!r})")

    # Skip file header: PMAI tag(4) + header_len(4) + file_len(4)
    # field1 = header_len (typically 28), field2 = total file length
    _, file_header_len, _ = struct.unpack_from(">4sII", data, 0)
    offset = file_header_len

    while offset + 12 <= len(data):
        tag_bytes = data[offset : offset + 4]
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError:
            raise AnlzParseError(f"Non-ASCII tag at offset {offset}: {tag_bytes!r}")

        header_len, total_len = struct.unpack_from(">II", data, offset + 4)

        if total_len < 12 or offset + total_len > len(data):
            raise AnlzParseError(
                f"Invalid section length at offset {offset}: "
                f"tag={tag}, header_len={header_len}, total_len={total_len}"
            )

        section_data = data[offset : offset + total_len]
        sections.append((tag, section_data))
        offset += total_len

    return sections


def parse_anlz_beatgrid(path: Path) -> list[dict]:
    """Parse PQTZ beat grid from an ANLZ .DAT file.

    Returns list of {"beat_number": int, "time_ms": float, "bpm": float}.
    Raises AnlzParseError on failure.
    """
    try:
        data = path.read_bytes()
    except OSError as e:
        raise AnlzParseError(f"Cannot read {path}: {e}") from e

    sections = _read_sections(data)

    for tag, section_data in sections:
        if tag != "PQTZ":
            continue

        # PQTZ header: tag(4) + header_len(4) + total_len(4) + unknown(4) + unknown(4) + entry_count(4) = 24 bytes
        if len(section_data) < 24:
            raise AnlzParseError(f"PQTZ section too small: {len(section_data)} bytes")

        entry_count = struct.unpack_from(">I", section_data, 20)[0]
        entries_offset = 24  # after the 24-byte header

        beats: list[dict] = []
        for i in range(entry_count):
            entry_start = entries_offset + i * 16
            if entry_start + 16 > len(section_data):
                logger.warning(
                    "PQTZ truncated at entry %d/%d in %s", i, entry_count, path
                )
                break

            beat_num, tempo_x100, time_ms = struct.unpack_from(
                ">HHI", section_data, entry_start
            )
            # tempo is stored as BPM * 100 (e.g. 12800 = 128.00 BPM)
            bpm = tempo_x100 / 100.0

            beats.append({
                "beat_number": beat_num,
                "time_ms": float(time_ms),
                "bpm": bpm,
            })

        return beats

    # No PQTZ section found — valid file but no beat grid
    return []


def parse_anlz_cues(path: Path) -> tuple[list[dict], list[dict]]:
    """Parse PCOB cue lists from an ANLZ .DAT file.

    Returns (hot_cues, memory_cues).
    Each cue: {"slot": int, "time_ms": float, "type": int}
      - slot: hot cue number (1-8), 0 for memory cues
      - type: 1=single, 2=loop

    Raises AnlzParseError on failure.
    """
    try:
        data = path.read_bytes()
    except OSError as e:
        raise AnlzParseError(f"Cannot read {path}: {e}") from e

    sections = _read_sections(data)

    hot_cues: list[dict] = []
    memory_cues: list[dict] = []

    for tag, section_data in sections:
        if tag != "PCOB":
            continue

        # PCOB header: tag(4) + header_len(4) + total_len(4) + cue_type(4) + unknown(2) + count(2)
        if len(section_data) < 20:
            continue

        cue_type_val = struct.unpack_from(">I", section_data, 12)[0]
        entry_count = struct.unpack_from(">H", section_data, 18)[0]
        is_hot = cue_type_val == 1  # 0=memory, 1=hotcue

        # Parse PCPT entries — start after the full header (header_len bytes)
        pcob_header_len = struct.unpack_from(">I", section_data, 4)[0]
        offset = pcob_header_len
        for _ in range(entry_count):
            if offset + 12 > len(section_data):
                break

            # Each PCPT entry has its own tag-length-value header
            entry_tag = section_data[offset : offset + 4]
            if entry_tag != b"PCPT":
                # Skip unknown sub-entry
                if offset + 8 <= len(section_data):
                    entry_total = struct.unpack_from(">I", section_data, offset + 8)[0]
                    offset += max(entry_total, 12)
                else:
                    break
                continue

            if offset + 56 > len(section_data):
                break

            entry_header_len = struct.unpack_from(">I", section_data, offset + 4)[0]
            entry_total_len = struct.unpack_from(">I", section_data, offset + 8)[0]

            # PCPT layout (56 bytes total):
            #   tag(4) + header_len(4) + total_len(4) + hot_cue(4) + status(4) +
            #   u1(4) + order_first(2) + order_last(2) + type(1) + pad(1) + u2(2) +
            #   time(4) + loop_time(4) + pad(16)
            hot_cue_num = struct.unpack_from(">I", section_data, offset + 12)[0]
            cue_point_type = struct.unpack_from(">B", section_data, offset + 28)[0]  # 1=single, 2=loop
            time_ms = struct.unpack_from(">I", section_data, offset + 32)[0]

            cue = {
                "slot": hot_cue_num if is_hot else 0,
                "time_ms": float(time_ms),
                "type": cue_point_type,
            }

            if is_hot:
                hot_cues.append(cue)
            else:
                memory_cues.append(cue)

            offset += entry_total_len

    return hot_cues, memory_cues


# ---------------------------------------------------------------------------
# PSSI phrase kind lookup tables (keyed by mood)
# ---------------------------------------------------------------------------

MOOD_HIGH_PHRASES: dict[int, str] = {
    1: "intro", 2: "up", 3: "down", 4: "chorus",
    5: "outro", 6: "verse", 7: "bridge", 8: "unknown",
}

MOOD_MID_PHRASES: dict[int, str] = {
    1: "intro", 2: "verse", 3: "chorus", 4: "bridge",
    5: "outro", 6: "verse", 7: "bridge", 8: "unknown",
}

MOOD_LOW_PHRASES: dict[int, str] = {
    1: "intro", 2: "verse", 3: "chorus", 4: "bridge",
    5: "outro", 6: "verse", 7: "bridge", 8: "unknown",
}

_MOOD_TABLES: dict[int, dict[int, str]] = {
    1: MOOD_HIGH_PHRASES,
    2: MOOD_MID_PHRASES,
    3: MOOD_LOW_PHRASES,
}

# Normalize to the labels consumed by LiveStrataAnalyzer.PHRASE_KIND_MAP
_PHRASE_NORMALIZE: dict[str, str] = {
    "up": "build",
    "down": "breakdown",
}


def _resolve_phrase_kind(mood: int, kind_id: int) -> str:
    """Map a PSSI kind_id to a normalized phrase label string."""
    table = _MOOD_TABLES.get(mood, MOOD_MID_PHRASES)
    raw = table.get(kind_id, "unknown")
    return _PHRASE_NORMALIZE.get(raw, raw)


# ---------------------------------------------------------------------------
# PSSI — phrase / song-structure analysis
# ---------------------------------------------------------------------------

def parse_anlz_phrases(path: Path) -> list[dict]:
    """Parse PSSI phrase analysis from an ANLZ .EXT or .2EX file.

    Returns list of {"start_beat": int, "end_beat": int, "kind": str, "mood": int}.
    Raises AnlzParseError on failure.
    """
    try:
        data = path.read_bytes()
    except OSError as e:
        raise AnlzParseError(f"Cannot read {path}: {e}") from e

    sections = _read_sections(data)

    for tag, section_data in sections:
        if tag != "PSSI":
            continue

        # PSSI body layout (offsets relative to section start):
        #   12: len_entry_bytes (u32)
        #   16: mood (u16)
        #   18: padding (6 bytes)
        #   24: end_beat (u16)
        #   26: padding (2 bytes)
        #   28: entry_count (u16)
        #   30: entries start
        if len(section_data) < 30:
            raise AnlzParseError(
                f"PSSI section too small: {len(section_data)} bytes"
            )

        try:
            len_entry_bytes = struct.unpack_from(">I", section_data, 12)[0]
            mood = struct.unpack_from(">H", section_data, 16)[0]
            body_end_beat = struct.unpack_from(">H", section_data, 24)[0]
            entry_count = struct.unpack_from(">H", section_data, 28)[0]
        except struct.error as e:
            raise AnlzParseError(f"PSSI header unpack failed: {e}") from e

        if len_entry_bytes == 0:
            raise AnlzParseError("PSSI len_entry_bytes is 0")

        entries_offset = 30
        raw_entries: list[tuple[int, int, int]] = []  # (beat, kind_id, phrase_number)

        for i in range(entry_count):
            entry_start = entries_offset + i * len_entry_bytes
            if entry_start + 6 > len(section_data):
                raise AnlzParseError(
                    f"PSSI truncated at entry {i}/{entry_count}"
                )
            try:
                phrase_number = struct.unpack_from(">H", section_data, entry_start)[0]
                beat = struct.unpack_from(">H", section_data, entry_start + 2)[0]
                kind_id = struct.unpack_from(">H", section_data, entry_start + 4)[0]
            except struct.error as e:
                raise AnlzParseError(
                    f"PSSI entry {i} unpack failed: {e}"
                ) from e
            raw_entries.append((beat, kind_id, phrase_number))

        # Build output with end-beat derivation
        phrases: list[dict] = []
        for idx, (beat, kind_id, _phrase_num) in enumerate(raw_entries):
            if idx + 1 < len(raw_entries):
                end_beat = raw_entries[idx + 1][0]
            else:
                end_beat = body_end_beat

            phrases.append({
                "start_beat": beat,
                "end_beat": end_beat,
                "kind": _resolve_phrase_kind(mood, kind_id),
                "mood": mood,
            })

        return phrases

    # No PSSI section found
    return []


# ---------------------------------------------------------------------------
# PPTH — original file path
# ---------------------------------------------------------------------------

def parse_anlz_file_path(path: Path) -> str | None:
    """Parse PPTH tag to extract the original audio file path.

    Returns the path string, or None if no PPTH tag found.
    Raises AnlzParseError on malformed data.
    """
    try:
        data = path.read_bytes()
    except OSError as e:
        raise AnlzParseError(f"Cannot read {path}: {e}") from e

    sections = _read_sections(data)

    for tag, section_data in sections:
        if tag != "PPTH":
            continue

        # PPTH layout: tag(4) + header_len(4) + total_len(4) + len_path(4) + path_bytes
        if len(section_data) < 16:
            raise AnlzParseError(
                f"PPTH section too small: {len(section_data)} bytes"
            )

        try:
            len_path = struct.unpack_from(">I", section_data, 12)[0]
        except struct.error as e:
            raise AnlzParseError(f"PPTH path length unpack failed: {e}") from e

        path_start = 16
        path_end = path_start + len_path
        if path_end > len(section_data):
            raise AnlzParseError(
                f"PPTH path data extends beyond section "
                f"(need {path_end}, have {len(section_data)})"
            )

        path_bytes = section_data[path_start:path_end]
        try:
            file_path = path_bytes.decode("utf-16-be").rstrip("\x00")
        except UnicodeDecodeError as e:
            raise AnlzParseError(f"PPTH path decode failed: {e}") from e

        return file_path

    return None
