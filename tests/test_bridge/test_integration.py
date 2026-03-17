"""Integration tests — full session lifecycle through the bridge adapter.

These tests feed sequences of raw JSON messages (from fixture files) through
the adapter and verify end-to-end state transitions that span multiple message
types, as opposed to the unit tests in test_adapter.py which test each message
type in isolation.
"""

import json
from pathlib import Path

import pytest

from scue.bridge.adapter import BridgeAdapter, DeviceInfo, PlayerState
from scue.bridge.messages import BridgeMessage, parse_message

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bridge"


def load_fixture(name: str) -> list[BridgeMessage]:
    with open(FIXTURES_DIR / name) as f:
        raw_list = json.load(f)
    return [parse_message(json.dumps(m)) for m in raw_list]


def feed_all(adapter: BridgeAdapter, fixture: str) -> None:
    for msg in load_fixture(fixture):
        adapter.handle_message(msg)


class TestFullSessionLifecycle:
    """Simulate a realistic session: discovery → metadata → playback → transition → shutdown."""

    def test_discovery_then_playback_accumulates_state(self):
        """Device discovery followed by playback should build up complete state."""
        adapter = BridgeAdapter()

        # Phase 1: devices come online
        feed_all(adapter, "device_discovery.json")
        assert len(adapter.devices) == 3
        assert adapter.bridge_connected is True

        # Phase 2: track loaded on player 1
        feed_all(adapter, "track_metadata.json")
        player1 = adapter.get_player(1)
        assert player1 is not None
        assert player1.title == "Strobe"
        assert len(player1.beat_grid) == 8
        assert len(player1.phrases) == 6
        assert len(player1.hot_cues) == 2

        # Phase 3: playback begins
        feed_all(adapter, "playback_session.json")
        player1 = adapter.get_player(1)
        assert player1 is not None
        assert player1.playback_state == "playing"
        assert player1.pitch == 2.5
        assert player1.bpm == 128.0

        # Devices should still be present
        assert len(adapter.devices) == 3

    def test_transition_updates_both_players(self):
        """A DJ transition should update on_air state for both decks."""
        adapter = BridgeAdapter()

        # Setup: discover devices, load track on player 1
        feed_all(adapter, "device_discovery.json")
        feed_all(adapter, "track_metadata.json")

        # Transition: player 2 loads, goes on-air, player 1 goes off-air
        feed_all(adapter, "transition.json")

        player1 = adapter.get_player(1)
        player2 = adapter.get_player(2)
        assert player1 is not None
        assert player2 is not None

        # After transition, player 1 is off-air
        assert player1.is_on_air is False
        # Player 2 is on-air with Opus loaded
        assert player2.is_on_air is True
        assert player2.title == "Opus"
        assert player2.artist == "Eric Prydz"

    def test_device_lost_removes_device_but_preserves_player(self):
        """After device_lost, the device map should shrink but player state remains.

        Player state is kept because it may be needed for logging/history.
        The adapter does not clear player state on device loss.
        """
        adapter = BridgeAdapter()

        feed_all(adapter, "device_discovery.json")
        assert "169.254.20.101" in adapter.devices

        feed_all(adapter, "transition.json")
        # transition.json ends with device_lost for player 1 at 169.254.20.101
        assert "169.254.20.101" not in adapter.devices

        # Player state should still be accessible (historical data)
        player1 = adapter.get_player(1)
        assert player1 is not None


class TestCallbackOrdering:
    """Verify callbacks fire in the expected order during a session."""

    def test_callbacks_fire_in_sequence(self):
        adapter = BridgeAdapter()
        events: list[str] = []

        adapter.on_device_change = lambda d, a: events.append(f"device_{a}:{d.device_name}")
        adapter.on_track_loaded = lambda pn, t, a: events.append(f"track:{pn}:{t}")
        adapter.on_player_update = lambda p: events.append(f"player:{p.player_number}:{p.playback_state}")
        adapter.on_beat = lambda pn, bwb, bpm: events.append(f"beat:{pn}:{bwb}")

        feed_all(adapter, "device_discovery.json")
        feed_all(adapter, "track_metadata.json")
        feed_all(adapter, "playback_session.json")

        # Device discovery should come first
        assert events[0] == "device_found:XDJ-AZ"

        # Track loaded callback should fire for Strobe
        track_events = [e for e in events if e.startswith("track:")]
        assert any("Strobe" in e for e in track_events)

        # Beat events should come after playback starts
        beat_events = [e for e in events if e.startswith("beat:")]
        assert len(beat_events) == 5
        assert beat_events[0] == "beat:1:1"

    def test_device_lost_callback_fires_with_correct_info(self):
        adapter = BridgeAdapter()
        lost_devices: list[DeviceInfo] = []
        adapter.on_device_change = lambda d, a: lost_devices.append(d) if a == "lost" else None

        feed_all(adapter, "device_discovery.json")
        feed_all(adapter, "transition.json")

        assert len(lost_devices) == 1
        assert lost_devices[0].device_name == "XDJ-AZ"
        assert lost_devices[0].ip_address == "169.254.20.101"


