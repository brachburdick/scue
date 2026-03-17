"""Tests for bridge adapter — stateful BridgeMessage → PlayerState normalization."""

import json
from pathlib import Path

import pytest

from scue.bridge.adapter import BridgeAdapter, DeviceInfo, PlayerState
from scue.bridge.messages import (
    BEAT,
    BEAT_GRID,
    BRIDGE_STATUS,
    CUE_POINTS,
    DEVICE_FOUND,
    DEVICE_LOST,
    PHRASE_ANALYSIS,
    PLAYER_STATUS,
    TRACK_METADATA,
    BridgeMessage,
    parse_message,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bridge"


def load_fixture(name: str) -> list[BridgeMessage]:
    with open(FIXTURES_DIR / name) as f:
        raw_list = json.load(f)
    return [parse_message(json.dumps(m)) for m in raw_list]


class TestDeviceDiscovery:
    def test_devices_populated(self):
        adapter = BridgeAdapter()
        messages = load_fixture("device_discovery.json")

        for msg in messages:
            adapter.handle_message(msg)

        assert len(adapter.devices) == 3
        ips = {d.ip_address for d in adapter.devices.values()}
        assert "169.254.20.101" in ips
        assert "169.254.20.102" in ips
        assert "169.254.20.100" in ips

    def test_device_found_callback(self):
        adapter = BridgeAdapter()
        found = []
        adapter.on_device_change = lambda device, action: found.append((device.device_name, action))

        messages = load_fixture("device_discovery.json")
        for msg in messages:
            adapter.handle_message(msg)

        device_names = [name for name, action in found if action == "found"]
        assert "XDJ-AZ" in device_names
        assert "DJM-900NXS2" in device_names

    def test_device_lost_removes_from_state(self):
        adapter = BridgeAdapter()
        messages = load_fixture("transition.json")
        for msg in messages:
            adapter.handle_message(msg)

        # transition.json ends with device_lost for player 1
        lost_ips = {d.ip_address for d in adapter.devices.values()}
        assert "169.254.20.101" not in lost_ips

    def test_device_lost_callback(self):
        adapter = BridgeAdapter()
        events = []
        adapter.on_device_change = lambda device, action: events.append((device, action))

        messages = load_fixture("transition.json")
        for msg in messages:
            adapter.handle_message(msg)

        lost_events = [(d.device_name, a) for d, a in events if a == "lost"]
        assert len(lost_events) >= 1
        assert lost_events[0][0] == "XDJ-AZ"


class TestBridgeStatus:
    def test_bridge_status_updates(self):
        adapter = BridgeAdapter()
        messages = load_fixture("device_discovery.json")

        for msg in messages:
            adapter.handle_message(msg)

        assert adapter.bridge_connected is True
        assert adapter.bridge_version == "1.2.0"


class TestPlayerStatus:
    def test_player_state_from_session(self):
        adapter = BridgeAdapter()
        messages = load_fixture("playback_session.json")

        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        assert player.bpm == 128.0
        assert player.pitch == 2.5  # last status has pitch 2.5
        assert player.playback_state == "playing"
        assert player.is_on_air is True

    def test_player_update_callback(self):
        adapter = BridgeAdapter()
        updates = []
        adapter.on_player_update = lambda p: updates.append(p.playback_state)

        messages = load_fixture("playback_session.json")
        for msg in messages:
            adapter.handle_message(msg)

        assert "cued" in updates
        assert "playing" in updates


class TestTrackMetadata:
    def test_metadata_populated(self):
        adapter = BridgeAdapter()
        messages = load_fixture("track_metadata.json")

        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        assert player.title == "Strobe"
        assert player.artist == "deadmau5"
        assert player.key == "Fm"
        assert player.duration == 637.0

    def test_track_loaded_callback(self):
        adapter = BridgeAdapter()
        loaded = []
        adapter.on_track_loaded = lambda pn, title, artist: loaded.append((pn, title, artist))

        messages = load_fixture("track_metadata.json")
        for msg in messages:
            adapter.handle_message(msg)

        assert len(loaded) == 1
        assert loaded[0] == (1, "Strobe", "deadmau5")

    def test_beat_grid_populated(self):
        adapter = BridgeAdapter()
        messages = load_fixture("track_metadata.json")

        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        assert len(player.beat_grid) == 8
        assert player.beat_grid[0]["beat_number"] == 1
        assert player.beat_grid[0]["time_ms"] == 250.0

    def test_phrase_analysis_populated(self):
        adapter = BridgeAdapter()
        messages = load_fixture("track_metadata.json")

        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        assert len(player.phrases) == 6
        assert player.phrases[0]["kind"] == "intro"

    def test_cue_points_populated(self):
        adapter = BridgeAdapter()
        messages = load_fixture("track_metadata.json")

        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        assert len(player.cue_points) == 1
        assert len(player.memory_points) == 3
        assert len(player.hot_cues) == 2
        assert player.hot_cues[0]["slot"] == 1


class TestBeatEvents:
    def test_beat_callback(self):
        adapter = BridgeAdapter()
        beats = []
        adapter.on_beat = lambda pn, bwb, bpm: beats.append((pn, bwb, bpm))

        messages = load_fixture("playback_session.json")
        for msg in messages:
            adapter.handle_message(msg)

        # playback_session.json has 5 beat messages
        assert len(beats) == 5
        player_nums = {b[0] for b in beats}
        assert player_nums == {1}
        beat_positions = [b[1] for b in beats]
        assert beat_positions == [1, 2, 3, 4, 1]


class TestTransition:
    def test_two_players_tracked(self):
        adapter = BridgeAdapter()
        messages = load_fixture("transition.json")

        for msg in messages:
            adapter.handle_message(msg)

        # Both players should have been tracked
        assert adapter.get_player(1) is not None
        assert adapter.get_player(2) is not None

    def test_deck2_metadata_loaded(self):
        adapter = BridgeAdapter()
        messages = load_fixture("transition.json")

        for msg in messages:
            adapter.handle_message(msg)

        player2 = adapter.get_player(2)
        assert player2 is not None
        assert player2.title == "Opus"
        assert player2.artist == "Eric Prydz"

    def test_on_air_transitions(self):
        adapter = BridgeAdapter()
        on_air_history: list[tuple[int, bool]] = []
        adapter.on_player_update = lambda p: on_air_history.append((p.player_number, p.is_on_air))

        messages = load_fixture("transition.json")
        for msg in messages:
            adapter.handle_message(msg)

        # Player 2 should go from off-air to on-air
        p2_states = [(pn, oa) for pn, oa in on_air_history if pn == 2]
        assert any(not oa for _, oa in p2_states)  # was off
        assert any(oa for _, oa in p2_states)       # then on

        # Player 1 should go from on-air to off-air
        p1_states = [(pn, oa) for pn, oa in on_air_history if pn == 1]
        assert any(oa for _, oa in p1_states)       # was on
        assert any(not oa for _, oa in p1_states)   # then off
