"""Filesystem browsing endpoint for the frontend folder picker."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])

# Default; overridden by init_filesystem_api() at startup
_audio_extensions: set[str] = {".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"}


def init_filesystem_api(audio_extensions: set[str] | None = None) -> None:
    """Initialize filesystem API with config-driven audio extensions."""
    global _audio_extensions
    if audio_extensions is not None:
        _audio_extensions = audio_extensions


@router.get("/browse")
async def browse(path: str = Query(default="")) -> dict:
    """List directory contents for the folder browser UI.

    Returns directories (for navigation) and audio files.
    Defaults to the user's home directory if no path is given.
    """
    target = Path(path) if path else Path.home()

    if not target.exists():
        raise HTTPException(404, f"Path not found: {path}")
    if not target.is_dir():
        raise HTTPException(400, f"Not a directory: {path}")

    entries = []
    try:
        for item in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": True,
                })
            elif item.is_file() and item.suffix.lower() in _audio_extensions:
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": False,
                })
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {path}")

    # Directories first, then files
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

    parent = str(target.parent) if target.parent != target else None

    return {
        "path": str(target),
        "parent": parent,
        "entries": entries,
    }
