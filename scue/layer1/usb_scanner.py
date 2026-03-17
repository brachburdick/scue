"""USB scanner — reads Pioneer exportLibrary.db via rbox and links tracks to SCUE analyses.

Pre-set preparation step: scan a USB while it's plugged into the computer,
build rekordbox_id → fingerprint mappings, and cache Pioneer metadata (beatgrid,
key, cue points) so enrichment works during the live set.

Per ADR-012: The bridge provides real-time data only. Track metadata comes from
the USB via rbox for DLP hardware (XDJ-AZ, Opus Quad, CDJ-3000X, OMNIS-DUO).

Per ADR-013: ANLZ file parsing uses a two-tier strategy:
  Tier 1: pyrekordbox (pure Python, full ANLZ support including phrases)
  Tier 2: custom anlz_parser (zero-dep fallback, beat grid + cues only)
Database reading (exportLibrary.db) remains via rbox OneLibrary.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .storage import TrackCache, TrackStore

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────

@dataclass
class UsbTrack:
    """A single track read from a Pioneer USB's exportLibrary.db."""
    rekordbox_id: int
    title: str
    artist: str
    bpm: float
    key: str
    file_path: str
    anlz_path: str = ""
    beatgrid: list[dict] = field(default_factory=list)
    cue_points: list[dict] = field(default_factory=list)
    memory_points: list[dict] = field(default_factory=list)
    hot_cues: list[dict] = field(default_factory=list)


@dataclass
class MatchedTrack:
    """A USB track successfully matched to an existing SCUE analysis."""
    usb_track: UsbTrack
    fingerprint: str
    match_method: str  # "path_stem" | "title_artist"


@dataclass
class ScanResult:
    """Result of scanning a USB and matching tracks."""
    usb_path: str
    total_tracks: int
    matched: list[MatchedTrack] = field(default_factory=list)
    unmatched: list[UsbTrack] = field(default_factory=list)
    already_linked: int = 0
    scan_timestamp: float = 0.0


# ── Core functions ────────────────────────────────────────────────────────

def read_usb_library(
    db_path: Path,
    anlz_dir: Path | None = None,
) -> list[UsbTrack]:
    """Read all tracks from a Pioneer USB's exportLibrary.db via rbox.

    Args:
        db_path: Path to exportLibrary.db.
        anlz_dir: Path to PIONEER/USBANLZ directory (for beatgrids/cues).

    Returns:
        List of UsbTrack objects.

    Raises:
        ImportError: If rbox is not installed.
        FileNotFoundError: If db_path doesn't exist.
    """
    try:
        from rbox import OneLibrary
    except ImportError:
        raise ImportError(
            "rbox is required for USB scanning. Install it with: pip install rbox"
        )

    if not db_path.exists():
        raise FileNotFoundError(f"exportLibrary.db not found: {db_path}")

    db = OneLibrary(str(db_path))
    contents = db.get_contents()
    logger.info("Read %d tracks from %s", len(contents), db_path)

    tracks: list[UsbTrack] = []
    for content in contents:
        # Resolve artist name
        artist_name = ""
        if content.artist_id is not None:
            artist = db.get_artist_by_id(content.artist_id)
            if artist and hasattr(artist, "name"):
                artist_name = artist.name

        # Resolve key name
        key_name = ""
        if content.key_id is not None:
            key = db.get_key_by_id(content.key_id)
            if key and hasattr(key, "name"):
                key_name = key.name

        # BPM is stored as bpmx100
        bpm = content.bpmx100 / 100.0 if content.bpmx100 else 0.0

        anlz_path = content.analysis_data_file_path or ""

        track = UsbTrack(
            rekordbox_id=content.id,
            title=content.title or "",
            artist=artist_name,
            bpm=bpm,
            key=key_name,
            file_path=content.path or "",
            anlz_path=anlz_path,
        )

        # Read ANLZ data if directory provided and path available.
        # Uses two-tier strategy: pyrekordbox (primary) → custom parser (fallback).
        # Both are pure Python — no Rust panic risk (ADR-013).
        if anlz_dir and anlz_path:
            _read_anlz_data(track, anlz_dir, anlz_path)

        tracks.append(track)

    return tracks


