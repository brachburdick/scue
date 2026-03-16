"""Mock bridge — replays JSON fixture files over WebSocket for testing.

Starts a WebSocket server on localhost:17400 (configurable) and replays
bridge messages from a JSON fixture file with realistic timing.

Usage:
    python tools/mock_bridge.py
    python tools/mock_bridge.py --fixture tests/fixtures/bridge/playback_session.json
    python tools/mock_bridge.py --speed 2.0 --port 17400
    python tools/mock_bridge.py --loop
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import websockets
from websockets.asyncio.server import ServerConnection

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [mock-bridge] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "bridge"
DEFAULT_PORT = 17400

# Connected clients
_clients: set[ServerConnection] = set()


def load_all_fixtures(fixture_dir: Path) -> list[dict]:
    """Load and merge all fixture files, sorted by timestamp."""
    all_messages: list[dict] = []
    for f in sorted(fixture_dir.glob("*.json")):
        with open(f) as fh:
            messages = json.load(fh)
            logger.info("Loaded %d messages from %s", len(messages), f.name)
            all_messages.extend(messages)

    all_messages.sort(key=lambda m: m.get("timestamp", 0))
    return all_messages


def load_fixture(path: Path) -> list[dict]:
    """Load a single fixture file."""
    with open(path) as f:
        messages = json.load(f)
    logger.info("Loaded %d messages from %s", len(messages), path.name)
    return messages


async def broadcast(message: dict) -> None:
    """Send a message to all connected clients."""
    global _clients
    data = json.dumps(message)
    disconnected = set()
    for client in _clients:
        try:
            await client.send(data)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)
    _clients -= disconnected


async def replay_messages(
    messages: list[dict],
    speed: float = 1.0,
    loop: bool = False,
) -> None:
    """Replay messages with timing based on timestamp deltas."""
    while True:
        if not messages:
            logger.warning("No messages to replay")
            return

        logger.info("Starting replay of %d messages (speed=%.1fx)", len(messages), speed)
        base_time = messages[0].get("timestamp", 0)

        for i, msg in enumerate(messages):
            # Calculate delay from previous message
            if i > 0:
                prev_ts = messages[i - 1].get("timestamp", 0)
                curr_ts = msg.get("timestamp", 0)
                delay = (curr_ts - prev_ts) / speed
                if delay > 0:
                    await asyncio.sleep(delay)

            # Wait for at least one client
            if not _clients:
                logger.info("Waiting for client connection...")
                while not _clients:
                    await asyncio.sleep(0.1)

            await broadcast(msg)
            msg_type = msg.get("type", "?")
            player = msg.get("player_number", "-")
            logger.info(
                "  [%d/%d] %s player=%s",
                i + 1, len(messages), msg_type, player,
            )

        logger.info("Replay complete")

        if not loop:
            break

        logger.info("Looping — restarting replay")
        await asyncio.sleep(1.0)


async def ws_handler(websocket: ServerConnection) -> None:
    """Handle a WebSocket client connection."""
    _clients.add(websocket)
    logger.info("Client connected (%d total)", len(_clients))
    try:
        async for _ in websocket:
            pass  # We don't expect messages from clients
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        _clients.discard(websocket)
        logger.info("Client disconnected (%d total)", len(_clients))


async def main(args: argparse.Namespace) -> None:
    if args.fixture:
        messages = load_fixture(Path(args.fixture))
    else:
        messages = load_all_fixtures(DEFAULT_FIXTURE_DIR)

    logger.info("Starting mock bridge on ws://localhost:%d", args.port)

    async with websockets.serve(ws_handler, "localhost", args.port):
        logger.info("Mock bridge ready — waiting for connections")
        await replay_messages(messages, speed=args.speed, loop=args.loop)

        # Keep server alive after replay
        if not args.loop:
            logger.info("Replay done — server staying alive (Ctrl+C to stop)")
            await asyncio.Future()  # run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock beat-link bridge for testing")
    parser.add_argument(
        "--fixture",
        type=str,
        help="Path to a specific fixture file (default: all fixtures merged)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"WebSocket port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier (default: 1.0)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Loop replay continuously",
    )

    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("Mock bridge stopped")
