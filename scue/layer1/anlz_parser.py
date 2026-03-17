"""Minimal ANLZ file parser — fallback for when pyrekordbox cannot handle a file.

Reads Pioneer ANLZ binary files (.DAT, .EXT) using the tag-length-value structure
documented by Deep Symmetry. Extracts only PQTZ (beat grid) and PCOB (cue list)
sections, skipping everything else.

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
