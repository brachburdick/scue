"""Shared deck state dataclass used by all Pioneer connection backends."""

import time
from dataclasses import dataclass, asdict

# Seconds with no packets before a deck/device is considered stale
STALE_TIMEOUT = 5.0


@dataclass
class DeckState:
    """Real-time state for a single Pioneer deck/player."""

    channel: int = 0

    # Playback flags
    is_playing: bool = False
    is_on_air: bool = False
    is_synced: bool = False
    is_master: bool = False
    is_looping: bool = False

    # BPM
    original_bpm: float = 0.0       # Track's native BPM
    effective_bpm: float = 0.0      # BPM after pitch adjustment
    pitch_percent: float = 0.0      # Pitch fader offset in %

    # Position
    beat_number: int = 0            # Absolute beat from track start
    beat_within_bar: int = 0        # 1–4
    playback_position_ms: float = 0.0

    # Identity (from keepalive / status packets)
    device_name: str = ""
    player_number: int = 0          # 1–4 as reported by the hardware

    # Track metadata
    track_title: str = ""
    track_artist: str = ""
    track_key: str = ""
    track_genre: str = ""
    track_length_sec: float = 0.0
    rekordbox_id: int = 0

    # Timing / diagnostics
    last_update: float = 0.0

    def is_stale(self) -> bool:
        if self.last_update == 0:
            return True
        return (time.time() - self.last_update) > STALE_TIMEOUT

    def to_dict(self) -> dict:
        return asdict(self)
