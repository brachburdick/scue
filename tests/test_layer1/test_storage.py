"""Tests for JSON file storage and SQLite cache."""

from pathlib import Path

from scue.layer1.models import Section, TrackAnalysis, TrackFeatures
from scue.layer1.storage import TrackCache, TrackStore


def _make_analysis(fingerprint: str = "a" * 64, title: str = "Test Track") -> TrackAnalysis:
    """Create a minimal TrackAnalysis for testing."""
    return TrackAnalysis(
        fingerprint=fingerprint,
        audio_path="/test/track.mp3",
        title=title,
        bpm=128.0,
        beats=[0.0, 0.469],
        downbeats=[0.0],
        sections=[
            Section(label="intro", start=0.0, end=16.0, original_label="intro"),
            Section(label="drop", start=16.0, end=48.0, original_label="chorus"),
        ],
        features=TrackFeatures(energy_curve=[0.5], mood="neutral"),
        duration=180.0,
    )


class TestTrackStore:
    """Tests for JSON file storage."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")
        analysis = _make_analysis()

        store.save(analysis)
        loaded = store.load(analysis.fingerprint)

        assert loaded is not None
        assert loaded.fingerprint == analysis.fingerprint
        assert loaded.bpm == 128.0
        assert len(loaded.sections) == 2

    def test_exists(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")
        analysis = _make_analysis()

        assert not store.exists(analysis.fingerprint)
        store.save(analysis)
        assert store.exists(analysis.fingerprint)

    def test_list_all(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")

        store.save(_make_analysis("a" * 64, "Track A"))
        store.save(_make_analysis("b" * 64, "Track B"))

        fingerprints = store.list_all()
        assert len(fingerprints) == 2
        assert "a" * 64 in fingerprints
        assert "b" * 64 in fingerprints

    def test_versioned_save(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")

        # Save v1
        analysis = _make_analysis()
        store.save(analysis)

        # Save v2 (enriched)
        analysis.version = 2
        analysis.source = "pioneer_enriched"
        analysis.pioneer_bpm = 128.5
        store.save(analysis)

        # Both versions should exist
        v1 = store.load("a" * 64, version=1)
        v2 = store.load("a" * 64, version=2)
        assert v1 is not None
        assert v2 is not None
        assert v2.pioneer_bpm == 128.5

    def test_load_latest(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")

        analysis = _make_analysis()
        store.save(analysis)

        # Save enriched version
        analysis.version = 2
        analysis.bpm = 128.5
        store.save(analysis)

        latest = store.load_latest("a" * 64)
        assert latest is not None
        assert latest.version == 2
        assert latest.bpm == 128.5

    def test_delete(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")
        analysis = _make_analysis()
        store.save(analysis)

        assert store.exists(analysis.fingerprint)
        store.delete(analysis.fingerprint)
        assert not store.exists(analysis.fingerprint)


class TestTrackCache:
    """Tests for SQLite cache."""

    def test_index_and_list(self, tmp_path: Path) -> None:
        cache = TrackCache(tmp_path / "cache" / "scue.db")
        analysis = _make_analysis()

        cache.index_analysis(analysis)

        tracks = cache.list_tracks()
        assert len(tracks) == 1
        assert tracks[0]["fingerprint"] == "a" * 64
        assert tracks[0]["bpm"] == 128.0
        assert tracks[0]["title"] == "Test Track"

    def test_count(self, tmp_path: Path) -> None:
        cache = TrackCache(tmp_path / "cache" / "scue.db")

        assert cache.count_tracks() == 0
        cache.index_analysis(_make_analysis("a" * 64))
        assert cache.count_tracks() == 1
        cache.index_analysis(_make_analysis("b" * 64))
        assert cache.count_tracks() == 2

    def test_get_track(self, tmp_path: Path) -> None:
        cache = TrackCache(tmp_path / "cache" / "scue.db")
        cache.index_analysis(_make_analysis())

        track = cache.get_track("a" * 64)
        assert track is not None
        assert track["bpm"] == 128.0

    def test_latest_version_in_list(self, tmp_path: Path) -> None:
        """List should return the latest version of each track."""
        cache = TrackCache(tmp_path / "cache" / "scue.db")

        # Index v1
        analysis = _make_analysis()
        cache.index_analysis(analysis)

        # Index v2
        analysis.version = 2
        analysis.bpm = 128.5
        cache.index_analysis(analysis)

        tracks = cache.list_tracks()
        assert len(tracks) == 1
        assert tracks[0]["version"] == 2
        assert tracks[0]["bpm"] == 128.5

    def test_rebuild_from_store(self, tmp_path: Path) -> None:
        tracks_dir = tmp_path / "tracks"
        store = TrackStore(tracks_dir)
        cache = TrackCache(tmp_path / "cache" / "scue.db")

        # Save some analyses
        store.save(_make_analysis("a" * 64, "Track A"))
        store.save(_make_analysis("b" * 64, "Track B"))

        # Rebuild cache
        count = cache.rebuild_from_store(store)
        assert count == 2
        assert cache.count_tracks() == 2
