"""Tests for the track scanner orchestrator."""

import asyncio
import time

import pytest

from scue.layer1.scanner import (
    CapturedTrackData,
    DeckCaptureSlot,
    ScanProgress,
    ScanStatus,
    TrackEntry,
    TrackScanner,
)


class TestScanProgress:
    """Test ScanProgress data model."""

    def test_initial_state(self):
        p = ScanProgress()
        assert p.status == ScanStatus.IDLE
        assert p.total == 0
        assert p.scanned == 0
        assert p.skipped == 0
        assert p.errors == 0

    def test_to_dict(self):
        p = ScanProgress(
            status=ScanStatus.SCANNING,
            total=100,
            scanned=42,
            skipped=5,
            errors=1,
            current_track="Test Track — Test Artist",
            started_at=time.time() - 60,
        )
        d = p.to_dict()
        assert d["status"] == "scanning"
        assert d["total"] == 100
        assert d["scanned"] == 42
        assert d["skipped"] == 5
        assert d["errors"] == 1
        assert d["current_track"] == "Test Track — Test Artist"
        assert d["duration_s"] > 0

    def test_error_messages_limited_to_10(self):
        p = ScanProgress()
        p.error_messages = [f"error {i}" for i in range(20)]
        d = p.to_dict()
        assert len(d["error_messages"]) == 10
        assert d["error_messages"][0] == "error 10"  # last 10

    def test_to_dict_includes_deck_progress(self):
        p = ScanProgress(
            deck_progress={1: {"scanned": 5, "errors": 0}, 2: {"scanned": 3, "errors": 1}},
        )
        d = p.to_dict()
        assert d["deck_progress"] == {1: {"scanned": 5, "errors": 0}, 2: {"scanned": 3, "errors": 1}}


class TestTrackEntry:
    """Test TrackEntry data model."""

    def test_basic_creation(self):
        t = TrackEntry(rekordbox_id=42001, title="Test", artist="DJ Test")
        assert t.rekordbox_id == 42001
        assert t.title == "Test"


class TestCapturedTrackData:
    """Test CapturedTrackData data model."""

    def test_basic_creation(self):
        c = CapturedTrackData(rekordbox_id=42001)
        assert c.rekordbox_id == 42001
        assert c.beat_grid == []
        assert c.phrases == []
        assert c.cue_points == []
        assert c.source_player == 0

    def test_source_player_field(self):
        c = CapturedTrackData(rekordbox_id=42001, source_player=2)
        assert c.source_player == 2


class TestDeckCaptureSlot:
    """Test DeckCaptureSlot data model."""

    def test_initial_state(self):
        slot = DeckCaptureSlot(player_number=1)
        assert slot.capture is None
        assert slot.received_metadata is False
        assert slot.has_essential_data is False

    def test_reset(self):
        slot = DeckCaptureSlot(player_number=2)
        slot.reset(rekordbox_id=42001, title="Test", artist="DJ")
        assert slot.capture is not None
        assert slot.capture.rekordbox_id == 42001
        assert slot.capture.source_player == 2
        assert slot.received_metadata is False

    def test_has_essential_data(self):
        slot = DeckCaptureSlot(player_number=1)
        slot.reset(42001)
        assert slot.has_essential_data is False

        slot.received_metadata = True
        assert slot.has_essential_data is False  # still need beatgrid or phrases

        slot.received_phrases = True
        assert slot.has_essential_data is True

    def test_has_essential_data_with_beatgrid(self):
        slot = DeckCaptureSlot(player_number=1)
        slot.reset(42001)
        slot.received_metadata = True
        slot.received_beatgrid = True
        assert slot.has_essential_data is True

    def test_reset_clears_flags(self):
        slot = DeckCaptureSlot(player_number=1)
        slot.reset(42001)
        slot.received_metadata = True
        slot.received_beatgrid = True
        slot.received_phrases = True
        slot.received_cues = True
        slot.received_waveform = True

        slot.reset(42002)
        assert slot.received_metadata is False
        assert slot.received_beatgrid is False
        assert slot.received_phrases is False
        assert slot.received_cues is False
        assert slot.received_waveform is False
        assert slot.capture.rekordbox_id == 42002


