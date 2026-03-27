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
    MEDIA_CHANGE,
    PHRASE_ANALYSIS,
    PLAYER_STATUS,
    TRACK_METADATA,
    BridgeMessage,
    MediaChangePayload,
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


class TestClear:
    """BridgeAdapter.clear() resets devices/players but preserves callbacks."""

    def test_clear_resets_devices_and_players(self):
        adapter = BridgeAdapter()
        messages = load_fixture("device_discovery.json")
        for msg in messages:
            adapter.handle_message(msg)
        assert len(adapter.devices) > 0

        adapter.clear()
        assert adapter.devices == {}
        assert adapter.players == {}

    def test_clear_preserves_callbacks(self):
        adapter = BridgeAdapter()
        cb_device = lambda d, a: None
        cb_player = lambda p: None
        cb_beat = lambda pn, bwb, bpm: None
        cb_track = lambda pn, t, a: None
        adapter.on_device_change = cb_device
        adapter.on_player_update = cb_player
        adapter.on_beat = cb_beat
        adapter.on_track_loaded = cb_track

        # Populate some state then clear
        messages = load_fixture("device_discovery.json")
        for msg in messages:
            adapter.handle_message(msg)
        adapter.clear()

        assert adapter.on_device_change is cb_device
        assert adapter.on_player_update is cb_player
        assert adapter.on_beat is cb_beat
        assert adapter.on_track_loaded is cb_track

    def test_clear_preserves_bridge_status(self):
        adapter = BridgeAdapter()
        adapter.bridge_connected = True
        adapter.bridge_version = "1.2.0"

        adapter.clear()

        assert adapter.bridge_connected is True
        assert adapter.bridge_version == "1.2.0"

    def test_clear_allows_fresh_data_accumulation(self):
        """After clear(), new messages populate state from scratch."""
        adapter = BridgeAdapter()
        messages = load_fixture("device_discovery.json")
        for msg in messages:
            adapter.handle_message(msg)
        assert len(adapter.devices) == 3

        adapter.clear()
        assert len(adapter.devices) == 0

        # Re-feed messages — state rebuilds
        for msg in messages:
            adapter.handle_message(msg)
        assert len(adapter.devices) == 3


class TestPlaybackPosition:
    """Test playback_position_ms derivation from beat_number + beat_grid."""

    def test_position_computed_from_beat_grid(self):
        """After receiving beat_grid + player_status, playback_position_ms is derived."""
        adapter = BridgeAdapter()

        # Feed beat_grid first
        beat_grid_msgs = load_fixture("beat_grid.json")
        for msg in beat_grid_msgs:
            adapter.handle_message(msg)

        # Feed a player_status with beat_number matching a grid entry
        messages = load_fixture("playback_session.json")
        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        # playback_session.json has beat_number values; with beat_grid loaded,
        # playback_position_ms should be non-None
        assert player.playback_position_ms is not None
        assert player.playback_position_ms > 0

    def test_position_none_without_beat_grid(self):
        """Without beat_grid data, playback_position_ms is None."""
        adapter = BridgeAdapter()

        # Feed player_status WITHOUT beat_grid
        messages = load_fixture("playback_session.json")
        for msg in messages:
            adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        # First status has beat_number=0 (cued), so position is None
        # But even later statuses with beat_number>0 have no grid -> None
        assert player.playback_position_ms is None

    def test_position_none_for_beat_zero(self):
        """beat_number=0 means no track / unknown, position should be None."""
        adapter = BridgeAdapter()
        player = PlayerState(player_number=1)
        player.beat_grid = [{"beat_number": 1, "time_ms": 250.0, "bpm": 128.0}]

        result = BridgeAdapter._compute_position_ms(player, 0)
        assert result is None

    def test_position_interpolation(self):
        """Position interpolates between grid entries using BPM."""
        player = PlayerState(player_number=1)
        player.beat_grid = [
            {"beat_number": 1, "time_ms": 250.0, "bpm": 120.0},
            {"beat_number": 5, "time_ms": 2250.0, "bpm": 120.0},
        ]
        # Beat 3 = entry at beat 1 + 2 beats at 120 BPM (500ms/beat) = 250 + 1000 = 1250
        result = BridgeAdapter._compute_position_ms(player, 3)
        assert result is not None
        assert abs(result - 1250.0) < 1.0


