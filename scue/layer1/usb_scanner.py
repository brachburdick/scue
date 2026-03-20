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

Dual-namespace scanning: reads both exportLibrary.db (DLP) and export.pdb
(DeviceSQL) when both exist, linking tracks across namespaces by file path.
This supports mixed hardware setups (e.g. XDJ-AZ + CDJ-3000 sharing the same USB).
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
    # Pioneer ANLZ waveform data (raw bytes, base64-encoded for storage)
    waveform_pwv5: bytes = b""  # Color detail (3-bit RGB + 5-bit height, 2 bytes/entry)
    waveform_pwv3: bytes = b""  # Monochrome detail (5-bit height + 3-bit intensity, 1 byte/entry)
    waveform_pwv7: bytes = b""  # 3-band detail (mid/high/low, 3 bytes/entry, CDJ-3000+)


@dataclass
class PdbTrack:
    """A single track read from a Pioneer USB's export.pdb (DeviceSQL format)."""
    devicesql_id: int
    title: str
    file_path: str
    bpm: float = 0.0
    artist_id: int = 0


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


def read_pdb_library(pdb_path: Path) -> list[PdbTrack]:
    """Read all tracks from a Pioneer USB's export.pdb (DeviceSQL format).

    Uses pyrekordbox's PDB support for parsing.

    Args:
        pdb_path: Path to export.pdb.

    Returns:
        List of PdbTrack objects.
    """
    if not pdb_path.exists():
        logger.debug("export.pdb not found at %s — skipping DeviceSQL scan", pdb_path)
        return []

    try:
        from pyrekordbox import RekordboxPdb
    except ImportError:
        logger.warning("pyrekordbox not installed — cannot read export.pdb")
        return []

    try:
        pdb = RekordboxPdb(pdb_path)
    except Exception:
        logger.exception("Failed to parse export.pdb at %s", pdb_path)
        return []

    tracks: list[PdbTrack] = []
    try:
        for row in pdb.get_tracks():
            track_id = getattr(row, "id", 0)
            title = getattr(row, "title", "") or ""
            file_path = getattr(row, "file_path", "") or ""
            bpm_raw = getattr(row, "tempo", 0)
            bpm = bpm_raw / 100.0 if bpm_raw else 0.0
            artist_id = getattr(row, "artist_id", 0) or 0

            tracks.append(PdbTrack(
                devicesql_id=track_id,
                title=title,
                file_path=file_path,
                bpm=bpm,
                artist_id=artist_id,
            ))
    except Exception:
        logger.exception("Error reading tracks from export.pdb")
        return []

    logger.info("Read %d tracks from %s (DeviceSQL)", len(tracks), pdb_path)
    return tracks


def _normalize_pioneer_path(path: str) -> str:
    """Normalize a Pioneer file path for cross-namespace matching.

    Both DLP (exportLibrary.db) and DeviceSQL (export.pdb) store file paths
    relative to the USB root, but may have minor differences in separators
    or casing. Normalize to lowercase with forward slashes.
    """
    return path.replace("\\", "/").lower().strip()


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
        pass  # Continue to read waveforms from .EXT/.2EX even if .DAT succeeded
    else:
        # Tier 2: custom minimal parser (beatgrid/cues only, no waveform support)
        _try_custom_parser(track, dat_path)

    # Read waveform data from .EXT and .2EX files (separate from .DAT)
    _try_read_waveforms(track, dat_path)


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


def _try_read_waveforms(track: UsbTrack, dat_path: Path) -> None:
    """Read waveform data from .EXT and .2EX ANLZ files.

    PWV5 (color detail) and PWV3 (monochrome detail) are in .EXT files.
    PWV7 (3-band detail) is in .2EX files (CDJ-3000+ only).

    Stores raw bytes on the UsbTrack. Decoding happens at API response time.
    """
    try:
        from pyrekordbox.anlz import AnlzFile
    except ImportError:
        return  # pyrekordbox not available

    # .EXT file: PWV5 (color) and PWV3 (monochrome)
    ext_path = dat_path.with_suffix(".EXT")
    if ext_path.exists():
        try:
            ext = AnlzFile.parse_file(ext_path)

            # PWV5: color detail waveform (primary)
            try:
                pwv5_tag = ext.get_tag("PWV5")
                if pwv5_tag is not None:
                    track.waveform_pwv5 = bytes(pwv5_tag.content.entries)
                    logger.debug(
                        "Read PWV5 for track %d: %d bytes",
                        track.rekordbox_id, len(track.waveform_pwv5),
                    )
            except Exception as e:
                logger.debug("PWV5 read failed for track %d: %s", track.rekordbox_id, e)

            # PWV3: monochrome detail waveform (fallback)
            try:
                pwv3_tag = ext.get_tag("PWV3")
                if pwv3_tag is not None:
                    track.waveform_pwv3 = bytes(pwv3_tag.content.entries)
                    logger.debug(
                        "Read PWV3 for track %d: %d bytes",
                        track.rekordbox_id, len(track.waveform_pwv3),
                    )
            except Exception as e:
                logger.debug("PWV3 read failed for track %d: %s", track.rekordbox_id, e)

        except Exception:
            logger.debug("Failed to parse .EXT file for track %d", track.rekordbox_id)

    # .2EX file: PWV7 (3-band detail, CDJ-3000+ only)
    ext2_path = dat_path.with_suffix(".2EX")
    if ext2_path.exists():
        try:
            ext2 = AnlzFile.parse_file(ext2_path)
            try:
                pwv7_tag = ext2.get_tag("PWV7")
                if pwv7_tag is not None:
                    track.waveform_pwv7 = bytes(pwv7_tag.content.entries)
                    logger.debug(
                        "Read PWV7 for track %d: %d bytes",
                        track.rekordbox_id, len(track.waveform_pwv7),
                    )
            except Exception as e:
                logger.debug("PWV7 read failed for track %d: %s", track.rekordbox_id, e)
        except Exception:
            logger.debug("Failed to parse .2EX file for track %d", track.rekordbox_id)


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
        # Skip if already linked (check DLP namespace — primary for DLP USBs)
        existing = cache.lookup_fingerprint(
            usb_track.rekordbox_id, source_player="dlp", source_slot="usb",
        )
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


