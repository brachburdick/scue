"""Rekordbox master.db scanner — reads the desktop database for full collection metadata.

Reads ~/Library/Pioneer/rekordbox/master.db (encrypted SQLite) via pyrekordbox
to get the authoritative mapping between audio files and ANLZ analysis data.

This is the most complete ingestion path:
  - Audio file paths → can compute SHA256 fingerprints → exact SCUE match
  - ANLZ data paths → phrases, beatgrid, cues, waveforms
  - Full metadata: title, artist, BPM, key, genre, rating, playlists

Unlike the ANLZ-only scanner (rekordbox_scanner.py), this scanner doesn't
rely on filename matching — it uses the actual file paths from the database.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .anlz_parser import AnlzParseError, parse_anlz_beatgrid, parse_anlz_cues, parse_anlz_phrases
from .storage import TrackCache, TrackStore

logger = logging.getLogger(__name__)

# Known master.db locations
MASTER_DB_PATHS = [
    Path.home() / "Library" / "Pioneer" / "rekordbox" / "master.db",
]

# ANLZ base directory (relative paths in master.db resolve from here)
ANLZ_BASE = Path.home() / "Library" / "Pioneer" / "rekordbox" / "share"


@dataclass
class MasterDbTrack:
    """A track from the rekordbox master.db with resolved paths and ANLZ data."""
    rekordbox_id: int
    title: str
    artist: str
    bpm: float              # Already divided by 100
    key: str
    genre: str
    rating: int
    duration_ms: int
    audio_path: str         # Full path to audio file on disk
    anlz_path: str          # Full path to ANLZ .DAT file
    audio_exists: bool
    anlz_exists: bool
    # Parsed ANLZ data (populated during scan)
    phrases: list[dict] = field(default_factory=list)
    beatgrid: list[dict] = field(default_factory=list)
    hot_cues: list[dict] = field(default_factory=list)
    memory_points: list[dict] = field(default_factory=list)
    # SCUE matching
    fingerprint: str | None = None


@dataclass
class MasterDbScanResult:
    """Result of scanning master.db."""
    total_tracks: int
    with_audio: int
    with_anlz: int
    matched_to_scue: int
    tracks: list[MasterDbTrack]
    scan_time_seconds: float


def detect_master_db() -> Path | None:
    """Find the rekordbox master.db file."""
    for path in MASTER_DB_PATHS:
        if path.exists():
            logger.info("Found master.db at %s (%.1f MB)", path, path.stat().st_size / 1e6)
            return path
    return None


def _compute_fingerprint(audio_path: Path) -> str | None:
    """Compute SHA256 fingerprint of an audio file."""
    try:
        h = hashlib.sha256()
        with open(audio_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _parse_anlz_phrases_pyrekordbox(ext_path: Path) -> list[dict]:
    """Parse PSSI phrases using pyrekordbox (handles obfuscated USB ANLZ entries).

    Falls back to empty list on any error. This is preferred over the custom
    parse_anlz_phrases() for master.db ingestion because rekordbox USB ANLZ
    files XOR-obfuscate the PSSI entry bytes, which pyrekordbox decodes.
    """
    try:
        from pyrekordbox.anlz import AnlzFile
        from .anlz_parser import _MOOD_TABLES, _PHRASE_NORMALIZE, MOOD_MID_PHRASES
    except ImportError:
        return []

    try:
        f = AnlzFile.parse_file(str(ext_path))
    except Exception as e:
        logger.debug("pyrekordbox failed to open %s: %s", ext_path.name, e)
        return []

    for _name, sec_list in f.items():
        if "PSSI" not in str(_name):
            continue
        try:
            sec = sec_list[0]
            c = sec.content
            mood = int(c.mood)
            end_beat = int(c.end_beat)
            entries = list(c.entries)

            table = _MOOD_TABLES.get(mood, MOOD_MID_PHRASES)
            phrases: list[dict] = []
            for idx, entry in enumerate(entries):
                beat = int(entry.beat)
                kind_id = int(entry.kind)
                if idx + 1 < len(entries):
                    next_beat = int(entries[idx + 1].beat)
                else:
                    next_beat = end_beat

                raw_label = table.get(kind_id, "unknown")
                label = _PHRASE_NORMALIZE.get(raw_label, raw_label)
                phrases.append({
                    "start_beat": beat,
                    "end_beat": next_beat,
                    "kind": label,
                    "mood": mood,
                })
            return phrases
        except Exception as e:
            logger.debug("pyrekordbox PSSI parse error for %s: %s", ext_path.name, e)

    return []


def _parse_anlz_for_track(track: MasterDbTrack) -> None:
    """Parse ANLZ data for a track (phrases, beatgrid, cues)."""
    dat_path = Path(track.anlz_path)
    if not dat_path.exists():
        return

    # Beatgrid from .DAT
    try:
        track.beatgrid = parse_anlz_beatgrid(dat_path)
    except AnlzParseError as e:
        logger.debug("Beatgrid parse failed for %s: %s", track.title[:30], e)

    # Cues from .DAT
    try:
        hot, mem = parse_anlz_cues(dat_path)
        track.hot_cues = hot
        track.memory_points = mem
    except AnlzParseError as e:
        logger.debug("Cue parse failed for %s: %s", track.title[:30], e)

    # Phrases from .EXT or .2EX — try fast custom parser first, fall back to
    # pyrekordbox for obfuscated USB ANLZ entries (XOR-encoded PSSI bytes).
    for suffix in (".EXT", ".2EX"):
        phrase_path = dat_path.with_suffix(suffix)
        if not phrase_path.exists():
            continue
        try:
            track.phrases = parse_anlz_phrases(phrase_path)
        except AnlzParseError:
            track.phrases = []
        # Sanity check: if custom parser returns all "unknown", data is likely
        # obfuscated — fall back to pyrekordbox
        if track.phrases and all(p["kind"] == "unknown" for p in track.phrases):
            logger.debug("Custom parser returned all-unknown for %s, trying pyrekordbox", phrase_path.name)
            track.phrases = _parse_anlz_phrases_pyrekordbox(phrase_path)
        if track.phrases:
            break


def scan_master_db(
    db_path: Path | None = None,
    match_scue: bool = True,
    store: TrackStore | None = None,
    progress_cb: callable | None = None,
) -> MasterDbScanResult:
    """Scan rekordbox master.db and optionally match to SCUE tracks.

    Args:
        db_path: Path to master.db. Auto-detected if None.
        match_scue: If True, compute fingerprints for tracks with audio on disk
                    and check if they exist in the SCUE track store.
        store: TrackStore for matching. Required if match_scue=True.
        progress_cb: Optional callback(current, total, message).

    Returns:
        MasterDbScanResult with all tracks and match statistics.
    """
    from pyrekordbox import Rekordbox6Database

    start_time = time.time()

    if db_path is None:
        db_path = detect_master_db()
    if db_path is None:
        raise FileNotFoundError("rekordbox master.db not found at known paths")

    logger.info("Opening master.db at %s", db_path)
    db = Rekordbox6Database(db_path)

    contents = list(db.get_content())
    total = len(contents)
    logger.info("master.db contains %d tracks", total)

    tracks: list[MasterDbTrack] = []
    with_audio = 0
    with_anlz = 0

    for i, c in enumerate(contents):
        if progress_cb and i % 100 == 0:
            progress_cb(i, total, "Reading master.db")

        # Skip sampler presets and tracks without BPM
        folder_path = c.FolderPath or ""
        if "/Sampler/" in folder_path or not c.BPM:
            continue

        # Resolve paths
        audio_path = folder_path
        audio_exists = Path(audio_path).exists() if audio_path else False

        anlz_rel = c.AnalysisDataPath or ""
        anlz_full = str(ANLZ_BASE / anlz_rel.lstrip("/")) if anlz_rel else ""
        anlz_exists = Path(anlz_full).exists() if anlz_full else False

        # Extract metadata
        artist = ""
        if c.Artist:
            artist = c.Artist.Name or ""
        key_str = ""
        if c.Key:
            key_str = getattr(c.Key, "Name", "") or getattr(c.Key, "ScaleName", "") or ""
        genre_str = ""
        if c.Genre:
            genre_str = c.Genre.Name or ""

        track = MasterDbTrack(
            rekordbox_id=c.ID,
            title=c.Title or "",
            artist=artist,
            bpm=c.BPM / 100.0 if c.BPM else 0.0,
            key=key_str,
            genre=genre_str,
            rating=c.Rating or 0,
            duration_ms=c.Length or 0,
            audio_path=audio_path,
            anlz_path=anlz_full,
            audio_exists=audio_exists,
            anlz_exists=anlz_exists,
        )

        if audio_exists:
            with_audio += 1
        if anlz_exists:
            with_anlz += 1

        tracks.append(track)

    logger.info(
        "Filtered to %d real tracks (%d with audio, %d with ANLZ)",
        len(tracks), with_audio, with_anlz,
    )

    # Parse ANLZ data only for tracks with audio on disk (these are the ones
    # we can create sidecars for). Parsing all 6000+ ANLZ files via pyrekordbox
    # is extremely slow; limiting to ~500 with audio keeps scan under 30s.
    anlz_tracks = [t for t in tracks if t.anlz_exists and t.audio_exists]
    for i, track in enumerate(anlz_tracks):
        if progress_cb and i % 50 == 0:
            progress_cb(i, len(anlz_tracks), "Parsing ANLZ data")
        _parse_anlz_for_track(track)

    # Match to SCUE tracks by fingerprint
    matched = 0
    if match_scue and store is not None:
        audio_tracks = [t for t in tracks if t.audio_exists]
        for i, track in enumerate(audio_tracks):
            if progress_cb and i % 20 == 0:
                progress_cb(i, len(audio_tracks), "Computing fingerprints")
            fp = _compute_fingerprint(Path(track.audio_path))
            if fp and store.exists(fp):
                track.fingerprint = fp
                matched += 1

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "master.db scan complete: %d tracks, %d audio, %d ANLZ, %d matched, %.1fs",
        len(tracks), with_audio, with_anlz, matched, elapsed,
    )

    return MasterDbScanResult(
        total_tracks=len(tracks),
        with_audio=with_audio,
        with_anlz=with_anlz,
        matched_to_scue=matched,
        tracks=tracks,
        scan_time_seconds=elapsed,
    )


def create_sidecars_from_master_db(
    result: MasterDbScanResult,
    store: TrackStore,
) -> int:
    """Create live_pioneer.json sidecars for matched tracks with ANLZ data.

    Returns the number of sidecars created.
    """
    created = 0
    for track in result.tracks:
        if not track.fingerprint:
            continue
        if not track.phrases and not track.beatgrid:
            continue

        analysis = store.load_latest(track.fingerprint)
        if analysis is None:
            continue

        sidecar = {
            "fingerprint": track.fingerprint,
            "rekordbox_id": track.rekordbox_id,
            "title": track.title,
            "artist": track.artist,
            "bpm": track.bpm,
            "duration": analysis.duration,
            "phrases": track.phrases,
            "beat_grid": track.beatgrid,
            "hot_cues": track.hot_cues,
            "memory_points": track.memory_points,
            "source": "master_db",
        }

        store.save_live_data(track.fingerprint, sidecar)
        created += 1
        logger.debug(
            "Created sidecar for %s (%s) — %d phrases, %d beats",
            track.fingerprint[:12], track.title[:30],
            len(track.phrases), len(track.beatgrid),
        )

    logger.info("Created %d sidecars from master.db scan", created)
    return created


@dataclass
class PlaylistNode:
    """A node in the rekordbox playlist tree."""
    id: int
    name: str
    is_folder: bool
    children: list["PlaylistNode"] = field(default_factory=list)
    track_ids: list[int] = field(default_factory=list)  # rekordbox IDs


def scan_playlists(db_path: Path | None = None) -> list[PlaylistNode]:
    """Read the rekordbox playlist/folder hierarchy from master.db.

    Returns a list of top-level playlist nodes (ParentID == 'root').
    Each node contains nested children and track IDs (rekordbox content IDs).
    """
    from pyrekordbox import Rekordbox6Database

    if db_path is None:
        db_path = detect_master_db()
    if db_path is None:
        raise FileNotFoundError("rekordbox master.db not found")

    db = Rekordbox6Database(db_path)
    all_playlists = list(db.get_playlist())

    # Build nodes
    nodes_by_id: dict[int, PlaylistNode] = {}
    for p in all_playlists:
        # Get track IDs for this playlist
        track_ids: list[int] = []
        if not p.is_folder:
            try:
                contents = list(db.get_playlist_contents(p.ID))
                track_ids = [c.ID for c in contents]
            except Exception as e:
                logger.debug("Failed to get contents for playlist %s: %s", p.Name, e)

        node = PlaylistNode(
            id=p.ID,
            name=p.Name or "",
            is_folder=p.is_folder,
            track_ids=track_ids,
        )
        nodes_by_id[p.ID] = node

    # Build tree: attach children to parents
    roots: list[PlaylistNode] = []
    for p in all_playlists:
        node = nodes_by_id[p.ID]
        if p.ParentID == "root":
            roots.append(node)
        elif p.ParentID in nodes_by_id:
            nodes_by_id[p.ParentID].children.append(node)
        else:
            # Orphan — treat as root
            roots.append(node)

    # Sort children by sequence number
    seq_map = {p.ID: (p.Seq or 0) for p in all_playlists}
    for node in nodes_by_id.values():
        node.children.sort(key=lambda n: seq_map.get(n.id, 0))
    roots.sort(key=lambda n: seq_map.get(n.id, 0))

    logger.info("Loaded %d playlists (%d top-level)", len(all_playlists), len(roots))
    return roots


def _playlist_tree_to_dict(nodes: list[PlaylistNode]) -> list[dict]:
    """Convert playlist tree to serializable dicts."""
    result = []
    for node in nodes:
        d: dict = {
            "id": node.id,
            "name": node.name,
            "is_folder": node.is_folder,
            "track_count": len(node.track_ids),
        }
        if node.is_folder:
            d["children"] = _playlist_tree_to_dict(node.children)
        else:
            d["track_ids"] = node.track_ids
            d["children"] = []
        result.append(d)
    return result


@dataclass
class IngestResult:
    """Result of preparing rekordbox tracks for SCUE ingestion."""
    total_in_rekordbox: int
    already_in_scue: int
    queued_for_analysis: list[str]   # audio paths to analyze
    sidecars_created: int
    sidecars_skipped: int            # no ANLZ data available


def ingest_from_master_db(
    store: TrackStore,
    db_path: Path | None = None,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    genre: str | None = None,
    search: str | None = None,
    progress_cb: callable | None = None,
) -> IngestResult:
    """Prepare rekordbox tracks for SCUE: create sidecars + return analysis queue.

    1. Reads master.db for all tracks with audio on disk
    2. Computes fingerprints to find which are already in SCUE
    3. Creates Pioneer sidecars for ALL tracks with ANLZ data
    4. Returns list of audio paths that need analysis (not yet in SCUE)

    Filters are applied before fingerprinting (which is the slow step).
    """
    from pyrekordbox import Rekordbox6Database

    start_time = time.time()

    if db_path is None:
        db_path = detect_master_db()
    if db_path is None:
        raise FileNotFoundError("rekordbox master.db not found")

    db = Rekordbox6Database(db_path)
    contents = list(db.get_content())

    # Build track list with metadata + path resolution
    tracks: list[MasterDbTrack] = []
    total = len(contents)

    for i, c in enumerate(contents):
        if progress_cb and i % 500 == 0:
            progress_cb(i, total, "Reading master.db")

        folder_path = c.FolderPath or ""
        if "/Sampler/" in folder_path or not c.BPM:
            continue

        bpm = c.BPM / 100.0 if c.BPM else 0.0
        audio_exists = Path(folder_path).exists() if folder_path else False
        if not audio_exists:
            continue  # Skip tracks without audio on disk

        # Apply filters before expensive operations
        if bpm_min is not None and bpm < bpm_min:
            continue
        if bpm_max is not None and bpm > bpm_max:
            continue

        artist = c.Artist.Name if c.Artist else ""
        title = c.Title or ""
        genre_str = c.Genre.Name if c.Genre else ""
        key_str = ""
        if c.Key:
            key_str = getattr(c.Key, "Name", "") or ""

        if genre and genre.lower() not in (genre_str or "").lower():
            continue
        if search:
            q = search.lower()
            if q not in title.lower() and q not in artist.lower():
                continue

        anlz_rel = c.AnalysisDataPath or ""
        anlz_full = str(ANLZ_BASE / anlz_rel.lstrip("/")) if anlz_rel else ""
        anlz_exists = Path(anlz_full).exists() if anlz_full else False

        tracks.append(MasterDbTrack(
            rekordbox_id=c.ID,
            title=title,
            artist=artist,
            bpm=bpm,
            key=key_str,
            genre=genre_str,
            rating=c.Rating or 0,
            duration_ms=c.Length or 0,
            audio_path=folder_path,
            anlz_path=anlz_full,
            audio_exists=True,
            anlz_exists=anlz_exists,
        ))

    logger.info("Filtered to %d tracks with audio on disk", len(tracks))

    # Parse ANLZ data
    for i, track in enumerate(tracks):
        if progress_cb and i % 50 == 0:
            progress_cb(i, len(tracks), "Parsing ANLZ data")
        if track.anlz_exists:
            _parse_anlz_for_track(track)

    # Compute fingerprints and classify tracks
    already_in_scue = 0
    queued: list[str] = []
    sidecars_created = 0
    sidecars_skipped = 0

    for i, track in enumerate(tracks):
        if progress_cb and i % 20 == 0:
            progress_cb(i, len(tracks), "Computing fingerprints")

        fp = _compute_fingerprint(Path(track.audio_path))
        if fp is None:
            continue
        track.fingerprint = fp

        exists = store.exists(fp)
        if exists:
            already_in_scue += 1
        else:
            queued.append(track.audio_path)

        # Create sidecar if ANLZ data available (for both new and existing tracks)
        if track.phrases or track.beatgrid:
            # Need duration from existing analysis, or estimate from BPM
            duration = 0.0
            if exists:
                analysis = store.load_latest(fp)
                if analysis:
                    duration = analysis.duration
            if duration <= 0 and track.duration_ms:
                duration = track.duration_ms / 1000.0

            sidecar = {
                "fingerprint": fp,
                "rekordbox_id": track.rekordbox_id,
                "title": track.title,
                "artist": track.artist,
                "bpm": track.bpm,
                "duration": duration,
                "phrases": track.phrases,
                "beat_grid": track.beatgrid,
                "hot_cues": track.hot_cues,
                "memory_points": track.memory_points,
                "source": "master_db",
            }
            store.save_live_data(fp, sidecar)
            sidecars_created += 1
        else:
            sidecars_skipped += 1

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "Ingest prep: %d total, %d already, %d queued, %d sidecars, %.1fs",
        len(tracks), already_in_scue, len(queued), sidecars_created, elapsed,
    )

    return IngestResult(
        total_in_rekordbox=len(tracks),
        already_in_scue=already_in_scue,
        queued_for_analysis=queued,
        sidecars_created=sidecars_created,
        sidecars_skipped=sidecars_skipped,
    )
