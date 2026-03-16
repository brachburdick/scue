"""Tests for scue.layer1.cursor — TrackCursor builder."""

import pytest

from scue.layer1.cursor import build_cursor, _find_section_index, _count_bars_in_section
from scue.layer1.models import (
    TrackAnalysis, Section, MusicalEvent, TrackFeatures, DeckState,
)


def _make_analysis() -> TrackAnalysis:
    """A simple 3-section analysis at 128 BPM."""
    return TrackAnalysis(
        fingerprint="test_fp",
        audio_path="/fake.wav",
        bpm=128.0,
        beats=[i * 0.46875 for i in range(256)],  # 128 BPM = 0.46875s per beat
        downbeats=[i * 1.875 for i in range(64)],  # every 4 beats
        sections=[
            Section(label="intro", start=0.0, end=30.0, confidence=0.8, bar_count=16, expected_bar_count=16),
            Section(label="build", start=30.0, end=60.0, confidence=0.9, bar_count=16, expected_bar_count=16),
            Section(label="drop", start=60.0, end=120.0, confidence=0.95, bar_count=32, expected_bar_count=32),
        ],
        events=[
            MusicalEvent(type="riser", timestamp=25.0, duration=5.0),
            MusicalEvent(type="impact", timestamp=60.0),
        ],
        features=TrackFeatures(energy_curve=[0.3, 0.4, 0.5, 0.7, 0.9, 0.95, 0.8, 0.6]),
    )


def _make_deck(position_ms: float = 15000.0, bpm: float = 128.0, is_master: bool = True) -> DeckState:
    return DeckState(
        channel=1,
        is_playing=True,
        is_master=is_master,
        original_bpm=bpm,
        effective_bpm=bpm,
        beat_number=33,
        beat_within_bar=1,
        playback_position_ms=position_ms,
        player_number=1,
    )


class TestFindSectionIndex:
    def test_finds_correct_section(self):
        sections = _make_analysis().sections
        assert _find_section_index(sections, 15.0) == 0  # intro
        assert _find_section_index(sections, 45.0) == 1  # build
        assert _find_section_index(sections, 90.0) == 2  # drop

    def test_boundary_belongs_to_current(self):
        sections = _make_analysis().sections
        assert _find_section_index(sections, 30.0) == 1  # start of build

    def test_past_end_returns_last(self):
        sections = _make_analysis().sections
        assert _find_section_index(sections, 200.0) == 2

    def test_empty_sections(self):
        assert _find_section_index([], 10.0) is None

    def test_before_first_section(self):
        sections = [Section(label="x", start=10.0, end=20.0)]
        assert _find_section_index(sections, 5.0) is None


class TestCountBars:
    def test_counts_downbeats(self):
        downbeats = [0.0, 1.875, 3.75, 5.625, 7.5, 9.375]
        assert _count_bars_in_section(downbeats, 0.0, 5.0) == 3  # at 0, 1.875, 3.75


class TestBuildCursor:
    def test_basic_cursor(self):
        analysis = _make_analysis()
        deck = _make_deck(position_ms=15000.0)  # 15s into intro
        cursor = build_cursor(analysis, deck)

        assert cursor is not None
        assert cursor.current_section.label == "intro"
        assert 0.0 < cursor.current_section.progress < 1.0
        assert cursor.next_section is not None
        assert cursor.next_section.label == "build"
        assert cursor.playback_state.is_playing is True
        assert cursor.beat_position.bpm == 128.0

    def test_cursor_in_last_section(self):
        analysis = _make_analysis()
        deck = _make_deck(position_ms=90000.0)  # 90s, in drop
        cursor = build_cursor(analysis, deck)

        assert cursor is not None
        assert cursor.current_section.label == "drop"
        assert cursor.next_section is None

    def test_cursor_returns_none_without_sections(self):
        analysis = _make_analysis()
        analysis.sections = []
        deck = _make_deck()
        assert build_cursor(analysis, deck) is None

    def test_upcoming_events(self):
        analysis = _make_analysis()
        deck = _make_deck(position_ms=20000.0)  # 20s — riser at 25s is ahead
        cursor = build_cursor(analysis, deck)

        assert cursor is not None
        assert len(cursor.upcoming_events) >= 1
        assert cursor.upcoming_events[0].type == "riser"

    def test_energy_interpolation(self):
        analysis = _make_analysis()
        deck = _make_deck(position_ms=60000.0)  # 60s, halfway through track
        cursor = build_cursor(analysis, deck)

        assert cursor is not None
        assert 0.0 <= cursor.current_features.energy <= 1.0

    def test_progress_at_section_start(self):
        analysis = _make_analysis()
        deck = _make_deck(position_ms=30000.0)  # exactly at build start
        cursor = build_cursor(analysis, deck)

        assert cursor is not None
        assert cursor.current_section.label == "build"
        assert cursor.current_section.progress == pytest.approx(0.0, abs=0.01)