class TestUnknownFields:
    """Verify adapter handles messages with extra/unknown fields gracefully."""

    def test_extra_payload_fields_ignored(self):
        """Bridge may add new fields. Adapter should not crash."""
        raw = {
            "type": "player_status",
            "timestamp": 1710600020.0,
            "player_number": 1,
            "payload": {
                "bpm": 130.0,
                "pitch": 0.0,
                "beat_within_bar": 1,
                "beat_number": 0,
                "playback_state": "playing",
                "is_on_air": True,
                "track_source_player": 1,
                "track_source_slot": "usb",
                "track_type": "rekordbox",
                "new_future_field": "should be ignored",
                "another_unknown": 42,
            },
        }
        adapter = BridgeAdapter()
        msg = parse_message(json.dumps(raw))
        adapter.handle_message(msg)

        player = adapter.get_player(1)
        assert player is not None
        assert player.bpm == 130.0
        assert player.playback_state == "playing"

    def test_device_with_uses_dlp_field(self):
        """Devices with uses_dlp field should populate DeviceInfo.uses_dlp."""
        raw = {
            "type": "device_found",
            "timestamp": 1710600001.0,
            "player_number": 1,
            "payload": {
                "device_name": "XDJ-AZ",
                "device_number": 1,
                "device_type": "cdj",
                "ip_address": "169.254.20.200",
                "uses_dlp": True,
            },
        }
        adapter = BridgeAdapter()
        msg = parse_message(json.dumps(raw))
        adapter.handle_message(msg)

        device = adapter.devices.get("169.254.20.200")
        assert device is not None
        assert device.uses_dlp is True

    def test_device_without_uses_dlp_defaults_false(self):
        """Older bridge versions may not send uses_dlp. Should default to False."""
        raw = {
            "type": "device_found",
            "timestamp": 1710600001.0,
            "player_number": 1,
            "payload": {
                "device_name": "CDJ-2000NXS2",
                "device_number": 1,
                "device_type": "cdj",
                "ip_address": "169.254.20.201",
            },
        }
        adapter = BridgeAdapter()
        msg = parse_message(json.dumps(raw))
        adapter.handle_message(msg)

        device = adapter.devices.get("169.254.20.201")
        assert device is not None
        assert device.uses_dlp is False


class TestMultiPlayerIsolation:
    """Verify that state updates for one player don't affect another."""

    def test_player_states_independent(self):
        adapter = BridgeAdapter()

        # Player 1 playing at 128 BPM
        msg1 = parse_message(json.dumps({
            "type": "player_status",
            "timestamp": 1710600020.0,
            "player_number": 1,
            "payload": {
                "bpm": 128.0, "pitch": 0.0, "beat_within_bar": 1,
                "beat_number": 0, "playback_state": "playing", "is_on_air": True,
                "track_source_player": 1, "track_source_slot": "usb", "track_type": "rekordbox",
            },
        }))
        # Player 2 cued at 140 BPM
        msg2 = parse_message(json.dumps({
            "type": "player_status",
            "timestamp": 1710600020.5,
            "player_number": 2,
            "payload": {
                "bpm": 140.0, "pitch": -3.0, "beat_within_bar": 1,
                "beat_number": 0, "playback_state": "cued", "is_on_air": False,
                "track_source_player": 2, "track_source_slot": "usb", "track_type": "rekordbox",
            },
        }))

        adapter.handle_message(msg1)
        adapter.handle_message(msg2)

        p1 = adapter.get_player(1)
        p2 = adapter.get_player(2)
        assert p1 is not None and p2 is not None

        assert p1.bpm == 128.0
        assert p1.playback_state == "playing"
        assert p1.is_on_air is True

        assert p2.bpm == 140.0
        assert p2.pitch == -3.0
        assert p2.playback_state == "cued"
        assert p2.is_on_air is False
