"""Tests for bridge command serialization and response parsing."""

import json

import pytest

from scue.bridge.commands import (
    BrowseAllTracksCommand,
    BrowsePlaylistCommand,
    BrowseRootMenuCommand,
    CommandResponse,
    LoadTrackCommand,
    parse_command_response,
    serialize_command,
)


class TestCommandSerialization:
    """Test command → JSON serialization."""

    def test_load_track_serialization(self):
        cmd = LoadTrackCommand(
            target_player=1,
            rekordbox_id=42001,
            source_player=1,
            source_slot="usb",
        )
        request_id, json_str = serialize_command(cmd)

        assert request_id  # non-empty UUID
        data = json.loads(json_str)
        assert data["command"] == "load_track"
        assert data["request_id"] == request_id
        assert data["params"]["target_player"] == 1
        assert data["params"]["rekordbox_id"] == 42001
        assert data["params"]["source_player"] == 1
        assert data["params"]["source_slot"] == "usb"
        assert data["params"]["source_type"] == "rekordbox"

    def test_browse_all_tracks_serialization(self):
        cmd = BrowseAllTracksCommand(player_number=2, slot="sd")
        request_id, json_str = serialize_command(cmd)

        data = json.loads(json_str)
        assert data["command"] == "browse_all_tracks"
        assert data["params"]["player_number"] == 2
        assert data["params"]["slot"] == "sd"

    def test_browse_root_menu_serialization(self):
        cmd = BrowseRootMenuCommand(player_number=1, slot="usb")
        request_id, json_str = serialize_command(cmd)

        data = json.loads(json_str)
        assert data["command"] == "browse_root_menu"
        assert data["params"]["player_number"] == 1

    def test_browse_playlist_serialization(self):
        cmd = BrowsePlaylistCommand(
            player_number=1, slot="usb", folder_id=42
        )
        request_id, json_str = serialize_command(cmd)

        data = json.loads(json_str)
        assert data["command"] == "browse_playlist"
        assert data["params"]["folder_id"] == 42
        assert data["params"]["is_folder"] is True  # default

    def test_browse_playlist_leaf_serialization(self):
        """is_folder=False for leaf playlist (list tracks, not sub-folders)."""
        cmd = BrowsePlaylistCommand(
            player_number=1, slot="usb", folder_id=8, is_folder=False
        )
        _, json_str = serialize_command(cmd)

        data = json.loads(json_str)
        assert data["command"] == "browse_playlist"
        assert data["params"]["folder_id"] == 8
        assert data["params"]["is_folder"] is False

    def test_unique_request_ids(self):
        cmd = LoadTrackCommand(
            target_player=1, rekordbox_id=1, source_player=1, source_slot="usb"
        )
        id1, _ = serialize_command(cmd)
        id2, _ = serialize_command(cmd)
        assert id1 != id2


class TestCommandResponseParsing:
    """Test response payload → CommandResponse parsing."""

    def test_ok_response(self):
        payload = {
            "request_id": "abc-123",
            "status": "ok",
            "command": "load_track",
            "data": {"target_player": 1, "rekordbox_id": 42001},
        }
        resp = parse_command_response(payload)

        assert resp.ok
        assert resp.request_id == "abc-123"
        assert resp.command == "load_track"
        assert resp.data["rekordbox_id"] == 42001
        assert resp.error_message is None

    def test_error_response(self):
        payload = {
            "request_id": "abc-456",
            "status": "error",
            "command": "browse_all_tracks",
            "data": {},
            "error_message": "ConnectionManager not running",
        }
        resp = parse_command_response(payload)

        assert not resp.ok
        assert resp.error_message == "ConnectionManager not running"

    def test_missing_fields_have_defaults(self):
        payload = {"request_id": "x"}
        resp = parse_command_response(payload)

        assert resp.status == "error"
        assert resp.command == ""
        assert resp.data == {}


class TestCommandResponsePayload:
    """Test that command_response messages parse via the standard message pipeline."""

    def test_command_response_in_all_types(self):
        from scue.bridge.messages import ALL_TYPES, COMMAND_RESPONSE
        assert COMMAND_RESPONSE in ALL_TYPES

    def test_parse_command_response_message(self):
        from scue.bridge.messages import parse_message

        raw = json.dumps({
            "type": "command_response",
            "timestamp": 1234567890.5,
            "player_number": None,
            "payload": {
                "request_id": "test-123",
                "status": "ok",
                "command": "load_track",
                "data": {},
            },
        })
        msg = parse_message(raw)
        assert msg.type == "command_response"
        assert msg.payload["request_id"] == "test-123"
