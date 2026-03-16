"""Tests for Layer 1B cursor (build_cursor)."""

from scue.bridge.adapter import PlayerState
from scue.layer1.cursor import (
    build_cursor,
    _find_section_index,
    _count_bars_in_section,
    _interpolate_energy,
    _section_to_info,
)
from scue.layer1.models import (
    Section, TrackAnalysis, TrackFeatures, MusicalEvent,
)


def _make_analysis(**overrides) -> TrackAnalysis:
    """Create a minimal TrackAnalysis for testing."""
    defaults = dict(
        fingerprint="abc123",
        audio_path="/test/track.mp3",
        bpm=128.0,
        beats=[i * 0.46875 for i in range(256)],  # 128 BPM = 0.46875s per beat
        downbeats=[i * 0.46875 * 4 for i in range(64)],
        sections=[
            Section(label="intro", start=0.0, end=30.0, bar_count=16, expected_bar_count=16, confidence=0.9),
            Section(label="build", start=30.0, end=60.0, bar_count=16, expected_bar_count=16, confidence=0.85),
            Section(label="drop", start=60.0, end=120.0, bar_count=32, expected_bar_count=32, confidence=0.95),
            Section(label="outro", start=120.0, end=150.0, bar_count=16, expected_bar_count=16, confidence=0.8),
        ],
        features=TrackFeatures(
            energy_curve=[0.2, 0.4, 0.6, 0.8, 1.0, 0.8, 0.6, 0.4, 0.2],
            mood="euphoric",
            danceability=0.8,
        ),
        duration=150.0,
    )
    defaults.update(overrides)
    return TrackAnalysis(**defaults)


def _make_player(**overrides) -> PlayerState:
    """Create a minimal PlayerState for testing."""
    defaults = dict(
        player_number=1,
        bpm=128.0,
        pitch=0.0,
        beat_within_bar=1,
        beat_number=1,
        playback_state="playing",
        is_on_air=True,
    )
    defaults.update(overrides)
    return PlayerState(**defaults)


class TestFindSectionIndex:
    def test_finds_first_section(self) -> None:
        analysis = _make_analysis()
        assert _find_section_index(analysis.sections, 15.0) == 0

    def test_finds_middle_section(self) -> None:
        analysis = _make_analysis()
        assert _find_section_index(analysis.sections, 45.0) == 1

    def test_finds_last_section(self) -> None:
        analysis = _make_analysis()
        assert _find_section_index(analysis.sections, 130.0) == 3

    def test_past_end_returns_last(self) -> None:
        analysis = _make_analysis()
        assert _find_section_index(analysis.sections, 200.0) == 3

    def test_before_start_returns_none(self) -> None:
        analysis = _make_analysis()
        assert _find_section_index(analysis.sections, -5.0) is None

    def test_exact_boundary(self) -> None:
        analysis = _make_analysis()
        # At exactly 30.0, should be in "build" (start <= pos < end)
        assert _find_section_index(analysis.sections, 30.0) == 1


class TestSectionToInfo:
    def test_progress_at_start(self) -> None:
        sec = Section(label="drop", start=60.0, end=120.0, bar_count=32, expected_bar_count=32, confidence=0.9)
        info = _section_to_info(sec, 60.0)
        assert info.progress == 0.0
        assert info.label == "drop"

    def test_progress_at_midpoint(self) -> None:
        sec = Section(label="drop", start=60.0, end=120.0, bar_count=32, expected_bar_count=32, confidence=0.9)
        info = _section_to_info(sec, 90.0)
        assert abs(info.progress - 0.5) < 0.001

    def test_progress_clamped_to_one(self) -> None:
        sec = Section(label="drop", start=60.0, end=120.0, bar_count=32, expected_bar_count=32, confidence=0.9)
        info = _section_to_info(sec, 130.0)
        assert info.progress == 1.0


class TestCountBarsInSection:
    def test_counts_downbeats(self) -> None:
        downbeats = [0.0, 1.875, 3.75, 5.625, 7.5, 9.375]
        count = _count_bars_in_section(downbeats, 0.0, 5.0)
        # Downbeats at 0.0, 1.875, 3.75 are <= 5.0
        assert count == 3

    def test_empty_downbeats(self) -> None:
        assert _count_bars_in_section([], 0.0, 5.0) == 0


