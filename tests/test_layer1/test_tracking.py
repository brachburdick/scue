"""Tests for scue.layer1.tracking — PlaybackTracker."""

import pytest

from scue.layer1.tracking import PlaybackTracker
from scue.layer1.models import (
    DeckState, TrackAnalysis, Section, TrackFeatures,
)
from scue.layer1 import db as _db


def _make_analysis(fp: str = "test_fp") -> TrackAnalysis:
    return TrackAnalysis(
        fingerprint=fp,
        audio_path="/fake.wav",
        bpm=128.0,
        beats=[i * 0.46875 for i in range(128)],
        downbeats=[i * 1.875 for i in range(32)],
        sections=[
            Section(label="intro", start=0.0, end=30.0, confidence=0.8, bar_count=16, expected_bar_count=16),
            Section(label="drop", start=30.0, end=60.0, confidence=0.9, bar_count=16, expected_bar_count=16),
        ],
        features=TrackFeatures(energy_curve=[0.3, 0.5, 0.8, 0.6]),
    )


def _make_deck(
    channel: int = 1,
    rekordbox_id: int = 42,
    is_master: bool = True,
    position_ms: float = 15000.0,
    bpm: float = 128.0,
) -> DeckState:
    return DeckState(
        channel=channel,
        is_playing=True,
        is_master=is_master,
        original_bpm=bpm,
        effective_bpm=bpm,
        beat_number=33,
        beat_within_bar=1,
        playback_position_ms=position_ms,
        player_number=channel,
        rekordbox_id=rekordbox_id,
    )


class TestPlaybackTracker:
    def test_returns_none_without_analysis(self, tmp_path):
        db_path = tmp_path / "test.db"
        tracker = PlaybackTracker(db_path=db_path)
        deck = _make_deck()
        cursor = tracker.on_deck_update(1, deck)
        assert cursor is None

    def test_returns_cursor_with_analysis(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        _db.store_analysis(analysis, db_path=db_path)
        _db.map_rekordbox_id(42, "test_fp", db_path=db_path)

        tracker = PlaybackTracker(db_path=db_path)
        deck = _make_deck(rekordbox_id=42)
        cursor = tracker.on_deck_update(1, deck)

        assert cursor is not None
        assert cursor.current_section.label == "intro"

    def test_non_master_returns_none(self, tmp_path):
        """ADR-005: only master deck produces cursor."""
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        _db.store_analysis(analysis, db_path=db_path)
        _db.map_rekordbox_id(42, "test_fp", db_path=db_path)

        tracker = PlaybackTracker(db_path=db_path)
        deck = _make_deck(is_master=False)
        cursor = tracker.on_deck_update(1, deck)
        assert cursor is None

    def test_track_change_reloads_analysis(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis(fp="fp_a")
        _db.store_analysis(analysis, db_path=db_path)
        _db.map_rekordbox_id(10, "fp_a", db_path=db_path)
        _db.map_rekordbox_id(20, "fp_a", db_path=db_path)

        tracker = PlaybackTracker(db_path=db_path)

        # Load track A
        deck_a = _make_deck(rekordbox_id=10)
        cursor = tracker.on_deck_update(1, deck_a)
        assert cursor is not None

        # Switch to track B (same fingerprint for simplicity)
        deck_b = _make_deck(rekordbox_id=20)
        cursor = tracker.on_deck_update(1, deck_b)
        assert cursor is not None

    def test_unknown_rekordbox_id(self, tmp_path):
        db_path = tmp_path / "test.db"
        tracker = PlaybackTracker(db_path=db_path)
        deck = _make_deck(rekordbox_id=999)
        cursor = tracker.on_deck_update(1, deck)
        assert cursor is None

    def test_enrichment_triggered_on_first_load(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        _db.store_analysis(analysis, db_path=db_path)
        _db.map_rekordbox_id(42, "test_fp", db_path=db_path)

        tracker = PlaybackTracker(db_path=db_path)
        deck = _make_deck(rekordbox_id=42, bpm=130.0)
        cursor = tracker.on_deck_update(1, deck)

        # Should have stored an enriched version
        enriched = _db.load_analysis("test_fp", version=2, db_path=db_path)
        assert enriched is not None
        assert enriched.bpm == 130.0

    def test_get_analysis(self, tmp_path):
        db_path = tmp_path / "test.db"
        analysis = _make_analysis()
        _db.store_analysis(analysis, db_path=db_path)
        _db.map_rekordbox_id(42, "test_fp", db_path=db_path)

        tracker = PlaybackTracker(db_path=db_path)
        deck = _make_deck(rekordbox_id=42)
        tracker.on_deck_update(1, deck)

        loaded = tracker.get_analysis(1)
        assert loaded is not None
