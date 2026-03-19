"""Tests for FallbackParser — standalone UDP Pro DJ Link parser."""

import struct
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scue.bridge.fallback import (
    ANNOUNCE_PORT,
    STATUS_PORT,
    MAGIC,
    PKT_KEEPALIVE,
    PKT_STATUS,
    KA_MINLEN,
    ST_MINLEN,
    FLAG_PLAYING,
    FLAG_ON_AIR,
    FallbackParser,
)
from scue.bridge.messages import BEAT, DEVICE_FOUND, PLAYER_STATUS, BridgeMessage


def _make_keepalive_packet(
    name: str = "XDJ-AZ",
    player_num: int = 1,
    ip: str = "169.254.20.101",
) -> bytes:
    """Build a minimal Pro DJ Link keepalive packet."""
    buf = bytearray(KA_MINLEN)
    buf[0:6] = MAGIC
    buf[0x0A] = PKT_KEEPALIVE
    # Device name (20 bytes, null-padded)
    name_bytes = name.encode("utf-8")[:20]
    buf[0x0C: 0x0C + len(name_bytes)] = name_bytes
    # Player number
    buf[0x21] = player_num
    # IP address (4 bytes big-endian)
    ip_parts = [int(p) for p in ip.split(".")]
    buf[0x2A: 0x2E] = bytes(ip_parts)
    return bytes(buf)


def _make_status_packet(
    player_num: int = 1,
    bpm: float = 128.0,
    pitch_percent: float = 0.0,
    beat_bar: int = 1,
    beat_num: int = 1,
    playing: bool = True,
    on_air: bool = True,
) -> bytes:
    """Build a minimal Pro DJ Link status packet."""
    buf = bytearray(ST_MINLEN)
    buf[0:6] = MAGIC
    buf[0x0A] = PKT_STATUS
    buf[0x21] = player_num

    # Flags
    flags = 0
    if playing:
        flags |= FLAG_PLAYING
    if on_air:
        flags |= FLAG_ON_AIR
    buf[0x89] = flags

    # BPM (4 bytes, value * 100)
    struct.pack_into(">I", buf, 0x92, int(bpm * 100))

    # Pitch (3 bytes, 0x100000 = 0%)
    pitch_raw = int((1.0 + pitch_percent / 100.0) * 0x100000)
    buf[0x96] = (pitch_raw >> 16) & 0xFF
    buf[0x97] = (pitch_raw >> 8) & 0xFF
    buf[0x98] = pitch_raw & 0xFF

    # Beat number (4 bytes)
    struct.pack_into(">I", buf, 0xA0, beat_num)

    # Beat within bar
    buf[0xA6] = beat_bar

    return bytes(buf)


