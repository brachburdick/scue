"""Integration tests for the analysis pipeline.

Tests marked @pytest.mark.slow require real audio files and analysis
dependencies (librosa, ruptures, optionally allin1-mlx).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Audio test tracks directory
AUDIO_DIR = Path("/Users/brach/Documents/Pirated Music/post-hibernation")

# 5 reference tracks spanning genres for testing
REFERENCE_TRACKS = [
    "Skrillex - Bangarang (Zero Bootleg).mp3",          # dubstep — clear drops
    "Kaivon - Think of Me.mp3",                          # melodic bass — builds + breakdowns
    "John Summit - Eat The Bass (WARCER Remix).mp3",     # house — steady energy
    "Champagne Drip - Fire Dub.mp3",                     # bass music — heavy sections
    "Furst.mp3",                                         # short track — fast test
]


def _audio_available() -> bool:
    """Check if the test audio directory exists and has files."""
    return AUDIO_DIR.exists() and any(AUDIO_DIR.glob("*.mp3"))


def _track_path(name: str) -> Path:
    """Get path for a reference track."""
    return AUDIO_DIR / name


skip_no_audio = pytest.mark.skipif(
    not _audio_available(),
    reason="Audio test tracks not available"
)


@skip_no_audio
class TestAnalysisPipeline:
    """Integration tests running the full pipeline on real audio."""

    @pytest.mark.slow
    def test_analyze_short_track(self, tmp_path: Path) -> None:
        """Analyze a short track end-to-end."""
        from scue.layer1.analysis import run_analysis

        track = _track_path("Furst.mp3")
        if not track.exists():
            pytest.skip(f"Track not found: {track.name}")

        analysis = run_analysis(
            audio_path=track,
            tracks_dir=tmp_path / "tracks",
            cache_path=tmp_path / "cache" / "scue.db",
            skip_waveform=True,
        )

        # Basic sanity checks
        assert analysis.fingerprint
        assert len(analysis.fingerprint) == 64
        assert analysis.bpm > 0
        assert analysis.duration > 0
        assert len(analysis.sections) >= 2  # at least intro + outro
        assert len(analysis.beats) > 0
        assert analysis.source == "analysis"
        assert analysis.version == 1

        # Sections should cover the track
        assert analysis.sections[0].start <= 1.0  # starts near beginning
        assert analysis.sections[-1].end >= analysis.duration * 0.9  # ends near end

        # First section should be intro, last should be outro
        assert analysis.sections[0].label == "intro"
        assert analysis.sections[-1].label == "outro"

    @pytest.mark.slow
    def test_analyze_with_waveform(self, tmp_path: Path) -> None:
        """Analyze with RGB waveform computation."""
        from scue.layer1.analysis import run_analysis

        track = _track_path("Furst.mp3")
        if not track.exists():
            pytest.skip(f"Track not found: {track.name}")

        analysis = run_analysis(
            audio_path=track,
            tracks_dir=tmp_path / "tracks",
            cache_path=tmp_path / "cache" / "scue.db",
            skip_waveform=False,
        )

        assert analysis.waveform is not None
        assert analysis.waveform.sample_rate == 60
        assert analysis.waveform.duration > 0
        assert len(analysis.waveform.low) > 0
        assert len(analysis.waveform.mid) > 0
        assert len(analysis.waveform.high) > 0
        # All values should be 0.0–1.0
        assert all(0.0 <= v <= 1.0 for v in analysis.waveform.low)

    @pytest.mark.slow
    def test_idempotent_analysis(self, tmp_path: Path) -> None:
        """Re-analyzing same file should return cached result."""
        from scue.layer1.analysis import run_analysis

        track = _track_path("Furst.mp3")
        if not track.exists():
            pytest.skip(f"Track not found: {track.name}")

        tracks_dir = tmp_path / "tracks"
        cache_path = tmp_path / "cache" / "scue.db"

        a1 = run_analysis(track, tracks_dir, cache_path, skip_waveform=True)
        a2 = run_analysis(track, tracks_dir, cache_path, skip_waveform=True)

        # Same fingerprint
        assert a1.fingerprint == a2.fingerprint

    @pytest.mark.slow
    def test_force_reanalysis(self, tmp_path: Path) -> None:
        """force=True should re-analyze even if cached."""
        from scue.layer1.analysis import run_analysis

        track = _track_path("Furst.mp3")
        if not track.exists():
            pytest.skip(f"Track not found: {track.name}")

        tracks_dir = tmp_path / "tracks"
        cache_path = tmp_path / "cache" / "scue.db"

        a1 = run_analysis(track, tracks_dir, cache_path, skip_waveform=True)
        a2 = run_analysis(track, tracks_dir, cache_path, skip_waveform=True, force=True)

        # Both should succeed
        assert a1.fingerprint == a2.fingerprint
        # Force should produce a fresh created_at
        assert a2.created_at >= a1.created_at

    @pytest.mark.slow
    def test_json_persistence(self, tmp_path: Path) -> None:
        """Analysis should be persisted as JSON and loadable."""
        from scue.layer1.analysis import run_analysis
        from scue.layer1.storage import TrackStore

        track = _track_path("Furst.mp3")
        if not track.exists():
            pytest.skip(f"Track not found: {track.name}")

        tracks_dir = tmp_path / "tracks"
        run_analysis(track, tracks_dir, skip_waveform=True)

        # Verify JSON file exists
        store = TrackStore(tracks_dir)
        fingerprints = store.list_all()
        assert len(fingerprints) == 1

        # Load and verify
        loaded = store.load(fingerprints[0])
        assert loaded is not None
        assert loaded.title == "Furst"
        assert loaded.bpm > 0

    @pytest.mark.slow
    def test_sqlite_cache(self, tmp_path: Path) -> None:
        """Analysis should be indexed in SQLite cache."""
        from scue.layer1.analysis import run_analysis
        from scue.layer1.storage import TrackCache

        track = _track_path("Furst.mp3")
        if not track.exists():
            pytest.skip(f"Track not found: {track.name}")

        cache_path = tmp_path / "cache" / "scue.db"
        run_analysis(
            track,
            tracks_dir=tmp_path / "tracks",
            cache_path=cache_path,
            skip_waveform=True,
        )

        cache = TrackCache(cache_path)
        assert cache.count_tracks() == 1
        tracks = cache.list_tracks()
        assert tracks[0]["title"] == "Furst"


@skip_no_audio
class TestSectionQuality:
    """Quality checks on section detection across reference tracks."""

    @pytest.mark.slow
    @pytest.mark.parametrize("track_name", REFERENCE_TRACKS)
    def test_reference_track_sections(self, track_name: str, tmp_path: Path) -> None:
        """Each reference track should produce valid sections."""
        from scue.layer1.analysis import run_analysis

        track = _track_path(track_name)
        if not track.exists():
            pytest.skip(f"Track not found: {track_name}")

        analysis = run_analysis(
            audio_path=track,
            tracks_dir=tmp_path / "tracks",
            skip_waveform=True,
        )

        # Must have sections
        assert len(analysis.sections) >= 2, f"{track_name}: too few sections"

        # Sections should be ordered and non-overlapping
        for i in range(len(analysis.sections) - 1):
            s1 = analysis.sections[i]
            s2 = analysis.sections[i + 1]
            assert s1.end <= s2.start + 0.01, \
                f"{track_name}: overlap at {s1.end} / {s2.start}"

        # All labels should be valid EDM labels
        valid_labels = {"intro", "verse", "build", "drop", "breakdown", "fakeout", "outro"}
        for s in analysis.sections:
            assert s.label in valid_labels, \
                f"{track_name}: invalid label '{s.label}'"

        # Confidence should be in range
        for s in analysis.sections:
            assert 0.0 <= s.confidence <= 1.0, \
                f"{track_name}: confidence {s.confidence} out of range"

        # First = intro, last = outro
        assert analysis.sections[0].label == "intro", \
            f"{track_name}: first section is '{analysis.sections[0].label}', expected 'intro'"
        assert analysis.sections[-1].label == "outro", \
            f"{track_name}: last section is '{analysis.sections[-1].label}', expected 'outro'"
