"""Track scanner — programmatically loads tracks on CDJ hardware to capture Pioneer data.

Uses the bridge command channel to browse USB contents and load tracks across one
or more decks in parallel. Captures all Finder data (metadata, beatgrid, phrases,
cues, waveform) that arrives via the existing read-only bridge stream.

Multi-deck scanning: tracks are placed in a shared queue. Each target deck runs
a worker that pulls from the queue, loads the track, waits for Finder data, and
persists the capture. Data callbacks are routed by player_number to the correct
deck's capture slot.

See specs/feat-bridge-command-channel/spec.md for the full design.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from ..bridge.client import BridgeWebSocket
from ..bridge.commands import (
    BrowseAllTracksCommand,
    BrowsePlaylistCommand,
    BrowseRootMenuCommand,
    CommandResponse,
    LoadTrackCommand,
)
from .storage import TrackCache

logger = logging.getLogger(__name__)


class ScanStatus(str, Enum):
    IDLE = "idle"
    BROWSING = "browsing"
    SCANNING = "scanning"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPING = "stopping"


@dataclass
class ScanProgress:
    """Current state of a scan job."""
    status: ScanStatus = ScanStatus.IDLE
    total: int = 0
    scanned: int = 0
    skipped: int = 0
    errors: int = 0
    current_track: str = ""
    current_rekordbox_id: int = 0
    error_messages: list[str] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    deck_progress: dict[int, dict] = field(default_factory=dict)  # player_number → counts

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "total": self.total,
            "scanned": self.scanned,
            "skipped": self.skipped,
            "errors": self.errors,
            "current_track": self.current_track,
            "current_rekordbox_id": self.current_rekordbox_id,
            "error_messages": self.error_messages[-10:],  # last 10 errors
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_s": round(
                (self.completed_at or time.time()) - self.started_at, 1
            ) if self.started_at else 0.0,
            "deck_progress": self.deck_progress,
        }


@dataclass
class TrackEntry:
    """A track discovered on the USB, ready to be scanned."""
    rekordbox_id: int
    title: str = ""
    artist: str = ""


@dataclass
class CapturedTrackData:
    """All Pioneer data captured for a single track during a scan."""
    rekordbox_id: int
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    key: str = ""
    bpm: float = 0.0
    duration: float = 0.0
    color: str | None = None
    rating: int = 0
    comment: str = ""
    beat_grid: list[dict] = field(default_factory=list)
    phrases: list[dict] = field(default_factory=list)
    cue_points: list[dict] = field(default_factory=list)
    memory_points: list[dict] = field(default_factory=list)
    hot_cues: list[dict] = field(default_factory=list)
    waveform_data: str = ""  # base64 of Pioneer RGB waveform
    waveform_frame_count: int = 0
    waveform_total_time_ms: int = 0
    waveform_is_color: bool = True
    captured_at: float = 0.0
    source_player: int = 0  # Which deck captured this track


@dataclass
class DeckCaptureSlot:
    """Per-deck capture state for multi-deck scanning.

    Each active deck gets its own slot to accumulate Finder data independently.
    Data callbacks route incoming messages to the correct slot by player_number.
    """
    player_number: int
    capture: CapturedTrackData | None = None
    received_metadata: bool = False
    received_beatgrid: bool = False
    received_phrases: bool = False
    received_cues: bool = False
    received_waveform: bool = False
    data_event: asyncio.Event = field(default_factory=asyncio.Event)

    def reset(self, rekordbox_id: int, title: str = "", artist: str = "") -> None:
        """Reset for a new track capture on this deck."""
        self.capture = CapturedTrackData(
            rekordbox_id=rekordbox_id,
            title=title,
            artist=artist,
            source_player=self.player_number,
        )
        self.received_metadata = False
        self.received_beatgrid = False
        self.received_phrases = False
        self.received_cues = False
        self.received_waveform = False
        self.data_event.clear()

    @property
    def has_essential_data(self) -> bool:
        """True when metadata + at least one of beatgrid/phrases has arrived."""
        return self.received_metadata and (
            self.received_beatgrid or self.received_phrases
        )


class TrackScanner:
    """Orchestrates batch scanning of tracks via bridge command channel.

    Supports multi-deck parallel scanning: multiple CDJ decks pull tracks
    from a shared queue concurrently. Data callbacks are routed to per-deck
    capture slots by player_number.

    Usage (single deck):
        scanner = TrackScanner(ws_client, cache)
        tracks = await scanner.browse_all_tracks(player=1, slot="usb")
        await scanner.start_scan(player=1, slot="usb", tracks=tracks)

    Usage (multi-deck):
        await scanner.start_scan(
            player=1, slot="usb", target_players=[1, 2],
        )
    """

    def __init__(
        self,
        ws_client: BridgeWebSocket,
        cache: TrackCache,
        settle_delay: float = 2.0,
        load_timeout: float = 15.0,
        on_progress: asyncio.coroutines = None,  # async callback(ScanProgress)
        on_track_captured: asyncio.coroutines = None,  # async callback(CapturedTrackData)
    ):
        self._ws = ws_client
        self._cache = cache
        self._settle_delay = settle_delay
        self._load_timeout = load_timeout
        self._on_progress = on_progress
        self._on_track_captured = on_track_captured

        self._progress = ScanProgress()
        self._stop_requested = False
        self._scan_task: asyncio.Task | None = None

        # Per-deck capture slots: keyed by player_number.
        # Populated when a scan starts, cleared when it ends.
        self._slots: dict[int, DeckCaptureSlot] = {}

    @property
    def progress(self) -> ScanProgress:
        return self._progress

    @property
    def is_scanning(self) -> bool:
        return self._progress.status in (ScanStatus.SCANNING, ScanStatus.BROWSING)

    # ── Browse commands ──────────────────────────────────────────────────

    async def browse_root_menu(self, player: int, slot: str) -> CommandResponse:
        """List top-level folders/playlists on a player's USB/SD slot."""
        cmd = BrowseRootMenuCommand(player_number=player, slot=slot)
        return await self._ws.send_command(cmd, timeout=10.0)

    async def browse_playlist(
        self, player: int, slot: str, folder_id: int, is_folder: bool = True
    ) -> CommandResponse:
        """List tracks/folders within a folder or playlist.

        is_folder=True navigates into a folder (returns sub-items).
        is_folder=False lists tracks within a leaf playlist.
        """
        cmd = BrowsePlaylistCommand(
            player_number=player, slot=slot, folder_id=folder_id,
            is_folder=is_folder,
        )
        return await self._ws.send_command(cmd, timeout=10.0)

    async def browse_all_tracks(self, player: int, slot: str) -> list[TrackEntry]:
        """Get flat list of all tracks on a USB/SD slot.

        Returns list of TrackEntry objects. May be large for big libraries.
        """
        cmd = BrowseAllTracksCommand(player_number=player, slot=slot)
        resp = await self._ws.send_command(cmd, timeout=30.0)

        if not resp.ok:
            raise RuntimeError(
                f"browse_all_tracks failed: {resp.error_message}"
            )

        tracks = []
        for item in resp.data.get("tracks", []):
            tracks.append(TrackEntry(
                rekordbox_id=int(item.get("rekordbox_id", 0)),
                title=item.get("title", ""),
                artist=item.get("artist", ""),
            ))
        logger.info("Browsed %d tracks on player %d slot %s", len(tracks), player, slot)
        return tracks

    # ── Scan orchestration ───────────────────────────────────────────────

    async def start_scan(
        self,
        player: int,
        slot: str,
        tracks: list[TrackEntry] | None = None,
        track_ids: list[int] | None = None,
        force_rescan: bool = False,
        target_players: list[int] | None = None,
    ) -> None:
        """Start a scan job across one or more decks.

        Args:
            player: Player number used for browsing tracks and as default
                    scan deck if target_players is not set.
            slot: "usb" or "sd".
            tracks: Pre-fetched track list. If None, browses all tracks first.
            track_ids: If provided, filter to only these rekordbox IDs.
            force_rescan: If True, re-scan tracks that already have pioneer_scan_data.
            target_players: Which decks to use for scanning. If None, uses [player].
                           Multiple decks scan in parallel from a shared queue.
        """
        if self.is_scanning:
            raise RuntimeError("Scan already in progress")

        if target_players is None:
            target_players = [player]

        self._stop_requested = False
        self._progress = ScanProgress(
            status=ScanStatus.BROWSING,
            started_at=time.time(),
        )
        await self._emit_progress()

        try:
            # Get track list if not provided
            if tracks is None:
                tracks = await self.browse_all_tracks(player, slot)

            # Filter to specific IDs if requested
            if track_ids is not None:
                id_set = set(track_ids)
                tracks = [t for t in tracks if t.rekordbox_id in id_set]

            # Filter out already-scanned tracks (unless force_rescan)
            if not force_rescan:
                tracks = self._filter_already_scanned(tracks, player, slot)

            self._progress.total = len(tracks)
            self._progress.status = ScanStatus.SCANNING
            await self._emit_progress()

            if not tracks:
                logger.info("No tracks to scan (all already scanned or empty USB)")
                self._progress.status = ScanStatus.COMPLETED
                self._progress.completed_at = time.time()
                await self._emit_progress()
                return

            logger.info(
                "Starting scan: %d tracks on %d deck(s) %s slot %s (force_rescan=%s)",
                len(tracks), len(target_players), target_players, slot, force_rescan,
            )

            # Set up per-deck capture slots and progress tracking
            self._slots.clear()
            for p in target_players:
                self._slots[p] = DeckCaptureSlot(player_number=p)
                self._progress.deck_progress[p] = {
                    "status": "idle", "scanned": 0, "errors": 0,
                    "current_track": "", "total": 0,
                }

            # Fill the shared work queue
            queue: asyncio.Queue[TrackEntry] = asyncio.Queue()
            for track in tracks:
                await queue.put(track)

            # Launch one worker per deck — they pull from the shared queue
            workers = [
                asyncio.create_task(
                    self._deck_worker(p, slot, queue),
                    name=f"scan-deck-{p}",
                )
                for p in target_players
            ]

            # Wait for all tracks to be processed (or stop requested)
            await queue.join()

            # Cancel idle workers (blocked on empty queue)
            for w in workers:
                w.cancel()
            # Suppress CancelledError from workers
            await asyncio.gather(*workers, return_exceptions=True)

            self._slots.clear()
            self._progress.status = ScanStatus.COMPLETED
            self._progress.completed_at = time.time()
            await self._emit_progress()

            logger.info(
                "Scan complete: %d scanned, %d skipped, %d errors in %.1fs",
                self._progress.scanned,
                self._progress.skipped,
                self._progress.errors,
                self._progress.completed_at - self._progress.started_at,
            )

        except Exception as e:
            logger.error("Scan failed: %s", e)
            self._slots.clear()
            self._progress.status = ScanStatus.FAILED
            self._progress.error_messages.append(str(e))
            self._progress.completed_at = time.time()
            await self._emit_progress()
            raise

    def stop_scan(self) -> None:
        """Request the current scan to stop after the current track."""
        if self.is_scanning:
            self._stop_requested = True
            self._progress.status = ScanStatus.STOPPING
            logger.info("Scan stop requested")

    async def _deck_worker(
        self, player: int, slot: str, queue: asyncio.Queue[TrackEntry]
    ) -> None:
        """Worker coroutine for a single deck. Pulls tracks from the shared queue."""
        while not self._stop_requested:
            try:
                track = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            try:
                await self._scan_one_track(player, slot, track)
            except Exception as e:
                logger.error("Deck %d worker error on rbid=%d: %s", player, track.rekordbox_id, e)
            finally:
                queue.task_done()

            # Settle delay between loads on this deck
            if not self._stop_requested:
                await asyncio.sleep(self._settle_delay)

    async def _scan_one_track(
        self, player: int, slot_name: str, track: TrackEntry
    ) -> None:
        """Load one track on a specific deck and capture all Pioneer data."""
        track_label = f"{track.title} — {track.artist}"

        # Update aggregate progress
        self._progress.current_track = track_label
        self._progress.current_rekordbox_id = track.rekordbox_id
        # Update per-deck progress
        if player in self._progress.deck_progress:
            self._progress.deck_progress[player]["current_track"] = track_label
            self._progress.deck_progress[player]["status"] = "scanning"
        await self._emit_progress()

        logger.info(
            "Deck %d scanning track %d/%d: rbid=%d %s",
            player,
            self._progress.scanned + self._progress.skipped + self._progress.errors + 1,
            self._progress.total,
            track.rekordbox_id,
            track_label,
        )

        # Reset this deck's capture slot
        deck_slot = self._slots.get(player)
        if deck_slot is None:
            logger.error("No capture slot for player %d", player)
            return
        deck_slot.reset(track.rekordbox_id, track.title, track.artist)

        # Send load command
        try:
            cmd = LoadTrackCommand(
                target_player=player,
                rekordbox_id=track.rekordbox_id,
                source_player=player,
                source_slot=slot_name,
            )
            resp = await self._ws.send_command(cmd, timeout=5.0)
            if not resp.ok:
                raise RuntimeError(f"load_track failed: {resp.error_message}")
        except Exception as e:
            logger.error("Failed to load track rbid=%d on deck %d: %s", track.rekordbox_id, player, e)
            self._progress.errors += 1
            if player in self._progress.deck_progress:
                self._progress.deck_progress[player]["errors"] = (
                    self._progress.deck_progress[player].get("errors", 0) + 1
                )
            self._progress.error_messages.append(
                f"deck={player} rbid={track.rekordbox_id}: load failed: {e}"
            )
            return

        # Wait for Finder data to arrive (metadata + at least one of beatgrid/phrases)
        try:
            await asyncio.wait_for(
                self._wait_for_track_data(player),
                timeout=self._load_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout waiting for data on deck %d rbid=%d — saving partial data",
                player, track.rekordbox_id,
            )

        # Finalize capture
        deck_slot.capture.captured_at = time.time()

        # Notify callback
        if self._on_track_captured:
            try:
                await self._on_track_captured(deck_slot.capture)
            except Exception as e:
                logger.error("on_track_captured callback failed: %s", e)

        self._progress.scanned += 1
        if player in self._progress.deck_progress:
            self._progress.deck_progress[player]["scanned"] = (
                self._progress.deck_progress[player].get("scanned", 0) + 1
            )

        logger.info(
            "Deck %d captured data for rbid=%d: meta=%s grid=%s phrases=%s cues=%s wf=%s",
            player, track.rekordbox_id,
            deck_slot.received_metadata,
            deck_slot.received_beatgrid,
            deck_slot.received_phrases,
            deck_slot.received_cues,
            deck_slot.received_waveform,
        )

    async def _wait_for_track_data(self, player: int) -> None:
        """Wait until we've received the essential data for a deck's current track.

        Essential = metadata + at least one of beatgrid or phrases.
        Other pieces (cues, waveform) are collected opportunistically within
        the timeout (handled by caller).
        """
        deck_slot = self._slots.get(player)
        if deck_slot is None:
            return

        while True:
            if deck_slot.has_essential_data:
                # Give a brief window for remaining data to arrive
                await asyncio.sleep(1.0)
                return
            await asyncio.sleep(0.2)

    # ── Data capture callbacks (called by adapter) ───────────────────────
    # Each callback routes by player_number to the correct deck's capture slot.

    def _get_active_slot(self, player_number: int, payload: dict | None = None) -> DeckCaptureSlot | None:
        """Get the active capture slot for a player, validating rekordbox_id if payload has one."""
        slot = self._slots.get(player_number)
        if slot is None or slot.capture is None:
            return None
        if payload is not None:
            rbid = payload.get("rekordbox_id", 0)
            if rbid and rbid != slot.capture.rekordbox_id:
                return None
        return slot

    def on_track_metadata(self, player_number: int, payload: dict) -> None:
        """Called when track_metadata arrives from bridge."""
        slot = self._get_active_slot(player_number, payload)
        if slot is None:
            return

        slot.capture.title = payload.get("title", "")
        slot.capture.artist = payload.get("artist", "")
        slot.capture.album = payload.get("album", "")
        slot.capture.genre = payload.get("genre", "")
        slot.capture.key = payload.get("key", "")
        slot.capture.bpm = payload.get("bpm", 0.0)
        slot.capture.duration = payload.get("duration", 0.0)
        slot.capture.color = payload.get("color")
        slot.capture.rating = payload.get("rating", 0)
        slot.capture.comment = payload.get("comment", "")
        slot.received_metadata = True

    def on_beat_grid(self, player_number: int, payload: dict) -> None:
        """Called when beat_grid arrives from bridge."""
        slot = self._get_active_slot(player_number)
        if slot is None:
            return
        slot.capture.beat_grid = payload.get("beats", [])
        slot.received_beatgrid = True

    def on_phrase_analysis(self, player_number: int, payload: dict) -> None:
        """Called when phrase_analysis arrives from bridge."""
        slot = self._get_active_slot(player_number)
        if slot is None:
            return
        slot.capture.phrases = payload.get("phrases", [])
        slot.received_phrases = True

    def on_cue_points(self, player_number: int, payload: dict) -> None:
        """Called when cue_points arrives from bridge."""
        slot = self._get_active_slot(player_number)
        if slot is None:
            return
        slot.capture.cue_points = payload.get("cue_points", [])
        slot.capture.memory_points = payload.get("memory_points", [])
        slot.capture.hot_cues = payload.get("hot_cues", [])
        slot.received_cues = True

    def on_track_waveform(self, player_number: int, payload: dict) -> None:
        """Called when track_waveform arrives from bridge."""
        slot = self._get_active_slot(player_number)
        if slot is None:
            return
        slot.capture.waveform_data = payload.get("data", "")
        slot.capture.waveform_frame_count = payload.get("frame_count", 0)
        slot.capture.waveform_total_time_ms = payload.get("total_time_ms", 0)
        slot.capture.waveform_is_color = payload.get("is_color", True)
        slot.received_waveform = True

    # ── Filtering ────────────────────────────────────────────────────────

    def _filter_already_scanned(
        self, tracks: list[TrackEntry], player: int, slot: str
    ) -> list[TrackEntry]:
        """Remove tracks that already have pioneer_scan_data in the cache."""
        unscanned = []
        skipped = 0
        for track in tracks:
            if self._cache.has_pioneer_scan_data(player, slot, track.rekordbox_id):
                skipped += 1
            else:
                unscanned.append(track)
        if skipped:
            logger.info("Skipping %d already-scanned tracks", skipped)
            self._progress.skipped = skipped
        return unscanned

    # ── Progress ─────────────────────────────────────────────────────────

    async def _emit_progress(self) -> None:
        """Emit progress update via callback."""
        if self._on_progress:
            try:
                await self._on_progress(self._progress)
            except Exception as e:
                logger.error("on_progress callback failed: %s", e)
