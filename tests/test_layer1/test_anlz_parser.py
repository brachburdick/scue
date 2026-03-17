"""Tests for the custom minimal ANLZ parser (fallback for pyrekordbox)."""

import struct
from pathlib import Path

import pytest

from scue.layer1.anlz_parser import (
    AnlzParseError,
    parse_anlz_beatgrid,
    parse_anlz_cues,
)


def _build_pmai_header(file_total_len: int = 4096) -> bytes:
    """Build the PMAI file header (28 bytes).

    file_total_len is deliberately different from header_len (28) to catch
    bugs where code reads the wrong field as the header offset. Real ANLZ
    files have header_len=28 but file_total_len=thousands of bytes.
    """
    tag = b"PMAI"
    header_len = 28
    return struct.pack(">4sII", tag, header_len, file_total_len) + b"\x00" * 16


def _build_pqtz_section(entries: list[tuple[int, int, int]]) -> bytes:
    """Build a PQTZ beat grid section.

    entries: list of (beat_number, tempo_x100, time_ms)
    """
    tag = b"PQTZ"
    header_len = 24
    entry_count = len(entries)
    # Header: tag(4) + header_len(4) + total_len(4) + u1(4) + u2(4) + count(4)
    total_len = header_len + entry_count * 16

    header = struct.pack(">4sIIIII", tag, header_len, total_len, 0, 0, entry_count)

    body = b""
    for beat_num, tempo_x100, time_ms in entries:
        # Entry: beat_number(u16) + tempo(u16) + time_ms(u32) + padding(8)
        body += struct.pack(">HHI", beat_num, tempo_x100, time_ms) + b"\x00" * 8

    return header + body


def _build_unknown_section(tag_name: str = "XXXX", size: int = 32) -> bytes:
    """Build an unknown/dummy section."""
    tag = tag_name.encode("ascii")
    header_len = 12
    total_len = max(size, 12)
    header = struct.pack(">4sII", tag, header_len, total_len)
    body = b"\x00" * (total_len - 12)
    return header + body


def _build_pcob_section(
    cue_type: int, entries: list[tuple[int, int, int]]
) -> bytes:
    """Build a PCOB cue list section.

    cue_type: 0=memory, 1=hotcue
    entries: list of (hot_cue_num, cue_point_type, time_ms)
    """
    # Build PCPT entries first
    pcpt_data = b""
    for hot_cue_num, cue_point_type, time_ms in entries:
        pcpt_header_len = 24
        pcpt_total_len = 56
        pcpt = struct.pack(">4sII", b"PCPT", pcpt_header_len, pcpt_total_len)
        # hot_cue(4) + status(4) + u1(4) + order_first(2) + order_last(2)
        pcpt += struct.pack(">III", hot_cue_num, 4, 0x10000)  # status=enabled
        pcpt += struct.pack(">HH", 0xFFFF, 1)
        # type(1) + pad(1) + u2(2) + time(4) + loop_time(4) + pad(16)
        pcpt += struct.pack(">BxHI", cue_point_type, 1000, time_ms)
        pcpt += struct.pack(">I", 0xFFFFFFFF)  # loop_time = -1
        pcpt += b"\x00" * 16
        pcpt_data += pcpt

    # PCOB header: tag(4) + header_len(4) + total_len(4) + cue_type(4) + u(2) + count(2) + pad(4)
    tag = b"PCOB"
    header_len = 24
    total_len = header_len + len(pcpt_data)
    entry_count = len(entries)
    header = struct.pack(">4sIIIHH", tag, header_len, total_len, cue_type, 0, entry_count)
    header += b"\x00" * 4  # pad to 24 bytes total

    return header + pcpt_data


def _write_anlz(tmp_path: Path, *sections: bytes) -> Path:
    """Write a complete ANLZ file with the given sections."""
    dat_path = tmp_path / "ANLZ0000.DAT"
    data = _build_pmai_header()
    for section in sections:
        data += section
    dat_path.write_bytes(data)
    return dat_path


# ── Beat Grid Tests ────────────────────────────────────────────────────────


