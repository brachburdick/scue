"""Tests for Layer 1 divergence logging."""

import tempfile
from pathlib import Path

from scue.layer1.divergence import log_divergence, query_divergences
from scue.layer1.models import DivergenceRecord
from scue.layer1.storage import TrackCache


def _make_cache(tmp_path: Path) -> TrackCache:
    return TrackCache(tmp_path / "test.db")


class TestLogDivergence:
    def test_creates_record(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        record = log_divergence(
            cache, "abc123def456", "bpm", 128.0, 127.5, "pioneer_adopted"
        )
        assert isinstance(record, DivergenceRecord)
        assert record.track_fingerprint == "abc123def456"
        assert record.divergence_field == "bpm"
        assert record.scue_value == "128.0"
        assert record.pioneer_value == "127.5"
        assert record.resolution == "pioneer_adopted"
        assert record.timestamp > 0

    def test_persists_to_cache(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        log_divergence(cache, "fp1", "bpm", 128.0, 127.5)
        log_divergence(cache, "fp1", "key", "Cm", "Dm")
        log_divergence(cache, "fp2", "beatgrid", "500 beats", "510 beats")

        all_records = query_divergences(cache)
        assert len(all_records) == 3

    def test_filter_by_fingerprint(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        log_divergence(cache, "fp1", "bpm", 128.0, 127.5)
        log_divergence(cache, "fp2", "bpm", 130.0, 129.0)

        results = query_divergences(cache, track_fingerprint="fp1")
        assert len(results) == 1
        assert results[0].track_fingerprint == "fp1"

    def test_filter_by_field(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        log_divergence(cache, "fp1", "bpm", 128.0, 127.5)
        log_divergence(cache, "fp1", "key", "Cm", "Dm")

        results = query_divergences(cache, divergence_field="key")
        assert len(results) == 1
        assert results[0].divergence_field == "key"

    def test_filter_by_both(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        log_divergence(cache, "fp1", "bpm", 128.0, 127.5)
        log_divergence(cache, "fp1", "key", "Cm", "Dm")
        log_divergence(cache, "fp2", "bpm", 130.0, 129.0)

        results = query_divergences(cache, track_fingerprint="fp1", divergence_field="bpm")
        assert len(results) == 1
        assert results[0].scue_value == "128.0"

    def test_default_resolution(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        record = log_divergence(cache, "fp1", "bpm", 128.0, 127.5)
        assert record.resolution == "pioneer_adopted"