class TestScannerDataCallbacks:
    """Test the scanner's data capture callbacks with multi-deck routing."""

    def _make_scanner(self):
        """Create a scanner with a mock WebSocket and cache."""

        class MockWs:
            connected = True
            async def send_command(self, cmd, timeout=10.0):
                from scue.bridge.commands import CommandResponse
                return CommandResponse(request_id="test", status="ok", command="test", data={})

        class MockCache:
            def has_pioneer_scan_data(self, player, slot, rbid):
                return False

        return TrackScanner(ws_client=MockWs(), cache=MockCache())

    def _setup_slot(self, scanner, player: int, rbid: int):
        """Set up a capture slot for a player with a specific rekordbox_id."""
        slot = DeckCaptureSlot(player_number=player)
        slot.reset(rbid)
        scanner._slots[player] = slot
        return slot

    def test_on_track_metadata_captures_data(self):
        scanner = self._make_scanner()
        slot = self._setup_slot(scanner, player=1, rbid=42001)

        scanner.on_track_metadata(1, {
            "rekordbox_id": 42001,
            "title": "Test Track",
            "artist": "DJ Test",
            "bpm": 128.0,
            "key": "Am",
            "duration": 300.0,
        })

        assert slot.capture.title == "Test Track"
        assert slot.capture.artist == "DJ Test"
        assert slot.capture.bpm == 128.0
        assert slot.received_metadata is True

    def test_on_track_metadata_ignores_wrong_rbid(self):
        scanner = self._make_scanner()
        slot = self._setup_slot(scanner, player=1, rbid=42001)

        scanner.on_track_metadata(1, {
            "rekordbox_id": 99999,  # wrong ID
            "title": "Wrong Track",
        })

        assert slot.capture.title == ""  # unchanged
        assert slot.received_metadata is False

    def test_on_beat_grid_captures_data(self):
        scanner = self._make_scanner()
        slot = self._setup_slot(scanner, player=1, rbid=42001)

        beats = [
            {"beat_number": 1, "time_ms": 0, "bpm": 128.0},
            {"beat_number": 2, "time_ms": 468.75, "bpm": 128.0},
        ]
        scanner.on_beat_grid(1, {"beats": beats})

        assert len(slot.capture.beat_grid) == 2
        assert slot.received_beatgrid is True

    def test_on_phrase_analysis_captures_data(self):
        scanner = self._make_scanner()
        slot = self._setup_slot(scanner, player=1, rbid=42001)

        phrases = [
            {"start_beat": 1, "end_beat": 65, "kind": "intro", "mood": 1},
            {"start_beat": 65, "end_beat": 193, "kind": "chorus_1", "mood": 1},
        ]
        scanner.on_phrase_analysis(1, {"phrases": phrases})

        assert len(slot.capture.phrases) == 2
        assert slot.received_phrases is True

    def test_on_cue_points_captures_data(self):
        scanner = self._make_scanner()
        slot = self._setup_slot(scanner, player=1, rbid=42001)

        scanner.on_cue_points(1, {
            "cue_points": [],
            "memory_points": [{"time_ms": 1000, "name": "Drop", "color": ""}],
            "hot_cues": [{"slot": 1, "time_ms": 500, "name": "A", "color": "#FF0000"}],
        })

        assert len(slot.capture.memory_points) == 1
        assert len(slot.capture.hot_cues) == 1
        assert slot.received_cues is True

    def test_on_track_waveform_captures_data(self):
        scanner = self._make_scanner()
        slot = self._setup_slot(scanner, player=1, rbid=42001)

        scanner.on_track_waveform(1, {
            "data": "AQIDBA==",
            "frame_count": 1,
            "total_time_ms": 1000,
            "is_color": True,
        })

        assert slot.capture.waveform_data == "AQIDBA=="
        assert slot.capture.waveform_frame_count == 1
        assert slot.received_waveform is True

    def test_callbacks_noop_when_no_slots(self):
        scanner = self._make_scanner()
        # No slots set up — should not raise
        scanner.on_track_metadata(1, {"rekordbox_id": 1, "title": "X"})
        scanner.on_beat_grid(1, {"beats": []})
        scanner.on_phrase_analysis(1, {"phrases": []})
        scanner.on_cue_points(1, {"cue_points": [], "memory_points": [], "hot_cues": []})
        scanner.on_track_waveform(1, {"data": "", "frame_count": 0, "total_time_ms": 0})

    # ── Multi-deck routing tests ─────────────────────────────────────

    def test_multi_deck_callbacks_route_by_player(self):
        """Data for player 1 goes to slot 1, data for player 2 goes to slot 2."""
        scanner = self._make_scanner()
        slot1 = self._setup_slot(scanner, player=1, rbid=42001)
        slot2 = self._setup_slot(scanner, player=2, rbid=42002)

        scanner.on_track_metadata(1, {
            "rekordbox_id": 42001,
            "title": "Track A",
            "artist": "Artist A",
        })
        scanner.on_track_metadata(2, {
            "rekordbox_id": 42002,
            "title": "Track B",
            "artist": "Artist B",
        })

        assert slot1.capture.title == "Track A"
        assert slot2.capture.title == "Track B"
        assert slot1.received_metadata is True
        assert slot2.received_metadata is True

    def test_multi_deck_ignores_unknown_player(self):
        """Data for a player not in slots is silently dropped."""
        scanner = self._make_scanner()
        slot1 = self._setup_slot(scanner, player=1, rbid=42001)

        # Player 3 is not in slots
        scanner.on_beat_grid(3, {"beats": [{"beat_number": 1, "time_ms": 0, "bpm": 128.0}]})

        # Slot 1 should be unaffected
        assert slot1.capture.beat_grid == []
        assert slot1.received_beatgrid is False

    def test_multi_deck_independent_data_accumulation(self):
        """Each deck accumulates data independently."""
        scanner = self._make_scanner()
        slot1 = self._setup_slot(scanner, player=1, rbid=42001)
        slot2 = self._setup_slot(scanner, player=2, rbid=42002)

        # Send beatgrid to deck 1 only
        scanner.on_beat_grid(1, {"beats": [{"beat_number": 1, "time_ms": 0, "bpm": 128.0}]})
        # Send phrases to deck 2 only
        scanner.on_phrase_analysis(2, {"phrases": [{"start_beat": 1, "end_beat": 65, "kind": "intro", "mood": 1}]})

        assert slot1.received_beatgrid is True
        assert slot1.received_phrases is False
        assert slot2.received_beatgrid is False
        assert slot2.received_phrases is True

    def test_metadata_rbid_check_per_deck(self):
        """Metadata with wrong rekordbox_id is rejected even when player matches."""
        scanner = self._make_scanner()
        slot1 = self._setup_slot(scanner, player=1, rbid=42001)

        scanner.on_track_metadata(1, {
            "rekordbox_id": 99999,  # wrong for this slot
            "title": "Wrong Track",
        })

        assert slot1.capture.title == ""
        assert slot1.received_metadata is False