def apply_scan_results(
    result: ScanResult,
    cache: TrackCache,
    pdb_tracks: list[PdbTrack] | None = None,
) -> int:
    """Persist matched track links and Pioneer metadata to the cache.

    For each matched track:
    - Links DLP rekordbox_id → fingerprint (source_player="dlp").
    - Stores Pioneer metadata in the DLP namespace.
    - If pdb_tracks provided, also links DeviceSQL ID → same fingerprint
      (source_player="devicesql") by matching file paths across namespaces.

    Args:
        result: ScanResult from match_usb_tracks().
        cache: TrackCache for persistence.
        pdb_tracks: Optional list of PdbTrack from read_pdb_library() for
                    dual-namespace linking.

    Returns:
        Number of new links created (DLP + DeviceSQL).
    """
    # Build DeviceSQL path→track index for cross-namespace matching
    pdb_by_path: dict[str, PdbTrack] = {}
    if pdb_tracks:
        for pt in pdb_tracks:
            if pt.file_path:
                pdb_by_path[_normalize_pioneer_path(pt.file_path)] = pt

    linked = 0
    for match in result.matched:
        t = match.usb_track

        # Link DLP rekordbox_id → fingerprint
        cache.link_rekordbox_id(
            t.rekordbox_id, match.fingerprint,
            source_player="dlp", source_slot="usb",
        )

        # Cache Pioneer metadata for enrichment (DLP namespace)
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
            "waveform_pwv5": t.waveform_pwv5,
            "waveform_pwv3": t.waveform_pwv3,
            "waveform_pwv7": t.waveform_pwv7,
        }, source_player="dlp", source_slot="usb")

        linked += 1
        logger.debug(
            "Linked DLP: rb_id=%d → fp=%s (%s) — %s",
            t.rekordbox_id, match.fingerprint[:12], match.match_method, t.title,
        )

        # Cross-namespace link: find DeviceSQL track with same file path
        if pdb_by_path and t.file_path:
            norm_path = _normalize_pioneer_path(t.file_path)
            pdb_track = pdb_by_path.get(norm_path)
            if pdb_track is not None:
                cache.link_rekordbox_id(
                    pdb_track.devicesql_id, match.fingerprint,
                    source_player="devicesql", source_slot="usb",
                )
                # Also store metadata under DeviceSQL namespace
                cache.store_pioneer_metadata(pdb_track.devicesql_id, {
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
                }, source_player="devicesql", source_slot="usb")
                linked += 1
                logger.debug(
                    "Linked DeviceSQL: ds_id=%d → fp=%s (cross-namespace via file path)",
                    pdb_track.devicesql_id, match.fingerprint[:12],
                )

    logger.info("Applied %d new links from USB scan", linked)
    return linked


def apply_pdb_only_scan(
    pdb_tracks: list[PdbTrack],
    cache: TrackCache,
    store: TrackStore,
) -> int:
    """For legacy-only USBs (no exportLibrary.db), match PDB tracks and link them.

    Uses the same matching logic as match_usb_tracks but for DeviceSQL tracks.

    Args:
        pdb_tracks: Tracks read from export.pdb.
        cache: SQLite cache for lookups.
        store: JSON store (not directly read, cache is sufficient).

    Returns:
        Number of new links created.
    """
    # Convert PdbTrack to UsbTrack for reuse of match_usb_tracks
    usb_tracks = [
        UsbTrack(
            rekordbox_id=pt.devicesql_id,
            title=pt.title,
            artist="",  # PDB tracks don't carry resolved artist name
            bpm=pt.bpm,
            key="",
            file_path=pt.file_path,
        )
        for pt in pdb_tracks
    ]

    result = match_usb_tracks(usb_tracks, cache, store)

    linked = 0
    for match in result.matched:
        t = match.usb_track
        cache.link_rekordbox_id(
            t.rekordbox_id, match.fingerprint,
            source_player="devicesql", source_slot="usb",
        )
        cache.store_pioneer_metadata(t.rekordbox_id, {
            "title": t.title,
            "artist": t.artist,
            "bpm": t.bpm,
            "key_name": t.key,
            "file_path": t.file_path,
            "scan_timestamp": time.time(),
        }, source_player="devicesql", source_slot="usb")
        linked += 1

    logger.info("Applied %d DeviceSQL-only links from USB scan", linked)
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
