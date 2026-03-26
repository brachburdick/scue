"""Local rekordbox library scanner — batch-ingest ANLZ files without hardware.

Rekordbox stores identical ANLZ files locally at:
  ~/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/

This module scans that directory, parses each .DAT file using the two-tier
ANLZ strategy (same as usb_scanner), and matches tracks to existing SCUE
analyses via file path stem.

Persistence uses composite key source_player="local", source_slot="library"
per ADR-015 pattern.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .anlz_parser import AnlzParseError, parse_anlz_beatgrid, parse_anlz_cues, parse_anlz_file_path, parse_anlz_phrases
from .storage import TrackCache, TrackStore
from .usb_scanner import MatchedTrack, ScanResult, UsbTrack, match_usb_tracks

logger = logging.getLogger(__name__)


# ── Known rekordbox ANLZ paths ─────────────────────────────────────────

REKORDBOX_ANLZ_PATHS = [
    Path.home() / "Library" / "Pioneer" / "rekordbox" / "share" / "PIONEER" / "USBANLZ",
]


# ── Data types ─────────────────────────────────────────────────────────

@dataclass
class LocalTrack:
    """A single track parsed from a local rekordbox ANLZ .DAT file."""
    anlz_path: str              # relative path within USBANLZ dir
    file_path: str              # from PPTH tag (original audio file path)
    beatgrid: list[dict] = field(default_factory=list)
    phrases: list[dict] = field(default_factory=list)
    cue_points: list[dict] = field(default_factory=list)
    memory_points: list[dict] = field(default_factory=list)
    hot_cues: list[dict] = field(default_factory=list)
    waveform_pwv5: bytes = b""
    waveform_pwv3: bytes = b""
    waveform_pwv7: bytes = b""


# ── Core functions ─────────────────────────────────────────────────────

def detect_library() -> dict | None:
    """Check known paths for a local rekordbox ANLZ directory.

    Returns:
        {"path": str, "dat_count": int} if found, None otherwise.
    """
    for candidate in REKORDBOX_ANLZ_PATHS:
        if candidate.exists() and candidate.is_dir():
            dat_count = sum(1 for _ in candidate.rglob("*.DAT"))
            logger.info("Detected rekordbox library at %s (%d .DAT files)", candidate, dat_count)
            return {"path": str(candidate), "dat_count": dat_count}

    logger.debug("No local rekordbox library found at known paths")
    return None


def scan_local_library(
    anlz_dir: Path,
    progress_cb: callable | None = None,
) -> list[LocalTrack]:
    """Walk all .DAT files in anlz_dir, parse each, return list of LocalTrack.

    Args:
        anlz_dir: Root directory containing ANLZ files (recursively).
        progress_cb: Optional callback(current, total) for progress reporting.

    Returns:
        List of successfully parsed LocalTrack objects.
    """
    dat_files = sorted(anlz_dir.rglob("*.DAT"))
    total = len(dat_files)
    logger.info("Scanning %d .DAT files in %s", total, anlz_dir)

    tracks: list[LocalTrack] = []
    skipped = 0

    for i, dat_path in enumerate(dat_files):
        if progress_cb is not None:
            progress_cb(i + 1, total)

        try:
            track = _parse_local_dat(dat_path, anlz_dir)
            if track is not None:
                tracks.append(track)
            else:
                skipped += 1
        except Exception:
            logger.debug("Skipping unparseable file: %s", dat_path, exc_info=True)
            skipped += 1

    logger.info(
        "Local library scan complete: %d tracks parsed, %d skipped, %d total files",
        len(tracks), skipped, total,
    )
    return tracks


def match_local_tracks(
    tracks: list[LocalTrack],
    cache: TrackCache,
    store: TrackStore,
) -> ScanResult:
    """Convert LocalTrack list to UsbTrack and delegate to usb_scanner matching.

    Uses source_player="local", source_slot="library" for cache persistence.

    Args:
        tracks: Parsed local tracks.
        cache: SQLite cache for lookups.
        store: JSON store (passed through to match_usb_tracks).

    Returns:
        ScanResult with matched/unmatched tracks.
    """
    usb_tracks = [_local_to_usb(t) for t in tracks]
    result = match_usb_tracks(usb_tracks, cache, store)
    result.usb_path = "local:library"

    # Persist matched tracks under local namespace
    linked = _apply_local_results(result, cache)
    logger.info("Local library: %d matched, %d unmatched, %d linked", len(result.matched), len(result.unmatched), linked)

    return result


# ── Internal helpers ───────────────────────────────────────────────────

def _parse_local_dat(dat_path: Path, anlz_dir: Path) -> LocalTrack | None:
    """Parse a single .DAT file into a LocalTrack.

    Returns None if the file has no PPTH tag (can't identify the audio file).
    """
    rel_path = str(dat_path.relative_to(anlz_dir))

    # Step 1: Extract file path from PPTH tag
    try:
        file_path = parse_anlz_file_path(dat_path)
    except AnlzParseError:
        logger.debug("No valid PPTH in %s", rel_path)
        return None

    if not file_path:
        logger.debug("Empty PPTH in %s", rel_path)
        return None

    track = LocalTrack(anlz_path=rel_path, file_path=file_path)

    # Step 2: Extract beatgrid
    try:
        track.beatgrid = parse_anlz_beatgrid(dat_path)
    except AnlzParseError as e:
        logger.debug("Beatgrid parse failed for %s: %s", rel_path, e)

    # Step 3: Extract cues
    try:
        hot, mem = parse_anlz_cues(dat_path)
        track.hot_cues = hot
        track.memory_points = mem
    except AnlzParseError as e:
        logger.debug("Cue parse failed for %s: %s", rel_path, e)

    # Step 4: Look for .EXT and .2EX siblings — extract phrases
    ext_path = dat_path.with_suffix(".EXT")
    if ext_path.exists():
        try:
            track.phrases = parse_anlz_phrases(ext_path)
        except AnlzParseError as e:
            logger.debug("Phrase parse failed for %s: %s", ext_path.name, e)

    ext2_path = dat_path.with_suffix(".2EX")
    if ext2_path.exists():
        # .2EX may also contain phrases (newer format)
        if not track.phrases:
            try:
                track.phrases = parse_anlz_phrases(ext2_path)
            except AnlzParseError as e:
                logger.debug("Phrase parse failed for %s: %s", ext2_path.name, e)

    # Step 5: Waveforms — skip (pyrekordbox not installed per constraints)

    return track


def _local_to_usb(t: LocalTrack) -> UsbTrack:
    """Convert a LocalTrack to UsbTrack for matching reuse."""
    return UsbTrack(
        rekordbox_id=0,  # not available from ANLZ files alone
        title=Path(t.file_path).stem if t.file_path else "",
        artist="",
        bpm=t.beatgrid[0]["bpm"] if t.beatgrid else 0.0,
        key="",
        file_path=t.file_path,
        anlz_path=t.anlz_path,
        beatgrid=t.beatgrid,
        cue_points=t.cue_points,
        memory_points=t.memory_points,
        hot_cues=t.hot_cues,
        waveform_pwv5=t.waveform_pwv5,
        waveform_pwv3=t.waveform_pwv3,
        waveform_pwv7=t.waveform_pwv7,
    )


def _apply_local_results(result: ScanResult, cache: TrackCache) -> int:
    """Persist matched local tracks to cache under local namespace."""
    linked = 0
    for match in result.matched:
        t = match.usb_track
        # Use a stable ID derived from file path hash since rekordbox_id=0
        stable_id = abs(hash(t.file_path)) % (2**31)

        cache.link_rekordbox_id(
            stable_id, match.fingerprint,
            source_player="local", source_slot="library",
        )
        cache.store_pioneer_metadata(stable_id, {
            "title": t.title,
            "artist": t.artist,
            "bpm": t.bpm,
            "key_name": t.key,
            "beatgrid": t.beatgrid,
            "cue_points": t.cue_points,
            "memory_points": t.memory_points,
            "hot_cues": t.hot_cues,
            "file_path": t.file_path,
            "scan_timestamp": result.scan_timestamp,
            "waveform_pwv5": t.waveform_pwv5,
            "waveform_pwv3": t.waveform_pwv3,
            "waveform_pwv7": t.waveform_pwv7,
        }, source_player="local", source_slot="library")

        linked += 1

    return linked
