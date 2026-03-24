"""Audio file streaming endpoint.

Serves audio files for browser playback during annotation.
Looks up the audio_path from a track's analysis JSON.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..layer1.storage import TrackStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audio", tags=["audio"])

_tracks_dir: Path | None = None

MIME_TYPES: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def init_audio_api(tracks_dir: Path) -> None:
    """Initialize the audio API with the tracks directory.

    Called during app startup.
    """
    global _tracks_dir
    _tracks_dir = tracks_dir
    logger.info("Audio API initialized: tracks=%s", tracks_dir)


def _get_store() -> TrackStore:
    if _tracks_dir is None:
        raise HTTPException(500, "Audio API not initialized")
    return TrackStore(_tracks_dir)


@router.get("/{fingerprint}")
async def stream_audio(fingerprint: str) -> FileResponse:
    """Stream an audio file for browser playback.

    Looks up the audio_path stored in the track's analysis JSON
    and returns the file with the appropriate content type.
    """
    store = _get_store()
    analysis = store.load_latest(fingerprint)
    if analysis is None:
        raise HTTPException(404, f"Track not found: {fingerprint[:16]}")

    audio_path = Path(analysis.audio_path)
    if not audio_path.exists():
        raise HTTPException(
            404,
            f"Audio file not found at: {analysis.audio_path}. "
            "The file may have been moved since analysis.",
        )

    mime = MIME_TYPES.get(audio_path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path=audio_path,
        media_type=mime,
        filename=audio_path.name,
    )
