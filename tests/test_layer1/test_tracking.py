"""Tests for Layer 1B PlaybackTracker."""

import time
from pathlib import Path

from scue.bridge.adapter import PlayerState
from scue.layer1.models import Section, TrackAnalysis, TrackFeatures
from scue.layer1.storage import TrackCache, TrackStore
from scue.layer1.tracking import PlaybackTracker


def _make_analysis(fp: str = "abc123def456", bpm: float = 128.0, **overrides) -> TrackAnalysis:
    defaults = dict(
        fingerprint=fp,
        audio_path="/test/track.mp3",
        bpm=bpm,
        beats=[i * 0.46875 for i in range(256)],
        downbeats=[i * 0.46875 * 4 for i in range(64)],
        sections=[
            Section(label="intro", start=0.0, end=30.0, bar_count=16, expected_bar_count=16, confidence=0.9),
            Section(label="drop", start=30.0, end=90.0, bar_count=32, expected_bar_count=32, confidence=0.95),
            Section(label="outro", start=90.0, end=120.0, bar_count=16, expected_bar_count=16, confidence=0.8),
        ],
        features=TrackFeatures(
            energy_curve=[0.3, 0.5, 0.7, 0.9, 0.5],
            mood="euphoric",
            danceability=0.8,
        ),
        duration=120.0,
    )
    defaults.update(overrides)
    return TrackAnalysis(**defaults)


def _make_player(
    player_number: int = 1,
    rekordbox_id: int = 42001,
    bpm: float = 128.0,
    is_on_air: bool = True,
    track_source_player: int = 0,
    track_source_slot: str = "",
    **overrides,
) -> PlayerState:
    defaults = dict(
        player_number=player_number,
        bpm=bpm,
        pitch=0.0,
        beat_within_bar=1,
        beat_number=1,
        playback_state="playing",
        is_on_air=is_on_air,
        rekordbox_id=rekordbox_id,
        track_source_player=track_source_player,
        track_source_slot=track_source_slot,
    )
    defaults.update(overrides)
    return PlayerState(**defaults)


def _setup(tmp_path: Path, analyses: list[TrackAnalysis] | None = None) -> tuple[PlaybackTracker, TrackStore, TrackCache]:
    store = TrackStore(tmp_path / "tracks")
    cache = TrackCache(tmp_path / "cache.db")
    if analyses is None:
        analyses = [_make_analysis()]
    for a in analyses:
        store.save(a)
        cache.index_analysis(a)
        if a.rekordbox_id:
            cache.link_rekordbox_id(a.rekordbox_id, a.fingerprint)
    tracker = PlaybackTracker(store, cache)
    return tracker, store, cache


