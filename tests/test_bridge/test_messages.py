"""Tests for bridge message parsing and serialization."""

import json
from pathlib import Path

import pytest

from scue.bridge.messages import (
    ALL_TYPES,
    BEAT,
    BEAT_GRID,
    BRIDGE_STATUS,
    CUE_POINTS,
    DEVICE_FOUND,
    DEVICE_LOST,
    PHRASE_ANALYSIS,
    PLAYER_STATUS,
    TRACK_METADATA,
    WAVEFORM_DETAIL,
    BeatGridPayload,
    BeatPayload,
    BridgeMessage,
    BridgeStatusPayload,
    CuePointsPayload,
    DevicePayload,
    PhraseAnalysisPayload,
    PlayerStatusPayload,
    TrackMetadataPayload,
    WaveformDetailPayload,
    message_to_json,
    parse_message,
    parse_typed_payload,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bridge"


# ── Fixture loading ──────────────────────────────────────────────────────

def load_fixture(name: str) -> list[dict]:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# ── parse_message basics ─────────────────────────────────────────────────

class TestParseMessage:
    def test_minimal_message(self):
        raw = '{"type": "beat", "timestamp": 1.0, "player_number": 1, "payload": {}}'
        msg = parse_message(raw)
        assert msg.type == "beat"
        assert msg.timestamp == 1.0
        assert msg.player_number == 1
        assert msg.payload == {}

    def test_null_player_number(self):
        raw = '{"type": "bridge_status", "timestamp": 1.0, "player_number": null, "payload": {}}'
        msg = parse_message(raw)
        assert msg.player_number is None

    def test_missing_timestamp_defaults_to_current_time(self):
        raw = '{"type": "beat", "player_number": 1, "payload": {}}'
        msg = parse_message(raw)
        assert msg.timestamp > 0

    def test_missing_payload_defaults_to_empty_dict(self):
        raw = '{"type": "beat", "timestamp": 1.0, "player_number": 1}'
        msg = parse_message(raw)
        assert msg.payload == {}

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_message("not json")

    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="type"):
            parse_message('{"timestamp": 1.0}')

    def test_non_object_json_raises(self):
        with pytest.raises(ValueError, match="Expected JSON object"):
            parse_message("[1, 2, 3]")


# ── Roundtrip serialization ──────────────────────────────────────────────

class TestRoundtrip:
    def test_roundtrip(self):
        original = BridgeMessage(
            type="player_status",
            timestamp=12345.678,
            player_number=2,
            payload={"bpm": 128.0, "pitch": 0.0},
        )
        json_str = message_to_json(original)
        restored = parse_message(json_str)
        assert restored.type == original.type
        assert restored.timestamp == original.timestamp
        assert restored.player_number == original.player_number
        assert restored.payload == original.payload


# ── Typed payload parsing ────────────────────────────────────────────────