class TestFallbackParserPacketParsing:
    """Test packet parsing logic without real UDP sockets."""

    def test_fallback_parser_emits_device_found(self):
        """Keepalive packet should emit DEVICE_FOUND BridgeMessage."""
        received: list[BridgeMessage] = []
        parser = FallbackParser(on_message=received.append)
        parser._running = True

        pkt = _make_keepalive_packet(name="XDJ-AZ", player_num=1, ip="169.254.20.101")
        parser._on_packet(pkt, ("169.254.20.101", ANNOUNCE_PORT))

        assert len(received) == 1
        msg = received[0]
        assert msg.type == DEVICE_FOUND
        assert msg.payload["device_name"] == "XDJ-AZ"
        assert msg.payload["device_number"] == 1
        assert msg.payload["ip_address"] == "169.254.20.101"

    def test_fallback_parser_emits_player_status(self):
        """Status packet should emit PLAYER_STATUS BridgeMessage."""
        received: list[BridgeMessage] = []
        parser = FallbackParser(on_message=received.append)
        parser._running = True

        pkt = _make_status_packet(player_num=1, bpm=128.0, playing=True)
        parser._on_packet(pkt, ("169.254.20.101", STATUS_PORT))

        # Status packet emits player_status (+ possibly beat)
        status_msgs = [m for m in received if m.type == PLAYER_STATUS]
        assert len(status_msgs) == 1
        msg = status_msgs[0]
        assert msg.player_number == 1
        assert msg.payload["bpm"] == 128.0
        assert msg.payload["playback_state"] == "playing"

    def test_fallback_parser_emits_beat(self):
        """Status packet with beat change should emit BEAT BridgeMessage."""
        received: list[BridgeMessage] = []
        parser = FallbackParser(on_message=received.append)
        parser._running = True

        # First packet establishes beat_within_bar=1
        pkt1 = _make_status_packet(player_num=1, bpm=128.0, beat_bar=1, playing=True)
        parser._on_packet(pkt1, ("169.254.20.101", STATUS_PORT))

        # Second packet with beat_within_bar=2 should trigger beat event
        pkt2 = _make_status_packet(player_num=1, bpm=128.0, beat_bar=2, playing=True)
        parser._on_packet(pkt2, ("169.254.20.101", STATUS_PORT))

        beat_msgs = [m for m in received if m.type == BEAT]
        assert len(beat_msgs) >= 1
        assert beat_msgs[-1].payload["beat_within_bar"] == 2

    def test_fallback_parser_callback_fires(self):
        """on_message callback should fire for each emitted message."""
        callback = MagicMock()
        parser = FallbackParser(on_message=callback)
        parser._running = True

        pkt = _make_keepalive_packet()
        parser._on_packet(pkt, ("169.254.20.101", ANNOUNCE_PORT))

        assert callback.call_count == 1
        msg = callback.call_args[0][0]
        assert isinstance(msg, BridgeMessage)

    def test_fallback_parser_ignores_non_magic_packets(self):
        """Packets without Pro DJ Link magic should be silently dropped."""
        received: list[BridgeMessage] = []
        parser = FallbackParser(on_message=received.append)
        parser._running = True

        parser._on_packet(b"\x00" * 50, ("169.254.20.101", STATUS_PORT))
        assert len(received) == 0
        assert parser.packet_count == 1  # counted but not emitted


class TestFallbackParserLifecycle:
    """Test start/stop without real UDP sockets."""

    @pytest.mark.asyncio
    async def test_fallback_parser_start_stop(self):
        """Parser starts and stops without error (mocked sockets)."""
        parser = FallbackParser()

        with patch(
            "scue.bridge.fallback.get_local_interfaces",
            return_value=[{
                "interface": "en16",
                "ip": "169.254.20.47",
                "netmask": "255.255.0.0",
                "broadcast": "169.254.255.255",
            }],
        ), patch(
            "scue.bridge.fallback.make_udp_socket",
        ) as mock_sock, patch(
            "asyncio.get_event_loop",
        ) as mock_loop:
            mock_transport = MagicMock()
            mock_loop.return_value.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, None)
            )
            mock_sock.return_value = MagicMock()

            await parser.start()
            assert parser.running is True
            # 2 transports: one for ANNOUNCE_PORT, one for STATUS_PORT
            assert len(parser._transports) == 2

            parser.stop()
            assert parser.running is False
            assert mock_transport.close.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_parser_interface_filtering(self):
        """When interface is specified, parser should prefer matching interface."""
        parser = FallbackParser(interface="en16")

        all_ifaces = [
            {"interface": "en0", "ip": "192.168.1.100", "netmask": "", "broadcast": ""},
            {"interface": "en16", "ip": "169.254.20.47", "netmask": "", "broadcast": ""},
        ]

        with patch(
            "scue.bridge.fallback.get_local_interfaces",
            return_value=all_ifaces,
        ), patch(
            "scue.bridge.fallback.make_udp_socket",
        ) as mock_sock, patch(
            "asyncio.get_event_loop",
        ) as mock_loop:
            mock_transport = MagicMock()
            mock_loop.return_value.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, None)
            )
            mock_sock.return_value = MagicMock()

            await parser.start()

            # Should only create sockets for en16, not en0
            sock_calls = mock_sock.call_args_list
            for call in sock_calls:
                assert call[0][0] == "169.254.20.47"  # only en16's IP

            parser.stop()