class TestParseAnlzBeatgrid:
    def test_valid_beatgrid(self, tmp_path):
        """Parse a valid PQTZ section with 3 beats."""
        pqtz = _build_pqtz_section([
            (1, 12800, 250),   # beat 1, 128.00 BPM, 250ms
            (2, 12800, 719),   # beat 2, 128.00 BPM, 719ms
            (3, 12800, 1187),  # beat 3, 128.00 BPM, 1187ms
        ])
        dat = _write_anlz(tmp_path, pqtz)
        result = parse_anlz_beatgrid(dat)

        assert len(result) == 3
        assert result[0] == {"beat_number": 1, "time_ms": 250.0, "bpm": 128.0}
        assert result[1] == {"beat_number": 2, "time_ms": 719.0, "bpm": 128.0}
        assert result[2] == {"beat_number": 3, "time_ms": 1187.0, "bpm": 128.0}

    def test_variable_bpm(self, tmp_path):
        """Beat grid with varying tempos."""
        pqtz = _build_pqtz_section([
            (1, 12000, 0),     # 120.00 BPM
            (2, 12500, 500),   # 125.00 BPM
        ])
        dat = _write_anlz(tmp_path, pqtz)
        result = parse_anlz_beatgrid(dat)

        assert len(result) == 2
        assert result[0]["bpm"] == 120.0
        assert result[1]["bpm"] == 125.0

    def test_skips_unknown_sections(self, tmp_path):
        """Parser skips unknown sections before PQTZ."""
        unknown = _build_unknown_section("PWAV", 64)
        pqtz = _build_pqtz_section([(1, 12800, 250)])
        dat = _write_anlz(tmp_path, unknown, pqtz)
        result = parse_anlz_beatgrid(dat)

        assert len(result) == 1
        assert result[0]["beat_number"] == 1

    def test_no_pqtz_returns_empty(self, tmp_path):
        """File with no PQTZ section returns empty list."""
        unknown = _build_unknown_section("PWAV", 64)
        dat = _write_anlz(tmp_path, unknown)
        result = parse_anlz_beatgrid(dat)

        assert result == []

    def test_empty_pqtz(self, tmp_path):
        """PQTZ section with zero entries."""
        pqtz = _build_pqtz_section([])
        dat = _write_anlz(tmp_path, pqtz)
        result = parse_anlz_beatgrid(dat)

        assert result == []

    def test_not_anlz_file(self, tmp_path):
        """Non-ANLZ file raises AnlzParseError."""
        dat = tmp_path / "not_anlz.dat"
        dat.write_bytes(b"NOT_ANLZ_DATA_HERE")
        with pytest.raises(AnlzParseError, match="Not an ANLZ file"):
            parse_anlz_beatgrid(dat)

    def test_empty_file(self, tmp_path):
        """Empty file raises AnlzParseError."""
        dat = tmp_path / "empty.dat"
        dat.write_bytes(b"")
        with pytest.raises(AnlzParseError, match="too small"):
            parse_anlz_beatgrid(dat)

    def test_missing_file(self, tmp_path):
        """Missing file raises AnlzParseError."""
        dat = tmp_path / "missing.dat"
        with pytest.raises(AnlzParseError, match="Cannot read"):
            parse_anlz_beatgrid(dat)

    def test_truncated_entries(self, tmp_path):
        """PQTZ claims 3 entries but file is truncated — parses what it can."""
        pqtz = _build_pqtz_section([(1, 12800, 250), (2, 12800, 719)])
        # Claim 3 entries but only provide 2
        pqtz = pqtz[:24] + struct.pack(">I", 3)[0:4]  # This won't work right
        # Better: manually build a truncated section
        tag = b"PQTZ"
        entry_count = 3
        # Only include data for 2 entries (32 bytes) not 3 (48 bytes)
        entries_data = b""
        entries_data += struct.pack(">HHI", 1, 12800, 250) + b"\x00" * 8
        entries_data += struct.pack(">HHI", 2, 12800, 719) + b"\x00" * 8
        header = struct.pack(
            ">4sIIIII", tag, 24, 24 + len(entries_data), 0, 0, entry_count
        )
        section = header + entries_data
        dat = _write_anlz(tmp_path, section)
        result = parse_anlz_beatgrid(dat)

        # Should parse the 2 complete entries and warn about truncation
        assert len(result) == 2


# ── Cue List Tests ─────────────────────────────────────────────────────────


class TestParseAnlzCues:
    def test_hot_cues(self, tmp_path):
        """Parse hot cues from PCOB section."""
        pcob = _build_pcob_section(1, [  # cue_type=1 (hotcue)
            (1, 1, 5000),   # hot cue A at 5000ms, type=single
            (2, 1, 30000),  # hot cue B at 30000ms, type=single
        ])
        dat = _write_anlz(tmp_path, pcob)
        hot, mem = parse_anlz_cues(dat)

        assert len(hot) == 2
        assert len(mem) == 0
        assert hot[0] == {"slot": 1, "time_ms": 5000.0, "type": 1}
        assert hot[1] == {"slot": 2, "time_ms": 30000.0, "type": 1}

    def test_memory_cues(self, tmp_path):
        """Parse memory cues from PCOB section."""
        pcob = _build_pcob_section(0, [  # cue_type=0 (memory)
            (0, 1, 10000),  # memory cue at 10000ms
            (0, 2, 60000),  # loop cue at 60000ms
        ])
        dat = _write_anlz(tmp_path, pcob)
        hot, mem = parse_anlz_cues(dat)

        assert len(hot) == 0
        assert len(mem) == 2
        assert mem[0] == {"slot": 0, "time_ms": 10000.0, "type": 1}
        assert mem[1] == {"slot": 0, "time_ms": 60000.0, "type": 2}

    def test_both_hot_and_memory(self, tmp_path):
        """File with both hot cue and memory cue PCOB sections."""
        pcob_hot = _build_pcob_section(1, [(1, 1, 5000)])
        pcob_mem = _build_pcob_section(0, [(0, 1, 10000)])
        dat = _write_anlz(tmp_path, pcob_hot, pcob_mem)
        hot, mem = parse_anlz_cues(dat)

        assert len(hot) == 1
        assert len(mem) == 1

    def test_no_pcob_returns_empty(self, tmp_path):
        """File with no PCOB section returns empty lists."""
        pqtz = _build_pqtz_section([(1, 12800, 250)])
        dat = _write_anlz(tmp_path, pqtz)
        hot, mem = parse_anlz_cues(dat)

        assert hot == []
        assert mem == []