class TestTypedPayloads:
    def test_device_found_payload(self):
        msg = BridgeMessage(
            type=DEVICE_FOUND,
            timestamp=1.0,
            player_number=1,
            payload={
                "device_name": "XDJ-AZ",
                "device_number": 1,
                "device_type": "cdj",
                "ip_address": "169.254.20.101",
            },
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, DevicePayload)
        assert p.device_name == "XDJ-AZ"
        assert p.device_type == "cdj"

    def test_bridge_status_payload(self):
        msg = BridgeMessage(
            type=BRIDGE_STATUS,
            timestamp=1.0,
            player_number=None,
            payload={"connected": True, "devices_online": 3, "version": "1.0.0"},
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, BridgeStatusPayload)
        assert p.connected is True
        assert p.devices_online == 3

    def test_player_status_payload(self):
        msg = BridgeMessage(
            type=PLAYER_STATUS,
            timestamp=1.0,
            player_number=1,
            payload={
                "bpm": 128.0,
                "pitch": 2.5,
                "beat_within_bar": 3,
                "beat_number": 42,
                "playback_state": "playing",
                "is_on_air": True,
            },
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, PlayerStatusPayload)
        assert p.bpm == 128.0
        assert p.pitch == 2.5
        assert p.playback_state == "playing"
        assert p.is_on_air is True

    def test_track_metadata_payload(self):
        msg = BridgeMessage(
            type=TRACK_METADATA,
            timestamp=1.0,
            player_number=1,
            payload={
                "title": "Strobe",
                "artist": "deadmau5",
                "bpm": 128.0,
                "duration": 637.0,
            },
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, TrackMetadataPayload)
        assert p.title == "Strobe"
        assert p.artist == "deadmau5"

    def test_beat_grid_payload(self):
        msg = BridgeMessage(
            type=BEAT_GRID,
            timestamp=1.0,
            player_number=1,
            payload={
                "beats": [
                    {"beat_number": 1, "time_ms": 250.0, "bpm": 128.0},
                    {"beat_number": 2, "time_ms": 718.75, "bpm": 128.0},
                ],
            },
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, BeatGridPayload)
        assert len(p.beats) == 2
        assert p.beats[0].beat_number == 1
        assert p.beats[1].time_ms == 718.75

    def test_phrase_analysis_payload(self):
        msg = BridgeMessage(
            type=PHRASE_ANALYSIS,
            timestamp=1.0,
            player_number=1,
            payload={
                "phrases": [
                    {"start_beat": 1, "end_beat": 128, "kind": "intro", "mood": 1},
                ],
            },
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, PhraseAnalysisPayload)
        assert len(p.phrases) == 1
        assert p.phrases[0].kind == "intro"

    def test_cue_points_payload(self):
        msg = BridgeMessage(
            type=CUE_POINTS,
            timestamp=1.0,
            player_number=1,
            payload={
                "cue_points": [{"time_ms": 250.0, "name": "", "color": ""}],
                "memory_points": [{"time_ms": 250.0, "name": "Start", "color": "#00FF00"}],
                "hot_cues": [{"slot": 1, "time_ms": 250.0, "name": "Start", "color": "#00FF00"}],
            },
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, CuePointsPayload)
        assert len(p.cue_points) == 1
        assert len(p.memory_points) == 1
        assert len(p.hot_cues) == 1
        assert p.hot_cues[0].slot == 1

    def test_beat_payload(self):
        msg = BridgeMessage(
            type=BEAT,
            timestamp=1.0,
            player_number=1,
            payload={"beat_within_bar": 1, "bpm": 128.0, "pitch": 0.0},
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, BeatPayload)
        assert p.beat_within_bar == 1

    def test_waveform_detail_payload(self):
        msg = BridgeMessage(
            type=WAVEFORM_DETAIL,
            timestamp=1.0,
            player_number=1,
            payload={"data": "AQIDBA==", "total_beats": 100},
        )
        p = parse_typed_payload(msg)
        assert isinstance(p, WaveformDetailPayload)
        assert p.data == "AQIDBA=="
        assert p.total_beats == 100

    def test_unknown_type_returns_none(self):
        msg = BridgeMessage(type="unknown_type", timestamp=1.0, player_number=None, payload={})
        assert parse_typed_payload(msg) is None

    def test_malformed_payload_returns_none(self):
        msg = BridgeMessage(
            type=PLAYER_STATUS,
            timestamp=1.0,
            player_number=1,
            payload={"wrong_field": True},
        )
        # Missing required fields → returns None
        assert parse_typed_payload(msg) is None


# ── Fixture file parsing ─────────────────────────────────────────────────

class TestFixtureParsing:
    """Ensure all fixture files parse cleanly."""

    @pytest.mark.parametrize("fixture_name", [
        "device_discovery.json",
        "playback_session.json",
        "track_metadata.json",
        "transition.json",
    ])
    def test_fixture_parses(self, fixture_name: str):
        messages = load_fixture(fixture_name)
        assert len(messages) > 0

        for raw in messages:
            msg = parse_message(json.dumps(raw))
            assert msg.type in ALL_TYPES or msg.type.startswith("_")
            assert isinstance(msg.timestamp, float)

    def test_device_discovery_fixture_types(self):
        messages = load_fixture("device_discovery.json")
        types = [m["type"] for m in messages]
        assert BRIDGE_STATUS in types
        assert DEVICE_FOUND in types

    def test_playback_session_has_beats(self):
        messages = load_fixture("playback_session.json")
        beat_msgs = [m for m in messages if m["type"] == BEAT]
        assert len(beat_msgs) >= 4  # at least one full bar

    def test_track_metadata_has_all_data_types(self):
        messages = load_fixture("track_metadata.json")
        types = {m["type"] for m in messages}
        assert TRACK_METADATA in types
        assert BEAT_GRID in types
        assert PHRASE_ANALYSIS in types
        assert CUE_POINTS in types

    def test_transition_has_two_players(self):
        messages = load_fixture("transition.json")
        players = {m["player_number"] for m in messages if m["player_number"] is not None}
        assert len(players) >= 2
