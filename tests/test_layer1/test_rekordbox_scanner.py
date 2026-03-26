"""Tests for the local rekordbox library scanner."""

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scue.layer1.rekordbox_scanner import (
    LocalTrack,
    detect_library,
    scan_local_library,
    match_local_tracks,
    _local_to_usb,
)


# ── ANLZ binary fixture builders ──────────────────────────────────────

def _pmai_header(file_total_len: int = 4096) -> bytes:
    """Build the PMAI file header (28 bytes)."""
    tag = b"PMAI"
    header_len = 28
    return struct.pack(">4sII", tag, header_len, file_total_len) + b"\x00" * 16


def _ppth_section(file_path: str) -> bytes:
    """Build a PPTH section with a UTF-16-BE encoded path."""
    path_bytes = file_path.encode("utf-16-be")
    header_len = 12
    len_path = len(path_bytes)
    body = struct.pack(">I", len_path) + path_bytes
    total_len = header_len + len(body)
    header = struct.pack(">4sII", b"PPTH", header_len, total_len)
    return header + body


def _pqtz_section(entries: list[tuple[int, int, int]]) -> bytes:
    """Build a PQTZ beat grid section.

    entries: list of (beat_number, tempo_x100, time_ms)
    """
    tag = b"PQTZ"
    header_len = 24
    entry_count = len(entries)
    total_len = header_len + entry_count * 16
    header = struct.pack(">4sIIIII", tag, header_len, total_len, 0, 0, entry_count)
    body = b""
    for beat_num, tempo_x100, time_ms in entries:
        body += struct.pack(">HHI", beat_num, tempo_x100, time_ms) + b"\x00" * 8
    return header + body


def _write_anlz(tmp_path: Path, filename: str, *sections: bytes) -> Path:
    """Write a complete ANLZ file from sections."""
    data = _pmai_header()
    for s in sections:
        data += s
    out = tmp_path / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


# ── detect_library ────────────────────────────────────────────────────

class TestDetectLibrary:
    def test_detect_library_found(self, tmp_path: Path) -> None:
        """Mock Path.exists() to simulate finding a rekordbox library."""
        fake_anlz = tmp_path / "USBANLZ"
        fake_anlz.mkdir()
        # Create some .DAT files
        (fake_anlz / "P001").mkdir()
        (fake_anlz / "P001" / "ANLZ0000.DAT").write_bytes(b"fake")
        (fake_anlz / "P001" / "ANLZ0001.DAT").write_bytes(b"fake")

        with patch("scue.layer1.rekordbox_scanner.REKORDBOX_ANLZ_PATHS", [fake_anlz]):
            result = detect_library()

        assert result is not None
        assert result["path"] == str(fake_anlz)
        assert result["dat_count"] == 2

    def test_detect_library_not_found(self) -> None:
        """When no known paths exist, returns None."""
        with patch("scue.layer1.rekordbox_scanner.REKORDBOX_ANLZ_PATHS", [Path("/nonexistent/path")]):
            result = detect_library()
        assert result is None


# ── scan_local_library ────────────────────────────────────────────────

class TestScanLocalLibrary:
    def test_scan_single_dat_file(self, tmp_path: Path) -> None:
        """Parse a minimal .DAT with PPTH + PQTZ and verify LocalTrack fields."""
        _write_anlz(
            tmp_path, "P001/ANLZ0000.DAT",
            _ppth_section("/Users/dj/Music/Track One.mp3"),
            _pqtz_section([(1, 12800, 0), (2, 12800, 469)]),
        )

        tracks = scan_local_library(tmp_path)

        assert len(tracks) == 1
        t = tracks[0]
        assert t.file_path == "/Users/dj/Music/Track One.mp3"
        assert t.anlz_path == "P001/ANLZ0000.DAT"
        assert len(t.beatgrid) == 2
        assert t.beatgrid[0]["bpm"] == 128.0
        assert t.beatgrid[1]["time_ms"] == 469.0

    def test_scan_skips_corrupt_files(self, tmp_path: Path) -> None:
        """Non-ANLZ files are skipped without aborting the scan."""
        # Write a corrupt file
        corrupt = tmp_path / "BAD" / "ANLZ0000.DAT"
        corrupt.parent.mkdir(parents=True)
        corrupt.write_bytes(b"this is not an ANLZ file at all")

        # Write a valid file
        _write_anlz(
            tmp_path, "GOOD/ANLZ0000.DAT",
            _ppth_section("/Music/Good Track.aiff"),
            _pqtz_section([(1, 13000, 0)]),
        )

        tracks = scan_local_library(tmp_path)

        # Only the valid track should survive
        assert len(tracks) == 1
        assert tracks[0].file_path == "/Music/Good Track.aiff"

    def test_scan_skips_no_ppth(self, tmp_path: Path) -> None:
        """DAT files without a PPTH tag are skipped (can't identify audio file)."""
        _write_anlz(
            tmp_path, "P001/ANLZ0000.DAT",
            _pqtz_section([(1, 12800, 0)]),  # beatgrid only, no PPTH
        )

        tracks = scan_local_library(tmp_path)
        assert len(tracks) == 0

    def test_progress_callback(self, tmp_path: Path) -> None:
        """Progress callback receives (current, total) for each file."""
        _write_anlz(
            tmp_path, "P001/ANLZ0000.DAT",
            _ppth_section("/Music/A.mp3"),
            _pqtz_section([(1, 12800, 0)]),
        )
        _write_anlz(
            tmp_path, "P002/ANLZ0000.DAT",
            _ppth_section("/Music/B.mp3"),
            _pqtz_section([(1, 13000, 0)]),
        )

        calls: list[tuple[int, int]] = []
        scan_local_library(tmp_path, progress_cb=lambda cur, tot: calls.append((cur, tot)))

        assert len(calls) == 2
        assert calls[0] == (1, 2)
        assert calls[1] == (2, 2)


# ── LocalTrack → UsbTrack conversion ─────────────────────────────────

class TestLocalToUsbConversion:
    def test_local_track_to_usb_track_conversion(self) -> None:
        """Verify the adapter creates a valid UsbTrack from LocalTrack."""
        local = LocalTrack(
            anlz_path="P001/ANLZ0000.DAT",
            file_path="/Users/dj/Music/Cool Track.mp3",
            beatgrid=[{"beat_number": 1, "time_ms": 0.0, "bpm": 128.0}],
            hot_cues=[{"slot": 1, "time_ms": 5000.0, "type": 1}],
            memory_points=[{"slot": 0, "time_ms": 30000.0, "type": 1}],
        )

        usb = _local_to_usb(local)

        assert usb.rekordbox_id == 0
        assert usb.title == "Cool Track"  # stem of file_path
        assert usb.artist == ""
        assert usb.bpm == 128.0  # from first beatgrid entry
        assert usb.file_path == "/Users/dj/Music/Cool Track.mp3"
        assert usb.anlz_path == "P001/ANLZ0000.DAT"
        assert len(usb.beatgrid) == 1
        assert len(usb.hot_cues) == 1
        assert len(usb.memory_points) == 1

    def test_local_track_empty_beatgrid_bpm_zero(self) -> None:
        """When beatgrid is empty, BPM should be 0.0."""
        local = LocalTrack(
            anlz_path="P001/ANLZ0000.DAT",
            file_path="/Music/No Grid.wav",
        )

        usb = _local_to_usb(local)
        assert usb.bpm == 0.0