def _read_anlz_data(track: UsbTrack, anlz_dir: Path, anlz_path: str) -> None:
    """Read beatgrid and cue points from ANLZ files for a track.

    Two-tier strategy (ADR-013):
      Tier 1: pyrekordbox — full ANLZ support, pure Python, safe exceptions.
      Tier 2: custom anlz_parser — zero-dep fallback, beat grid + cues only.

    If both fail, the track's ANLZ fields stay empty. Enrichment will use
    librosa-derived data instead.

    Args:
        track: UsbTrack to populate with ANLZ data.
        anlz_dir: Root USBANLZ directory on the USB.
        anlz_path: Relative path to the ANLZ file (from exportLibrary.db).
    """
    # anlz_path is like "/PIONEER/USBANLZ/P019/0002DB9B/ANLZ0000.DAT"
    # Strip leading /PIONEER/USBANLZ/ to get the relative portion
    rel = anlz_path
    for prefix in ["/PIONEER/USBANLZ/", "PIONEER/USBANLZ/"]:
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break

    dat_path = anlz_dir / rel
    if not dat_path.exists():
        return

    # Tier 1: pyrekordbox
    if _try_pyrekordbox(track, dat_path):
        return

    # Tier 2: custom minimal parser
    _try_custom_parser(track, dat_path)


def _try_pyrekordbox(track: UsbTrack, dat_path: Path) -> bool:
    """Attempt to parse ANLZ data with pyrekordbox.

    Returns True if parsing succeeded (even if some sections were empty).
    Returns False if pyrekordbox is unavailable or threw an exception.
    """
    try:
        from pyrekordbox.anlz import AnlzFile
    except ImportError:
        logger.debug("pyrekordbox not installed — skipping Tier 1 ANLZ parsing")
        return False

    try:
        anlz = AnlzFile.parse_file(dat_path)
    except Exception:
        logger.exception(
            "pyrekordbox failed to parse %s for track %d",
            dat_path.name, track.rekordbox_id,
        )
        return False

    # Beat grid — PQTZ tag
    # Use get_tag() (returns PQTZAnlzTag with .content.entries),
    # NOT get() (returns a tuple of numpy arrays).
    try:
        beat_grid_tag = anlz.get_tag("beat_grid")
        if beat_grid_tag is not None:
            track.beatgrid = [
                {
                    "beat_number": entry.beat,
                    "time_ms": float(entry.time),
                    # pyrekordbox .tempo is BPM×100 (e.g. 12800 = 128.00 BPM)
                    "bpm": entry.tempo / 100.0 if entry.tempo else 0.0,
                }
                for entry in beat_grid_tag.content.entries
            ]
    except Exception as e:
        logger.debug("pyrekordbox beatgrid read failed for track %d: %s", track.rekordbox_id, e)

    # Cue lists — PCOB tags (one for hot cues, one for memory cues)
    # pyrekordbox cue_type is a string: "hotcue" or "memory"
    # Entry .type is a string: "single" or "loop"
    try:
        for pcob_tag in anlz.getall_tags("PCOB"):
            cue_type_str = str(pcob_tag.content.cue_type)  # "hotcue" or "memory"
            is_hot = cue_type_str == "hotcue"
            for entry in pcob_tag.content.entries:
                type_str = str(entry.type)  # "single" or "loop"
                cue_type_int = 2 if type_str == "loop" else 1
                cue = {
                    "slot": entry.hot_cue if is_hot else 0,
                    "time_ms": float(entry.time),
                    "type": cue_type_int,
                }
                if is_hot:
                    track.hot_cues.append(cue)
                else:
                    track.memory_points.append(cue)
    except Exception as e:
        logger.debug("pyrekordbox cue read failed for track %d: %s", track.rekordbox_id, e)

    logger.debug(
        "pyrekordbox parsed track %d: %d beats, %d hot cues, %d memory cues",
        track.rekordbox_id, len(track.beatgrid),
        len(track.hot_cues), len(track.memory_points),
    )
    return True


def _try_custom_parser(track: UsbTrack, dat_path: Path) -> bool:
    """Attempt to parse ANLZ data with the custom minimal parser (Tier 2).

    Returns True if parsing succeeded, False otherwise.
    """
    from .anlz_parser import AnlzParseError, parse_anlz_beatgrid, parse_anlz_cues

    try:
        track.beatgrid = parse_anlz_beatgrid(dat_path)
    except AnlzParseError as e:
        logger.warning(
            "Custom ANLZ parser failed for beatgrid, track %d: %s",
            track.rekordbox_id, e,
        )
        return False

    try:
        hot, mem = parse_anlz_cues(dat_path)
        track.hot_cues = hot
        track.memory_points = mem
    except AnlzParseError as e:
        logger.debug(
            "Custom ANLZ parser failed for cues, track %d: %s",
            track.rekordbox_id, e,
        )

    logger.debug(
        "Custom parser parsed track %d: %d beats, %d hot cues, %d memory cues",
        track.rekordbox_id, len(track.beatgrid),
        len(track.hot_cues), len(track.memory_points),
    )
    return True


