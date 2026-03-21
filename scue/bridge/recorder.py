"""Bridge message recorder — captures live bridge messages to fixture files.

Records BridgeMessage objects from the listen loop to JSONL files for replay
via tools/mock_bridge.py. Start/stop via the /api/bridge/record endpoints.

Output format matches existing fixtures in tests/fixtures/bridge/:
one JSON object per line with {type, timestamp, player_number, payload}.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from .messages import BridgeMessage

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "bridge"


class MessageRecorder:
    """Records bridge messages to a JSONL file."""

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = output_dir
        self._file = None
        self._path: Path | None = None
        self._count = 0
        self._start_time: float | None = None

    @property
    def is_recording(self) -> bool:
        return self._file is not None

    @property
    def message_count(self) -> int:
        return self._count

    @property
    def recording_path(self) -> str | None:
        return str(self._path) if self._path else None

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def start(self, name: str | None = None) -> str:
        """Start recording. Returns the output file path."""
        if self.is_recording:
            raise RuntimeError("Already recording")

        self._output_dir.mkdir(parents=True, exist_ok=True)

        if name is None:
            name = f"recorded-{time.strftime('%Y%m%d-%H%M%S')}"
        # Sanitize
        name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)

        self._path = self._output_dir / f"{name}.jsonl"
        self._file = open(self._path, "w")
        self._count = 0
        self._start_time = time.time()

        logger.info("Recording started: %s", self._path)
        return str(self._path)

    def stop(self) -> dict:
        """Stop recording. Returns summary."""
        if not self.is_recording:
            raise RuntimeError("Not recording")

        elapsed = self.elapsed_seconds
        self._file.close()
        self._file = None

        summary = {
            "path": str(self._path),
            "messages": self._count,
            "duration_seconds": round(elapsed, 1),
        }

        logger.info(
            "Recording stopped: %d messages in %.1fs → %s",
            self._count, elapsed, self._path,
        )

        self._path = None
        self._start_time = None
        self._count = 0
        return summary

    def record(self, msg: BridgeMessage) -> None:
        """Record a single message. Called from the bridge listen loop."""
        if self._file is None:
            return

        line = json.dumps({
            "type": msg.type,
            "timestamp": msg.timestamp,
            "player_number": msg.player_number,
            "payload": msg.payload,
        })
        self._file.write(line + "\n")
        self._file.flush()
        self._count += 1
