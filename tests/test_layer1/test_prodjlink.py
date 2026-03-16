"""Tests for Pro DJ Link packet parsing.

Tests use synthetic packet data constructed from known offsets.
No real Pioneer hardware required.
"""

import struct
import pytest

from scue.layer1.prodjlink import (
    ProDJLinkClient, MAGIC, PKT_STATUS, PKT_KEEPALIVE,
    ST_FLAGS, ST_BPM, ST_PITCH, ST_BEAT_NUM, ST_BEAT_BAR, ST_MINLEN,
    FLAG_PLAYING, FLAG_MASTER, FLAG_SYNC, FLAG_ON_AIR,
)


def _make_status_packet(
    player_num: int = 1,
    bpm_x100: int = 12800,      # 128.00 BPM
    pitch: int = 0x100000,      # 0% pitch
    beat_num: int = 33,
    beat_bar: int = 1,
    flags: int = FLAG_PLAYING | FLAG_ON_AIR,
    rb_id: int = 42,
) -> bytes:
    """Build a minimal synthetic CDJ status packet."""
    pkt = bytearray(ST_MINLEN + 1)

    # Magic header
    pkt[:6] = MAGIC

    # Packet type at offset 0x0a
    pkt[0x0a] = PKT_STATUS

    # Player number
    pkt[0x21] = player_num

    # Rekordbox track ID (4 bytes big-endian)
    struct.pack_into(">I", pkt, 0x2c, rb_id)

    # Flags
    pkt[ST_FLAGS] = flags

    # BPM (4 bytes big-endian, BPM * 100)
    struct.pack_into(">I", pkt, ST_BPM, bpm_x100)

    # Pitch (3 bytes big-endian)
    pkt[ST_PITCH]     = (pitch >> 16) & 0xFF
    pkt[ST_PITCH + 1] = (pitch >> 8)  & 0xFF
    pkt[ST_PITCH + 2] = pitch         & 0xFF

    # Beat number (4 bytes big-endian)
    struct.pack_into(">I", pkt, ST_BEAT_NUM, beat_num)

    # Beat within bar
    pkt[ST_BEAT_BAR] = beat_bar

    return bytes(pkt)


class TestPacketParsing:

    def setup_method(self):
        self.client = ProDJLinkClient()

    def test_status_packet_bpm(self):
        pkt = _make_status_packet(bpm_x100=12800)
        self.client._on_packet(pkt, ("169.254.11.53", 50000))
        deck = self.client.decks.get(1)
        assert deck is not None
        assert deck.original_bpm == pytest.approx(128.0, abs=0.01)

    def test_status_packet_effective_bpm_at_neutral_pitch(self):
        pkt = _make_status_packet(bpm_x100=12800, pitch=0x100000)
        self.client._on_packet(pkt, ("169.254.11.53", 50000))
        deck = self.client.decks[1]
        assert deck.effective_bpm == pytest.approx(128.0, abs=0.01)
        assert deck.pitch_percent == pytest.approx(0.0, abs=0.01)

    def test_status_packet_flags(self):
        flags = FLAG_PLAYING | FLAG_ON_AIR | FLAG_MASTER
        pkt = _make_status_packet(flags=flags)
        self.client._on_packet(pkt, ("169.254.11.53", 50000))
        deck = self.client.decks[1]
        assert deck.is_playing is True
        assert deck.is_on_air is True
        assert deck.is_master is True
        assert deck.is_synced is False

    def test_status_packet_beat_position(self):
        pkt = _make_status_packet(beat_num=33, beat_bar=1)
        self.client._on_packet(pkt, ("169.254.11.53", 50000))
        deck = self.client.decks[1]
        assert deck.beat_number == 33
        assert deck.beat_within_bar == 1

    def test_non_magic_packet_ignored(self):
        garbage = b"\x00" * 100
        self.client._on_packet(garbage, ("169.254.11.53", 50000))
        assert not self.client.decks  # nothing parsed

    def test_packet_count_increments(self):
        pkt = _make_status_packet()
        self.client._on_packet(pkt, ("169.254.11.53", 50000))
        self.client._on_packet(pkt, ("169.254.11.53", 50000))
        assert self.client.packet_count == 2
