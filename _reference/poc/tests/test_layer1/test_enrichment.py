"""Tests for scue.layer1.enrichment — Pioneer enrichment pass."""

import pytest

from scue.layer1.enrichment import run_enrichment_pass
from scue.layer1.models import TrackAnalysis, Section, MusicalEvent, TrackFeatures
from scue.layer1 import db as _db


def _make_analysis(bpm: float = 128.0) -> TrackAnalysis:
    return TrackAnalysis(
        fingerprint="test_fp",
        audio_path="/fake.wav",
        bpm=bpm,
        beats=[i * (60.0 / bpm) for i in range(64)],
        downbeats=[i * 4 * (60.0 / bpm) for i in range(16)],
        sections=[
            Section(label="intro", start=0.0, end=30.0, confidence=0.8),
            Section(label="drop", start=30.0, end=60.0, confidence=0.9),
        ],
        events=[
            MusicalEvent(type="riser", timestamp=25.0, duration=5.0),
        ],
        features=TrackFeatures(
            energy_curve=[0.3, 0.5, 0.8],
            key="Am",
        ),
        version=1,
    )


class TestEnrichmentPass:
    def test_version_incremented(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        enriched = run_enrichment_pass(analysis, pioneer_bpm=128.0, db_path=db_path)
        assert enriched.version == 2

    def test_original_not_modified(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        original_bpm = analysis.bpm
        run_enrichment_pass(analysis, pioneer_bpm=130.0, db_path=db_path)
        assert analysis.bpm == original_bpm
        assert analysis.version == 1

    def test_bpm_swap(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis(bpm=128.0)
        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, db_path=db_path)
        assert enriched.bpm == 130.0
        assert enriched.beatgrid_source == "pioneer_enriched"

    def test_section_timestamps_scaled(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis(bpm=128.0)
        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, db_path=db_path)
        ratio = 130.0 / 128.0
        # Sections should be scaled by 1/ratio (faster BPM = shorter times)
        assert enriched.sections[0].end < analysis.sections[0].end

    def test_event_timestamps_scaled(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis(bpm=128.0)
        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, db_path=db_path)
        # Riser was at 25.0s — should be shorter at faster BPM
        assert enriched.events[0].timestamp < 25.0

    def test_key_swap(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        enriched = run_enrichment_pass(
            analysis, pioneer_bpm=128.0, pioneer_key="Cm", db_path=db_path,
        )
        assert enriched.features.key == "Cm"
        assert enriched.features.key_source == "pioneer_enriched"

    def test_no_change_when_bpm_matches(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis(bpm=128.0)
        enriched = run_enrichment_pass(analysis, pioneer_bpm=128.0, db_path=db_path)
        # Sections should stay the same
        assert enriched.sections[0].end == analysis.sections[0].end

    def test_pioneer_beatgrid_replaces(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        pioneer_grid = [i * 0.5 for i in range(100)]
        enriched = run_enrichment_pass(
            analysis, pioneer_bpm=128.0, pioneer_beatgrid=pioneer_grid, db_path=db_path,
        )
        assert enriched.beats == pioneer_grid

    def test_partial_enrichment_bpm_only(self, tmp_path):
        """When no beatgrid/key is available, only BPM is swapped."""
        db_path = tmp_path / "test.db"
        analysis = _make_analysis(bpm=128.0)
        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, db_path=db_path)
        assert enriched.bpm == 130.0
        # Beatgrid should be scaled, not replaced
        assert len(enriched.beats) == len(analysis.beats)
        assert enriched.beats[1] < analysis.beats[1]  # faster BPM = shorter intervals
