"""Typed command builders and response parsers for the bridge command channel.

Commands are sent from Python → Java bridge over the existing WebSocket.
Responses come back as 'command_response' messages correlated by request_id.

See specs/feat-bridge-command-channel/spec.md for the full protocol.
"""

import json
import uuid
from dataclasses import dataclass


# ── Command dataclasses ──────────────────────────────────────────────────

@dataclass
class BrowseRootMenuCommand:
    """List top-level folders/playlists on a USB/SD slot."""
    player_number: int
    slot: str  # "usb" | "sd"

    def to_wire(self) -> tuple[str, dict]:
        return "browse_root_menu", {
            "player_number": self.player_number,
            "slot": self.slot,
        }


@dataclass
class BrowsePlaylistCommand:
    """List tracks/folders within a specific folder."""
    player_number: int
    slot: str  # "usb" | "sd"
    folder_id: int
    sort_order: str = "default"

    def to_wire(self) -> tuple[str, dict]:
        return "browse_playlist", {
            "player_number": self.player_number,
            "slot": self.slot,
            "folder_id": self.folder_id,
            "sort_order": self.sort_order,
        }


@dataclass
class BrowseAllTracksCommand:
    """Flat list of all tracks on a USB/SD slot."""
    player_number: int
    slot: str  # "usb" | "sd"
    sort_order: str = "default"

    def to_wire(self) -> tuple[str, dict]:
        return "browse_all_tracks", {
            "player_number": self.player_number,
            "slot": self.slot,
            "sort_order": self.sort_order,
        }


@dataclass
class LoadTrackCommand:
    """Load a specific track onto a CDJ deck."""
    target_player: int
    rekordbox_id: int
    source_player: int
    source_slot: str  # "usb" | "sd"
    source_type: str = "rekordbox"

    def to_wire(self) -> tuple[str, dict]:
        return "load_track", {
            "target_player": self.target_player,
            "rekordbox_id": self.rekordbox_id,
            "source_player": self.source_player,
            "source_slot": self.source_slot,
            "source_type": self.source_type,
        }


# ── Response dataclass ───────────────────────────────────────────────────

@dataclass
class CommandResponse:
    """Parsed response from the bridge for a command."""
    request_id: str
    status: str  # "ok" | "error"
    command: str
    data: dict
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# ── Serialization ────────────────────────────────────────────────────────

Command = BrowseRootMenuCommand | BrowsePlaylistCommand | BrowseAllTracksCommand | LoadTrackCommand


def serialize_command(cmd: Command) -> tuple[str, str]:
    """Serialize a command to (request_id, json_string) for sending over WebSocket.

    Returns the request_id so the caller can correlate the response.
    """
    request_id = str(uuid.uuid4())
    command_name, params = cmd.to_wire()
    envelope = {
        "command": command_name,
        "request_id": request_id,
        "params": params,
    }
    return request_id, json.dumps(envelope)


def parse_command_response(payload: dict) -> CommandResponse:
    """Parse a command_response message payload into a CommandResponse."""
    return CommandResponse(
        request_id=payload.get("request_id", ""),
        status=payload.get("status", "error"),
        command=payload.get("command", ""),
        data=payload.get("data", {}),
        error_message=payload.get("error_message"),
    )
