"""Tests for PSSI (phrase analysis) and PPTH (file path) ANLZ parsing."""

import struct
from pathlib import Path

import pytest

from scue.layer1.anlz_parser import (
    AnlzParseError,
    parse_anlz_file_path,
    parse_anlz_phrases,
)


# ---------------------------------------------------------------------------
# Helpers — build synthetic ANLZ binary data
# ---------------------------------------------------------------------------

def _pmai_header() -> bytes:
    """Minimal PMAI file header (28 bytes)."""
    tag = b"PMAI"
    header_len = 28
    # file_len is set to 0 — _read_sections doesn't validate it
    return struct.pack(">4sII", tag, header_len, 0) + b"\x00" * 16


def _pssi_section(
    mood: int,
    end_beat: int,
    entries: list[tuple[int, int, int]],  # (phrase_number, beat, kind_id)
    len_entry_bytes: int = 24,
) -> bytes:
    """Build a PSSI section from parameters.

    Each entry is len_entry_bytes wide; only first 6 bytes are meaningful.
    """
    entry_count = len(entries)

    # Body: len_entry_bytes(4) + mood(2) + pad(6) + end_beat(2) + pad(2) + entry_count(2) = 18 bytes
    body = struct.pack(">I", len_entry_bytes)
    body += struct.pack(">H", mood)
    body += b"\x00" * 6  # padding
    body += struct.pack(">H", end_beat)
    body += b"\x00" * 2  # padding
    body += struct.pack(">H", entry_count)

    for phrase_number, beat, kind_id in entries:
        entry = struct.pack(">HHH", phrase_number, beat, kind_id)
        entry += b"\x00" * (len_entry_bytes - 6)  # pad to len_entry_bytes
        body += entry

    total_len = 12 + len(body)
    header = struct.pack(">4sII", b"PSSI", 12, total_len)
    return header + body


def _ppth_section(file_path: str) -> bytes:
    """Build a PPTH section with a UTF-16-BE encoded path."""
    path_bytes = file_path.encode("utf-16-be")
    header_len = 12  # standard section header size
    len_path = len(path_bytes)
    body = struct.pack(">I", len_path) + path_bytes
    total_len = header_len + len(body)
    header = struct.pack(">4sII", b"PPTH", header_len, total_len)
    return header + body


def _dummy_section(tag: str, body_size: int = 8) -> bytes:
    """Build a dummy ANLZ section with the given tag."""
    body = b"\x00" * body_size
    total_len = 12 + body_size
    return struct.pack(">4sII", tag.encode("ascii"), 12, total_len) + body


def _write_anlz(tmp_path: Path, *sections: bytes) -> Path:
    """Write a complete ANLZ file from sections, return its Path."""
    data = _pmai_header()
    for s in sections:
        data += s
    p = tmp_path / "test.ext"
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------------------
# PSSI tests
# ---------------------------------------------------------------------------

class TestParsePssiBasic:
    """test_parse_pssi_basic — 3 phrases, verify output shape and kind strings."""

    def test_three_phrases(self, tmp_path: Path) -> None:
        # mood=2 (mid): kind 1=intro, 2=verse, 3=chorus
        entries = [
            (1, 1, 1),    # phrase 1, beat 1, kind=intro
            (2, 33, 2),   # phrase 2, beat 33, kind=verse
            (3, 97, 3),   # phrase 3, beat 97, kind=chorus
        ]
        section = _pssi_section(mood=2, end_beat=161, entries=entries)
        p = _write_anlz(tmp_path, section)

        result = parse_anlz_phrases(p)

        assert len(result) == 3
        assert result[0] == {"start_beat": 1, "end_beat": 33, "kind": "intro", "mood": 2}
        assert result[1] == {"start_beat": 33, "end_beat": 97, "kind": "verse", "mood": 2}
        assert result[2] == {"start_beat": 97, "end_beat": 161, "kind": "chorus", "mood": 2}