def match_usb_tracks(
    usb_tracks: list[UsbTrack],
    cache: TrackCache,
    store: TrackStore,
) -> ScanResult:
    """Match USB tracks against existing SCUE analyses.

    Uses two-pass matching:
    1. File path stem match (highest confidence).
    2. Normalized title+artist match (fallback).

    Args:
        usb_tracks: Tracks read from USB.
        cache: SQLite cache for lookups.
        store: JSON store (not directly read, cache is sufficient).

    Returns:
        ScanResult with matched and unmatched tracks.
    """
    result = ScanResult(
        usb_path="",
        total_tracks=len(usb_tracks),
        scan_timestamp=time.time(),
    )

    # Load all existing analyses for matching
    analyses = cache.list_tracks(limit=10000)

    # Build lookup indices
    stem_index: dict[str, str] = {}  # filename_stem → fingerprint
    title_artist_index: dict[str, str] = {}  # "title|artist" → fingerprint

    for a in analyses:
        fp = a["fingerprint"]
        audio_path = a.get("audio_path", "")
        if audio_path:
            stem = Path(audio_path).stem.lower()
            stem_index[stem] = fp

        title = _normalize(a.get("title", ""))
        artist = _normalize(a.get("artist", ""))
        if title:
            key = f"{title}|{artist}"
            title_artist_index[key] = fp

    # Match each USB track
    for usb_track in usb_tracks:
        # Skip if already linked
        existing = cache.lookup_fingerprint(usb_track.rekordbox_id)
        if existing is not None:
            result.already_linked += 1
            continue

        # Pass 1: file path stem match (exact or prefix — Pioneer truncates long names)
        usb_stem = Path(usb_track.file_path).stem.lower() if usb_track.file_path else ""
        if usb_stem:
            # Exact match first
            if usb_stem in stem_index:
                result.matched.append(MatchedTrack(
                    usb_track=usb_track,
                    fingerprint=stem_index[usb_stem],
                    match_method="path_stem",
                ))
                continue

            # Prefix match: Pioneer truncates filenames on export
            # Check if any analysis stem starts with the USB stem or vice versa
            matched_fp = _prefix_match(usb_stem, stem_index)
            if matched_fp:
                result.matched.append(MatchedTrack(
                    usb_track=usb_track,
                    fingerprint=matched_fp,
                    match_method="path_stem",
                ))
                continue

        # Pass 2: normalized title+artist match
        usb_title = _normalize(usb_track.title)
        usb_artist = _normalize(usb_track.artist)
        if usb_title:
            key = f"{usb_title}|{usb_artist}"
            if key in title_artist_index:
                result.matched.append(MatchedTrack(
                    usb_track=usb_track,
                    fingerprint=title_artist_index[key],
                    match_method="title_artist",
                ))
                continue

        # No match
        result.unmatched.append(usb_track)

    logger.info(
        "USB scan: %d total, %d matched, %d unmatched, %d already linked",
        result.total_tracks, len(result.matched),
        len(result.unmatched), result.already_linked,
    )
    return result


def apply_scan_results(result: ScanResult, cache: TrackCache) -> int:
    """Persist matched track links and Pioneer metadata to the cache.

    For each matched track:
    - Links rekordbox_id → fingerprint in track_ids table.
    - Stores Pioneer metadata (beatgrid, cues, key, BPM) in pioneer_metadata table.

    Args:
        result: ScanResult from match_usb_tracks().
        cache: TrackCache for persistence.

    Returns:
        Number of new links created.
    """
    linked = 0
    for match in result.matched:
        t = match.usb_track

        # Link rekordbox_id → fingerprint
        cache.link_rekordbox_id(t.rekordbox_id, match.fingerprint)

        # Cache Pioneer metadata for enrichment
        cache.store_pioneer_metadata(t.rekordbox_id, {
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
        })

        linked += 1
        logger.debug(
            "Linked: rb_id=%d → fp=%s (%s) — %s",
            t.rekordbox_id, match.fingerprint[:12], match.match_method, t.title,
        )

    logger.info("Applied %d new links from USB scan", linked)
    return linked


# ── Helpers ───────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Normalize a string for fuzzy matching: lowercase, strip, collapse whitespace."""
    return " ".join(s.strip().lower().split())


def _prefix_match(usb_stem: str, stem_index: dict[str, str], min_len: int = 20) -> str | None:
    """Find a fingerprint where the USB stem is a prefix of (or prefixed by) a stored stem.

    Pioneer hardware truncates long filenames on USB export. This catches those
    cases by matching prefixes when both stems share a common start of at least
    min_len characters.

    Returns the fingerprint if exactly one match is found, else None (ambiguous).
    """
    if len(usb_stem) < min_len:
        return None

    matches: list[str] = []
    for stored_stem, fp in stem_index.items():
        if stored_stem.startswith(usb_stem) or usb_stem.startswith(stored_stem):
            common = min(len(usb_stem), len(stored_stem))
            if common >= min_len:
                matches.append(fp)

    return matches[0] if len(matches) == 1 else None