class TestPlaybackTracker:
    def test_no_cursor_when_off_air(self, tmp_path: Path) -> None:
        analysis = _make_analysis(rekordbox_id=42001)
        tracker, store, cache = _setup(tmp_path, [analysis])
        cache.link_rekordbox_id(42001, analysis.fingerprint)

        player = _make_player(is_on_air=False, rekordbox_id=42001)
        cursor = tracker.on_player_update(player)
        assert cursor is None

    def test_cursor_when_on_air(self, tmp_path: Path) -> None:
        analysis = _make_analysis(rekordbox_id=42001)
        tracker, store, cache = _setup(tmp_path, [analysis])
        cache.link_rekordbox_id(42001, analysis.fingerprint)

        player = _make_player(is_on_air=True, rekordbox_id=42001)
        tracker.update_position(1, 15000.0)
        cursor = tracker.on_player_update(player)
        assert cursor is not None
        assert cursor.current_section.label == "intro"

    def test_no_cursor_without_analysis(self, tmp_path: Path) -> None:
        store = TrackStore(tmp_path / "tracks")
        cache = TrackCache(tmp_path / "cache.db")
        tracker = PlaybackTracker(store, cache)

        player = _make_player(rekordbox_id=99999)
        cursor = tracker.on_player_update(player)
        assert cursor is None

    def test_track_change_reloads(self, tmp_path: Path) -> None:
        a1 = _make_analysis(fp="fp1", rekordbox_id=1001)
        a2 = _make_analysis(fp="fp2", rekordbox_id=1002, bpm=130.0)
        tracker, store, cache = _setup(tmp_path, [a1, a2])
        cache.link_rekordbox_id(1001, "fp1")
        cache.link_rekordbox_id(1002, "fp2")

        # Load first track
        p1 = _make_player(rekordbox_id=1001)
        tracker.update_position(1, 15000.0)
        tracker.on_player_update(p1)
        assert tracker.get_analysis(1) is not None
        assert tracker.get_analysis(1).fingerprint == "fp1"

        # Load second track
        p2 = _make_player(rekordbox_id=1002)
        tracker.on_player_update(p2)
        assert tracker.get_analysis(1) is not None
        assert tracker.get_analysis(1).fingerprint == "fp2"

    def test_enrichment_on_first_load(self, tmp_path: Path) -> None:
        analysis = _make_analysis(rekordbox_id=42001)
        tracker, store, cache = _setup(tmp_path, [analysis])
        cache.link_rekordbox_id(42001, analysis.fingerprint)

        player = _make_player(rekordbox_id=42001, bpm=130.0)
        tracker.update_position(1, 15000.0)
        cursor = tracker.on_player_update(player)

        # Should have enriched — analysis version bumped
        loaded_analysis = tracker.get_analysis(1)
        assert loaded_analysis is not None
        assert loaded_analysis.version == 2
        assert loaded_analysis.source == "pioneer_enriched"
        assert loaded_analysis.bpm == 130.0

    def test_enrichment_only_once(self, tmp_path: Path) -> None:
        analysis = _make_analysis(rekordbox_id=42001)
        tracker, store, cache = _setup(tmp_path, [analysis])
        cache.link_rekordbox_id(42001, analysis.fingerprint)

        player = _make_player(rekordbox_id=42001, bpm=130.0)
        tracker.on_player_update(player)

        # Simulate unload and reload
        tracker._player_track[1] = 0
        tracker._player_analysis[1] = None
        tracker.on_player_update(player)

        # Version should still be 2 (not 3), since enrichment is per-fingerprint
        loaded = tracker.get_analysis(1)
        assert loaded is not None
        # It reloads the latest version from store (which is v2 from first enrichment)
        assert loaded.version == 2

    def test_unload_track(self, tmp_path: Path) -> None:
        analysis = _make_analysis(rekordbox_id=42001)
        tracker, store, cache = _setup(tmp_path, [analysis])
        cache.link_rekordbox_id(42001, analysis.fingerprint)

        # Load
        player = _make_player(rekordbox_id=42001)
        tracker.on_player_update(player)
        assert tracker.get_analysis(1) is not None

        # Unload (rekordbox_id=0)
        player_empty = _make_player(rekordbox_id=0)
        tracker.on_player_update(player_empty)
        assert tracker.get_analysis(1) is None

    def test_update_position(self, tmp_path: Path) -> None:
        analysis = _make_analysis(rekordbox_id=42001)
        tracker, store, cache = _setup(tmp_path, [analysis])
        cache.link_rekordbox_id(42001, analysis.fingerprint)

        player = _make_player(rekordbox_id=42001)
        tracker.update_position(1, 45000.0)
        cursor = tracker.on_player_update(player)

        assert cursor is not None
        assert cursor.current_section.label == "drop"
        assert cursor.playback_state.playback_position_ms == 45000.0

    def test_multi_player(self, tmp_path: Path) -> None:
        a1 = _make_analysis(fp="fp1", rekordbox_id=1001)
        a2 = _make_analysis(fp="fp2", rekordbox_id=1002)
        tracker, store, cache = _setup(tmp_path, [a1, a2])
        cache.link_rekordbox_id(1001, "fp1")
        cache.link_rekordbox_id(1002, "fp2")

        # Player 1 on-air, reading from player 1's USB
        p1 = _make_player(player_number=1, rekordbox_id=1001, is_on_air=True,
                           track_source_player=1, track_source_slot="usb")
        tracker.update_position(1, 15000.0)
        c1 = tracker.on_player_update(p1)
        assert c1 is not None

        # Player 2 not on-air, also reading from player 1's USB
        p2 = _make_player(player_number=2, rekordbox_id=1002, is_on_air=False,
                           track_source_player=1, track_source_slot="usb")
        c2 = tracker.on_player_update(p2)
        assert c2 is None

        # Player 2 goes on-air
        p2_on = _make_player(player_number=2, rekordbox_id=1002, is_on_air=True,
                              track_source_player=1, track_source_slot="usb")
        tracker.update_position(2, 50000.0)
        c2 = tracker.on_player_update(p2_on)
        assert c2 is not None

    def test_dlp_namespace_fallback(self, tmp_path: Path) -> None:
        """Tracker falls back to DLP namespace when direct player lookup fails (ADR-015)."""
        analysis = _make_analysis(rekordbox_id=0)
        store = TrackStore(tmp_path / "tracks")
        cache = TrackCache(tmp_path / "cache.db")
        store.save(analysis)
        cache.index_analysis(analysis)
        # Link under DLP namespace (as USB scanner does)
        cache.link_rekordbox_id(5001, analysis.fingerprint, source_player="dlp", source_slot="usb")

        tracker = PlaybackTracker(store, cache)

        # Bridge reports player 1 with rekordbox_id=5001, no track_source_player set
        player = _make_player(player_number=1, rekordbox_id=5001, is_on_air=True)
        tracker.update_position(1, 15000.0)
        cursor = tracker.on_player_update(player)

        # Should resolve via DLP fallback
        assert cursor is not None
        assert tracker.get_analysis(1) is not None
        assert tracker.get_analysis(1).fingerprint == analysis.fingerprint

    def test_composite_key_with_source_fields(self, tmp_path: Path) -> None:
        """Tracker uses track_source_player/slot from PlayerState for lookup (ADR-015)."""
        analysis = _make_analysis(rekordbox_id=0)
        store = TrackStore(tmp_path / "tracks")
        cache = TrackCache(tmp_path / "cache.db")
        store.save(analysis)
        cache.index_analysis(analysis)
        # Link under player 2 / sd namespace
        cache.link_rekordbox_id(7001, analysis.fingerprint, source_player="2", source_slot="sd")

        tracker = PlaybackTracker(store, cache)

        # Player 1 playing a track from player 2's SD slot
        player = _make_player(
            player_number=1, rekordbox_id=7001, is_on_air=True,
            track_source_player=2, track_source_slot="sd",
        )
        tracker.update_position(1, 15000.0)
        cursor = tracker.on_player_update(player)

        assert cursor is not None
        assert tracker.get_analysis(1).fingerprint == analysis.fingerprint

    def test_multi_usb_different_tracks_same_id(self, tmp_path: Path) -> None:
        """Two USBs with same rekordbox_id resolve to different tracks (ADR-015)."""
        a1 = _make_analysis(fp="fp_usb1", rekordbox_id=0, bpm=128.0)
        a2 = _make_analysis(fp="fp_usb2", rekordbox_id=0, bpm=140.0)
        store = TrackStore(tmp_path / "tracks")
        cache = TrackCache(tmp_path / "cache.db")
        for a in [a1, a2]:
            store.save(a)
            cache.index_analysis(a)

        # Same rekordbox_id=1, different source players (USB in player 1 vs player 2)
        cache.link_rekordbox_id(1, "fp_usb1", source_player="1", source_slot="usb")
        cache.link_rekordbox_id(1, "fp_usb2", source_player="2", source_slot="usb")

        tracker = PlaybackTracker(store, cache)

        # Player 1 playing from its own USB
        p1 = _make_player(
            player_number=1, rekordbox_id=1, is_on_air=True,
            track_source_player=1, track_source_slot="usb",
        )
        tracker.update_position(1, 15000.0)
        c1 = tracker.on_player_update(p1)
        assert c1 is not None
        assert tracker.get_analysis(1).fingerprint == "fp_usb1"

        # Player 2 playing from its own USB — same rekordbox_id, different track
        p2 = _make_player(
            player_number=2, rekordbox_id=1, is_on_air=True,
            track_source_player=2, track_source_slot="usb",
        )
        tracker.update_position(2, 15000.0)
        c2 = tracker.on_player_update(p2)
        assert c2 is not None
        assert tracker.get_analysis(2).fingerprint == "fp_usb2"