class TestStatusDictPlayerFields:
    """Test that to_status_dict() includes new player fields."""

    def test_player_dict_includes_new_fields(self):
        from scue.bridge.manager import BridgeManager

        mgr = BridgeManager()
        mgr._status = "running"

        # Manually set up adapter state
        player = PlayerState(player_number=1)
        player.bpm = 128.0
        player.playback_position_ms = 5000.0
        player.track_source_player = 1
        player.track_source_slot = "usb"
        mgr._adapter._players[1] = player

        status = mgr.to_status_dict()
        p1 = status["players"]["1"]

        assert p1["playback_position_ms"] == 5000.0
        assert p1["track_source_player"] == 1
        assert p1["track_source_slot"] == "usb"

    def test_player_dict_null_position(self):
        from scue.bridge.manager import BridgeManager

        mgr = BridgeManager()
        mgr._status = "running"

        player = PlayerState(player_number=1)
        player.bpm = 128.0
        player.playback_position_ms = None
        mgr._adapter._players[1] = player

        status = mgr.to_status_dict()
        p1 = status["players"]["1"]

        assert p1["playback_position_ms"] is None


class TestMediaChange:
    """Tests for media_change (USB/SD hot-swap) message handling."""

    def test_media_change_parsed(self):
        """media_change messages parse into MediaChangePayload."""
        messages = load_fixture("media_change.json")
        media_msgs = [m for m in messages if m.type == MEDIA_CHANGE]
        assert len(media_msgs) == 4  # unmount usb, mount usb, unmount sd, mount sd

    def test_unmount_callback_fires(self):
        adapter = BridgeAdapter()
        events: list[tuple[int, str, str]] = []
        adapter.on_media_change = lambda p, s, a: events.append((p, s, a))

        for msg in load_fixture("media_change.json"):
            adapter.handle_message(msg)

        unmounts = [(p, s, a) for p, s, a in events if a == "unmounted"]
        assert len(unmounts) == 2
        assert (1, "usb", "unmounted") in unmounts
        assert (1, "sd", "unmounted") in unmounts

    def test_mount_callback_fires(self):
        adapter = BridgeAdapter()
        events: list[tuple[int, str, str]] = []
        adapter.on_media_change = lambda p, s, a: events.append((p, s, a))

        for msg in load_fixture("media_change.json"):
            adapter.handle_message(msg)

        mounts = [(p, s, a) for p, s, a in events if a == "mounted"]
        assert len(mounts) == 2
        assert (1, "usb", "mounted") in mounts
        assert (1, "sd", "mounted") in mounts

    def test_no_callback_no_error(self):
        """Adapter handles media_change gracefully when no callback is set."""
        adapter = BridgeAdapter()
        # on_media_change defaults to None
        for msg in load_fixture("media_change.json"):
            adapter.handle_message(msg)  # Should not raise

    def test_media_change_payload_fields(self):
        """Verify MediaChangePayload has correct field values from fixture."""
        from scue.bridge.messages import parse_typed_payload

        messages = load_fixture("media_change.json")
        media_msgs = [m for m in messages if m.type == MEDIA_CHANGE]

        # First: USB unmount
        p1 = parse_typed_payload(media_msgs[0])
        assert isinstance(p1, MediaChangePayload)
        assert p1.slot == "usb"
        assert p1.action == "unmounted"
        assert p1.player_number == 1
        assert p1.media_name is None

        # Second: USB mount with media details
        p2 = parse_typed_payload(media_msgs[1])
        assert isinstance(p2, MediaChangePayload)
        assert p2.slot == "usb"
        assert p2.action == "mounted"
        assert p2.media_name == "PIONEER DJ"
        assert p2.track_count == 342

    def test_media_change_does_not_affect_player_state(self):
        """media_change events should not alter player state or devices."""
        adapter = BridgeAdapter()
        messages = load_fixture("media_change.json")
        for msg in messages:
            adapter.handle_message(msg)

        # Device should exist from device_found, but media_change doesn't add/remove devices
        assert len(adapter.devices) == 1  # Only the XDJ-AZ from device_found
        # Player state should be empty — media_change doesn't create player entries
        assert len(adapter._players) == 0

    def test_rapid_unmount_mount_preserves_order(self):
        """Rapid unmount→mount on same slot fires callbacks in order."""
        adapter = BridgeAdapter()
        events: list[tuple[int, str, str]] = []
        adapter.on_media_change = lambda p, s, a: events.append((p, s, a))

        for msg in load_fixture("media_change.json"):
            adapter.handle_message(msg)

        # USB: unmount then mount
        usb_events = [(p, s, a) for p, s, a in events if s == "usb"]
        assert usb_events == [(1, "usb", "unmounted"), (1, "usb", "mounted")]

        # SD: unmount then mount
        sd_events = [(p, s, a) for p, s, a in events if s == "sd"]
        assert sd_events == [(1, "sd", "unmounted"), (1, "sd", "mounted")]

    def test_multi_player_media_changes(self):
        """media_change events from different players are distinguished."""
        adapter = BridgeAdapter()
        events: list[tuple[int, str, str]] = []
        adapter.on_media_change = lambda p, s, a: events.append((p, s, a))

        for msg in load_fixture("media_change_multi.json"):
            adapter.handle_message(msg)

        # Player 2: usb unmount + mount; Player 1: sd unmount
        p2_events = [(p, s, a) for p, s, a in events if p == 2]
        assert p2_events == [(2, "usb", "unmounted"), (2, "usb", "mounted")]

        p1_events = [(p, s, a) for p, s, a in events if p == 1]
        assert p1_events == [(1, "sd", "unmounted")]

    def test_media_change_interleaved_with_player_status(self):
        """media_change between player_status updates doesn't corrupt tracking state."""
        adapter = BridgeAdapter()
        events: list[tuple[int, str, str]] = []
        adapter.on_media_change = lambda p, s, a: events.append((p, s, a))

        for msg in load_fixture("media_change_multi.json"):
            adapter.handle_message(msg)

        # Player 1 had player_status before AND after player 2's media_change
        assert 1 in adapter._players
        p1 = adapter._players[1]
        assert p1.bpm == 128.0
        assert p1.pitch == 0.02  # Second status update value
        assert p1.playback_state == "playing"

        # Player 2 has no player_status — only media_change (which doesn't create state)
        assert 2 not in adapter._players

    def test_unmount_payload_defaults(self):
        """Unmount payloads carry media_name=None and track_count=-1."""
        from scue.bridge.messages import parse_typed_payload

        messages = load_fixture("media_change.json")
        unmounts = [m for m in messages if m.type == MEDIA_CHANGE
                    and m.payload.get("action") == "unmounted"]
        assert len(unmounts) == 2

        for msg in unmounts:
            p = parse_typed_payload(msg)
            assert isinstance(p, MediaChangePayload)
            assert p.media_name is None
            assert p.track_count == -1

    def test_mount_payload_has_media_details(self):
        """Mount payloads carry media_name and positive track_count."""
        from scue.bridge.messages import parse_typed_payload

        messages = load_fixture("media_change.json")
        mounts = [m for m in messages if m.type == MEDIA_CHANGE
                   and m.payload.get("action") == "mounted"]
        assert len(mounts) == 2

        for msg in mounts:
            p = parse_typed_payload(msg)
            assert isinstance(p, MediaChangePayload)
            assert p.media_name is not None
            assert p.track_count > 0

    def test_media_change_callback_receives_correct_args(self):
        """Callback signature is (player_number, slot, action) — verify all three."""
        adapter = BridgeAdapter()
        received = {}
        def capture(player_number, slot, action):
            received["player_number"] = player_number
            received["slot"] = slot
            received["action"] = action
        adapter.on_media_change = capture

        # Feed just the first media_change (usb unmount)
        messages = load_fixture("media_change.json")
        media_msgs = [m for m in messages if m.type == MEDIA_CHANGE]
        adapter.handle_message(media_msgs[0])

        assert received["player_number"] == 1
        assert received["slot"] == "usb"
        assert received["action"] == "unmounted"
