"""Tests for audio fingerprinting."""

import tempfile
from pathlib import Path

import pytest

from scue.layer1.fingerprint import compute_fingerprint


class TestFingerprint:
    """Tests for SHA256 audio fingerprinting."""

    def test_deterministic(self, tmp_path: Path) -> None:
        """Same file content produces same fingerprint."""
        f = tmp_path / "test.mp3"
        f.write_bytes(b"fake audio content" * 100)

        fp1 = compute_fingerprint(f)
        fp2 = compute_fingerprint(f)
        assert fp1 == fp2

    def test_different_content(self, tmp_path: Path) -> None:
        """Different file content produces different fingerprint."""
        f1 = tmp_path / "track1.mp3"
        f2 = tmp_path / "track2.mp3"
        f1.write_bytes(b"content A" * 100)
        f2.write_bytes(b"content B" * 100)

        assert compute_fingerprint(f1) != compute_fingerprint(f2)

    def test_hex_format(self, tmp_path: Path) -> None:
        """Fingerprint should be a 64-char hex string (SHA256)."""
        f = tmp_path / "test.mp3"
        f.write_bytes(b"test content")

        fp = compute_fingerprint(f)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_file_not_found(self) -> None:
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            compute_fingerprint("/nonexistent/file.mp3")

    def test_large_file(self, tmp_path: Path) -> None:
        """Should handle files larger than chunk size."""
        f = tmp_path / "large.mp3"
        # Write 256KB — larger than the 64KB chunk size
        f.write_bytes(b"x" * 256 * 1024)
        fp = compute_fingerprint(f)
        assert len(fp) == 64
