#!/usr/bin/env python3
"""CLI: replay captured Pro DJ Link UDP packets for testing.

Reads a JSON packet capture file and retransmits each packet to localhost,
allowing Layer 1B (ProDJLinkClient) to be tested without real Pioneer hardware.

Usage:
    # Replay a capture at real speed:
    python tools/mock_prodjlink.py tests/fixtures/prodjlink/my_capture.json

    # Replay at 2x speed:
    python tools/mock_prodjlink.py tests/fixtures/prodjlink/my_capture.json --speed 2.0

Capture JSON format:
    [
      { "src_ip": "169.254.11.53", "src_port": 50000, "timestamp": 1700000000.0, "data_hex": "5173..." },
      ...
    ]

Status: STUB — not yet implemented (Milestone 2).
"""

import argparse
import json
import socket
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Replay Pro DJ Link packet captures")
    parser.add_argument("capture_file", help="Path to JSON capture file")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playback speed multiplier (default 1.0 = real time)")
    parser.add_argument("--target", default="127.0.0.1",
                        help="Target host to send packets to (default 127.0.0.1)")
    args = parser.parse_args()

    capture_path = Path(args.capture_file)
    if not capture_path.exists():
        print(f"Error: capture file not found: {capture_path}", file=sys.stderr)
        sys.exit(1)

    with open(capture_path) as f:
        packets = json.load(f)

    print(f"Loaded {len(packets)} packets from {capture_path}")
    print("TODO: replay not yet implemented — see Milestone 2")

    # TODO(milestone-2): implement
    # for i, pkt in enumerate(packets):
    #     data = bytes.fromhex(pkt["data_hex"])
    #     port = pkt["src_port"]
    #     delay = (packets[i]["timestamp"] - packets[i-1]["timestamp"]) / args.speed if i > 0 else 0
    #     time.sleep(max(0, delay))
    #     sock.sendto(data, (args.target, port))
    #     print(f"Sent packet {i+1}/{len(packets)}: {len(data)} bytes to port {port}")


if __name__ == "__main__":
    main()