class TestInterpolateEnergy:
    def test_at_start(self) -> None:
        curve = [0.0, 0.5, 1.0]
        assert _interpolate_energy(curve, 0.0, 10.0) == 0.0

    def test_at_end(self) -> None:
        curve = [0.0, 0.5, 1.0]
        assert _interpolate_energy(curve, 10.0, 10.0) == 1.0

    def test_midpoint(self) -> None:
        curve = [0.0, 1.0]
        result = _interpolate_energy(curve, 5.0, 10.0)
        assert abs(result - 0.5) < 0.001

    def test_empty_curve(self) -> None:
        assert _interpolate_energy([], 5.0, 10.0) == 0.5

    def test_zero_duration(self) -> None:
        assert _interpolate_energy([0.5], 0.0, 0.0) == 0.5


class TestBuildCursor:
    def test_basic_cursor(self) -> None:
        analysis = _make_analysis()
        player = _make_player()
        cursor = build_cursor(analysis, player, position_ms=15000.0)
        assert cursor is not None
        assert cursor.current_section.label == "intro"
        assert cursor.next_section is not None
        assert cursor.next_section.label == "build"
        assert cursor.beat_position.bpm == 128.0
        assert cursor.playback_state.is_playing is True

    def test_last_section_no_next(self) -> None:
        analysis = _make_analysis()
        player = _make_player()
        cursor = build_cursor(analysis, player, position_ms=130000.0)
        assert cursor is not None
        assert cursor.current_section.label == "outro"
        assert cursor.next_section is None

    def test_no_sections_returns_none(self) -> None:
        analysis = _make_analysis(sections=[])
        player = _make_player()
        assert build_cursor(analysis, player, position_ms=5000.0) is None

    def test_uses_player_bpm(self) -> None:
        analysis = _make_analysis()
        player = _make_player(bpm=130.0)
        cursor = build_cursor(analysis, player, position_ms=15000.0)
        assert cursor is not None
        assert cursor.beat_position.bpm == 130.0
        assert cursor.beat_position.original_bpm == 128.0

    def test_zero_bpm_falls_back(self) -> None:
        analysis = _make_analysis()
        player = _make_player(bpm=0.0)
        cursor = build_cursor(analysis, player, position_ms=15000.0)
        assert cursor is not None
        assert cursor.beat_position.bpm == 128.0

    def test_section_progress(self) -> None:
        analysis = _make_analysis()
        player = _make_player()
        cursor = build_cursor(analysis, player, position_ms=15000.0)
        assert cursor is not None
        # 15s into a 0-30s section = 50%
        assert abs(cursor.current_section.progress - 0.5) < 0.01

    def test_energy_interpolation(self) -> None:
        analysis = _make_analysis()
        player = _make_player()
        cursor = build_cursor(analysis, player, position_ms=75000.0)
        assert cursor is not None
        # At position 75s / 150s = 50%, energy curve midpoint
        assert cursor.current_features.energy > 0.0
        assert cursor.current_features.mood == "euphoric"

    def test_playback_state(self) -> None:
        analysis = _make_analysis()
        player = _make_player(playback_state="paused", is_on_air=False, pitch=2.5)
        cursor = build_cursor(analysis, player, position_ms=15000.0)
        assert cursor is not None
        assert cursor.playback_state.is_playing is False
        assert cursor.playback_state.is_on_air is False
        assert cursor.playback_state.pitch_percent == 2.5

    def test_upcoming_events(self) -> None:
        events = [
            MusicalEvent(type="kick", timestamp=10.0),
            MusicalEvent(type="snare", timestamp=20.0),
            MusicalEvent(type="riser", timestamp=50.0),
        ]
        analysis = _make_analysis(events=events)
        player = _make_player()
        cursor = build_cursor(analysis, player, position_ms=15000.0)
        assert cursor is not None
        # Position is 15s, so events at 20s and 50s are upcoming
        assert len(cursor.upcoming_events) == 2
        assert cursor.upcoming_events[0].type == "snare"

    def test_default_position_is_zero(self) -> None:
        analysis = _make_analysis()
        player = _make_player()
        cursor = build_cursor(analysis, player)
        assert cursor is not None
        assert cursor.playback_state.playback_position_ms == 0.0
