#!/usr/bin/env python3
"""CLI: replay captured Pro DJ Link UDP packets for testing.

Reads a JSON packet capture file and retransmits each packet to localhost,
allowing Layer 1B (ProDJLinkClient) to be tested without real Pioneer hardware.

Usage:
    # Replay a capture at real speed:
    python tools/mock_prodjlink.py tests/fixtures/prodjlink/my_capture.json

    # Replay at 2x speed:
    python tools/mock_prodjlink.py tests/fixtures/prodjlink/my_capture.json --speed 2.0

    # Loop forever:
    python tools/mock_prodjlink.py tests/fixtures/prodjlink/my_capture.json --loop

Capture JSON format:
    [
      { "src_ip": "169.254.11.53", "src_port": 50000, "timestamp": 1700000000.0, "data_hex": "5173..." },
      ...
    ]
"""

import argparse
import json
import socket
import sys
import time
from pathlib import Path


def replay(packets: list[dict], target: str, speed: float) -> None:
    """Replay a list of packets to the target host."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for i, pkt in enumerate(packets):
            data = bytes.fromhex(pkt["data_hex"])
            port = pkt.get("src_port", 50000)

            # Inter-packet delay (scaled by speed)
            if i > 0:
                delay = (pkt["timestamp"] - packets[i - 1]["timestamp"]) / speed
                if delay > 0:
                    time.sleep(delay)

            sock.sendto(data, (target, port))
            print(
                f"\r  Sent {i + 1}/{len(packets)}: {len(data)} bytes → {target}:{port}",
                end="", flush=True,
            )
        print()  # newline after progress
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Replay Pro DJ Link packet captures")
    parser.add_argument("capture_file", help="Path to JSON capture file")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playback speed multiplier (default 1.0 = real time)")
    parser.add_argument("--target", default="127.0.0.1",
                        help="Target host to send packets to (default 127.0.0.1)")
    parser.add_argument("--loop", action="store_true",
                        help="Loop replay forever")
    args = parser.parse_args()

    capture_path = Path(args.capture_file)
    if not capture_path.exists():
        print(f"Error: capture file not found: {capture_path}", file=sys.stderr)
        sys.exit(1)

    with open(capture_path) as f:
        packets = json.load(f)

    if not packets:
        print("Error: capture file is empty", file=sys.stderr)
        sys.exit(1)

    # Sort by timestamp
    packets.sort(key=lambda p: p.get("timestamp", 0))

    duration = packets[-1]["timestamp"] - packets[0]["timestamp"]
    print(f"Loaded {len(packets)} packets from {capture_path}")
    print(f"Duration: {duration:.1f}s (replay at {args.speed}x = {duration / args.speed:.1f}s)")
    print(f"Target: {args.target}")
    print()

    try:
        iteration = 0
        while True:
            iteration += 1
            if args.loop:
                print(f"Pass {iteration}:")
            replay(packets, args.target, args.speed)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