class TestParsePssiEmpty:
    """test_parse_pssi_empty — no PSSI tag → returns []."""

    def test_no_pssi_tag(self, tmp_path: Path) -> None:
        dummy = _dummy_section("PQTZ")
        p = _write_anlz(tmp_path, dummy)
        assert parse_anlz_phrases(p) == []


class TestParsePssiSingleEntry:
    """test_parse_pssi_single_entry — one phrase, end_beat from body."""

    def test_single_entry(self, tmp_path: Path) -> None:
        entries = [(1, 1, 1)]  # intro starting at beat 1
        section = _pssi_section(mood=3, end_beat=129, entries=entries)
        p = _write_anlz(tmp_path, section)

        result = parse_anlz_phrases(p)

        assert len(result) == 1
        assert result[0]["start_beat"] == 1
        assert result[0]["end_beat"] == 129  # from body end_beat
        assert result[0]["kind"] == "intro"


class TestParsePssiMoodMapping:
    """test_parse_pssi_mood_mapping — mood=1 kind_id=2 → 'build' (not 'up')."""

    def test_high_mood_up_normalized(self, tmp_path: Path) -> None:
        entries = [(1, 1, 2)]  # mood=1, kind_id=2 → "up" → "build"
        section = _pssi_section(mood=1, end_beat=33, entries=entries)
        p = _write_anlz(tmp_path, section)

        result = parse_anlz_phrases(p)

        assert result[0]["kind"] == "build"

    def test_high_mood_down_normalized(self, tmp_path: Path) -> None:
        entries = [(1, 1, 3)]  # mood=1, kind_id=3 → "down" → "breakdown"
        section = _pssi_section(mood=1, end_beat=33, entries=entries)
        p = _write_anlz(tmp_path, section)

        result = parse_anlz_phrases(p)

        assert result[0]["kind"] == "breakdown"


class TestParsePssiUnknownKind:
    """test_parse_pssi_unknown_kind — kind_id=99 → 'unknown'."""

    def test_unknown_kind_id(self, tmp_path: Path) -> None:
        entries = [(1, 1, 99)]
        section = _pssi_section(mood=2, end_beat=33, entries=entries)
        p = _write_anlz(tmp_path, section)

        result = parse_anlz_phrases(p)

        assert result[0]["kind"] == "unknown"


class TestParsePssiTruncated:
    """test_parse_pssi_truncated — partial data raises AnlzParseError."""

    def test_truncated_entries(self, tmp_path: Path) -> None:
        # Build a section that claims 3 entries but only has bytes for 1
        entries = [(1, 1, 1)]
        section = _pssi_section(mood=2, end_beat=33, entries=entries, len_entry_bytes=24)

        # Patch entry_count to 3 while only having 1 entry's worth of data
        section_ba = bytearray(section)
        struct.pack_into(">H", section_ba, 28, 3)  # offset 28 from section start = entry_count
        section = bytes(section_ba)

        p = _write_anlz(tmp_path, section)

        with pytest.raises(AnlzParseError, match="truncated"):
            parse_anlz_phrases(p)


# ---------------------------------------------------------------------------
# PPTH tests
# ---------------------------------------------------------------------------

class TestParsePpthBasic:
    """test_parse_ppth_basic — extract a UTF-16-BE file path."""

    def test_extract_path(self, tmp_path: Path) -> None:
        original = "/Contents/Music/Artist/Track.mp3"
        section = _ppth_section(original)
        p = _write_anlz(tmp_path, section)

        result = parse_anlz_file_path(p)

        assert result == original

    def test_path_with_unicode(self, tmp_path: Path) -> None:
        original = "/Contents/Music/Björk/Début.mp3"
        section = _ppth_section(original)
        p = _write_anlz(tmp_path, section)

        assert parse_anlz_file_path(p) == original


class TestParsePpthMissing:
    """test_parse_ppth_missing — no PPTH tag → returns None."""

    def test_no_ppth_tag(self, tmp_path: Path) -> None:
        dummy = _dummy_section("PQTZ")
        p = _write_anlz(tmp_path, dummy)

        assert parse_anlz_file_path(p) is None
