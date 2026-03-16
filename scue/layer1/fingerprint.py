"""Audio file fingerprinting via SHA256.

The fingerprint is the primary key for all track analysis storage.
It is computed from the raw audio file bytes (not decoded audio samples),
so it is fast and deterministic.
"""

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Read in 64KB chunks for memory efficiency on large files
_CHUNK_SIZE = 65536


def compute_fingerprint(audio_path: str | Path) -> str:
    """Compute SHA256 fingerprint of an audio file.

    Args:
        audio_path: Path to the audio file.

    Returns:
        Hex-encoded SHA256 hash string.

    Raises:
        FileNotFoundError: If the audio file does not exist.
        OSError: If the file cannot be read.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)

    fingerprint = hasher.hexdigest()
    logger.debug("Fingerprint for %s: %s", path.name, fingerprint[:16])
    return fingerprint
