"""Live playback tracking — Layer 1B.

Translates incoming PlayerState updates from the bridge adapter into TrackCursor
snapshots, and triggers the Pioneer enrichment pass when a new track is first
loaded on a deck.

ADR-006: Master-deck-only cursor for Milestone 2 — only the on-air deck
produces a TrackCursor. Non-on-air decks are tracked internally but return
None from on_player_update().
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from ..bridge.adapter import DeviceInfo, PlayerState
from .cursor import build_cursor
from .enrichment import run_enrichment_pass
from .models import TrackAnalysis, TrackCursor
from .storage import TrackStore, TrackCache
from .strata.live_analyzer import LiveStrataAnalyzer
from .strata.models import ArrangementFormula

log = logging.getLogger(__name__)

# Callback type for looking up device info by player number
DeviceLookup = Callable[[int], DeviceInfo | None]

# Callback for live strata updates (player_number, formula)
OnLiveStrata = Callable[[int, ArrangementFormula], None]


class PlaybackTracker:
    """Converts raw PlayerState changes into TrackCursor updates.

    For each bridge adapter player update:
    1. Check if track changed on this player (rekordbox_id)
    2. If changed: look up stored TrackAnalysis, trigger enrichment if needed
    3. Build TrackCursor from analysis + player state
    4. Return cursor only for on-air player
    """

    def __init__(
        self,
        store: TrackStore,
        cache: TrackCache,
        device_lookup: DeviceLookup | None = None,
    ) -> None:
        self._store = store
        self._cache = cache
        self._device_lookup = device_lookup
        # Per-player state: rekordbox_id currently loaded
        self._player_track: dict[int, int] = {}
        # Per-player cached analysis (avoids repeated lookups)
        self._player_analysis: dict[int, TrackAnalysis | None] = {}
        # Tracks that have already been enriched this session
        self._enriched: set[str] = set()
        # Per-player last known position (ms) from player_status
        self._player_position_ms: dict[int, float] = {}
        # Per-player cached live strata formula
        self._player_live_strata: dict[int, ArrangementFormula | None] = {}
        # Callback for live strata updates
        self.on_live_strata: OnLiveStrata | None = None
        # Fingerprints that have already been captured this session
        self._captured_live: set[str] = set()

    def on_player_update(self, player: PlayerState) -> TrackCursor | None:
        """Process a PlayerState update and return an updated TrackCursor, or None.

        Args:
            player: current player state from bridge adapter.

        Returns:
            Updated TrackCursor if this player is on-air and analysis is available,
            else None.
        """
        pn = player.player_number

        # Track changes: detect when a new track is loaded
        current_rb_id = player.rekordbox_id
        prev_rb_id = self._player_track.get(pn)

        if current_rb_id != prev_rb_id:
            self._player_track[pn] = current_rb_id
            self._player_analysis[pn] = None  # invalidate cache
            self._player_live_strata[pn] = None  # invalidate live strata

            if current_rb_id > 0:
                self._load_track_for_player(player)
                self._try_build_live_strata(player)
                self._try_capture_live_data(player)
            else:
                log.debug("Player %d: track unloaded", pn)
        elif current_rb_id > 0:
            # Retry live strata / capture if we didn't have enough data on first attempt
            # (phrases/waveform may arrive after initial player_status)
            if self._player_live_strata.get(pn) is None:
                self._try_build_live_strata(player)
            self._try_capture_live_data(player)

        # Only on-air player produces a cursor
        if not player.is_on_air:
            return None

        analysis = self._player_analysis.get(pn)
        if analysis is None:
            return None

        # Use adapter-computed position from PlayerState if available,
        # falling back to manually-set position (from update_position()).
        position_ms = (
            player.playback_position_ms
            if player.playback_position_ms is not None
            else self._player_position_ms.get(pn, 0.0)
        )
        return build_cursor(analysis, player, position_ms=position_ms)

    def on_track_loaded(self, player_number: int, title: str, artist: str) -> None:
        """Called by bridge adapter when a new track loads on a player.

        This is the signal to look up analysis and trigger enrichment.
        The actual work is done in on_player_update when player state arrives.
        """
        log.info("Track loaded on player %d: %s — %s", player_number, title, artist)

    def update_position(self, player_number: int, position_ms: float) -> None:
        """Update the known playback position for a player.

        Called from player_status messages which include beat_number.
        Position estimation from beat_number * beat_duration is the primary
        position source until we get DBSERVER timeline data.
        """
        self._player_position_ms[player_number] = position_ms

    def get_analysis(self, player_number: int) -> TrackAnalysis | None:
        """Get the currently loaded analysis for a player (for debugging)."""
        return self._player_analysis.get(player_number)

    def get_live_strata(self, player_number: int) -> ArrangementFormula | None:
        """Get the live strata formula for a player."""
        return self._player_live_strata.get(player_number)

    def _try_capture_live_data(self, player: PlayerState) -> None:
        """Capture live Pioneer data to disk when phrases + beat_grid are available.

        Called on track load and on subsequent updates when data arrives late.
        Only captures once per fingerprint per session (idempotent).
        """
        pn = player.player_number

        # Need both phrases and beat_grid to capture (spec requirement)
        if not player.phrases or not player.beat_grid:
            return

        # Resolve fingerprint for this track
        rb_id = player.rekordbox_id
        src_player = str(player.track_source_player) if player.track_source_player else str(pn)
        src_slot = player.track_source_slot or "usb"

        fp = self._cache.lookup_fingerprint(rb_id, source_player=src_player, source_slot=src_slot)
        if fp is None:
            for ns in ("dlp", "devicesql"):
                fp = self._cache.lookup_fingerprint(rb_id, source_player=ns, source_slot=src_slot)
                if fp is not None:
                    break
        if fp is None:
            return

        # Skip if already captured this session
        if fp in self._captured_live:
            return

        # Build the snapshot
        data: dict = {
            "fingerprint": fp,
            "rekordbox_id": rb_id,
            "title": player.title,
            "artist": player.artist,
            "bpm": player.bpm,
            "duration": player.duration,
            "key": player.key,
            "player_number": pn,
            "captured_at": time.time(),
            "phrases": player.phrases,
            "beat_grid": player.beat_grid,
            "cue_points": player.cue_points,
            "memory_points": player.memory_points,
            "hot_cues": player.hot_cues,
        }

        # Include waveform if available
        if player.pioneer_waveform:
            data["pioneer_waveform"] = player.pioneer_waveform

        self._store.save_live_data(fp, data)
        self._cache.set_has_live_data(fp)
        self._captured_live.add(fp)
        log.info(
            "Player %d: captured live Pioneer data for fp=%s (%d phrases, %d beats)",
            pn, fp[:12], len(player.phrases), len(player.beat_grid),
        )

    def _try_build_live_strata(self, player: PlayerState) -> None:
        """Attempt to build a live strata formula from Pioneer hardware data.

        Called when a new track loads or when new Pioneer data arrives.
        Fires on_live_strata callback on success.
        """
        pn = player.player_number
        formula = LiveStrataAnalyzer.build_from_pioneer(player)
        if formula is None:
            return

        self._player_live_strata[pn] = formula
        log.info(
            "Player %d: live strata built (%d sections, %.4fs)",
            pn, len(formula.sections), formula.compute_time_seconds,
        )
        if self.on_live_strata:
            self.on_live_strata(pn, formula)

    def _load_track_for_player(self, player: PlayerState) -> None:
        """Look up analysis for a newly loaded track and trigger enrichment."""
        pn = player.player_number
        rb_id = player.rekordbox_id

        # Resolve source_player/source_slot for composite key lookup (ADR-015).
        # The bridge reports which player hosts the media and which slot it's in.
        # Convert int player number to string for the composite key.
        src_player = str(player.track_source_player) if player.track_source_player else str(pn)
        src_slot = player.track_source_slot or "usb"

        # Look up fingerprint from rekordbox_id via cache
        fp = self._cache.lookup_fingerprint(rb_id, source_player=src_player, source_slot=src_slot)
        if fp is None:
            # Fallback: try DLP and DeviceSQL namespaces (USB scan uses these)
            for ns in ("dlp", "devicesql"):
                fp = self._cache.lookup_fingerprint(rb_id, source_player=ns, source_slot=src_slot)
                if fp is not None:
                    break
        if fp is None:
            log.info(
                "Player %d: rekordbox_id=%d (src=%s/%s) has no fingerprint mapping — "
                "analysis unavailable until track is manually linked",
                pn, rb_id, src_player, src_slot,
            )
            return

        analysis = self._store.load_latest(fp)
        if analysis is None:
            log.info("Player %d: no analysis found for fp=%s", pn, fp[:12])
            return

        # Trigger enrichment on first load with Pioneer data
        if fp not in self._enriched and player.bpm > 0:
            # Fetch cached Pioneer metadata from USB scan (ADR-012)
            # Try the exact source first, then DLP/DeviceSQL namespaces
            pioneer_meta = self._cache.get_pioneer_metadata(
                rb_id, source_player=src_player, source_slot=src_slot,
            )
            if pioneer_meta is None:
                for ns in ("dlp", "devicesql"):
                    pioneer_meta = self._cache.get_pioneer_metadata(
                        rb_id, source_player=ns, source_slot=src_slot,
                    )
                    if pioneer_meta is not None:
                        break

            pioneer_key = player.key
            pioneer_beatgrid: list[float] | None = None
            if pioneer_meta:
                if not pioneer_key and pioneer_meta.get("key_name"):
                    pioneer_key = pioneer_meta["key_name"]
                bg = pioneer_meta.get("beatgrid")
                if bg:
                    # Extract beat timestamps, converting ms → seconds
                    # (enrichment expects seconds per its contract)
                    pioneer_beatgrid = [b["time_ms"] / 1000.0 for b in bg if "time_ms" in b]

            enriched = run_enrichment_pass(
                analysis,
                pioneer_bpm=player.bpm,
                store=self._store,
                cache=self._cache,
                pioneer_key=pioneer_key,
                pioneer_beatgrid=pioneer_beatgrid,
            )
            self._enriched.add(fp)
            analysis = enriched
            log.info(
                "Player %d: enriched fp=%s with Pioneer BPM=%.2f key=%s beatgrid=%s",
                pn, fp[:12], player.bpm, pioneer_key or "(none)",
                f"{len(pioneer_beatgrid)} beats" if pioneer_beatgrid else "(none)",
            )

        self._player_analysis[pn] = analysis
        log.info("Player %d: loaded analysis fp=%s v%d", pn, fp[:12], analysis.version)
