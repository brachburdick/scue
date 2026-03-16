"""Live playback tracking — Layer 1B.

Translates incoming PlayerState updates from the bridge adapter into TrackCursor
snapshots, and triggers the Pioneer enrichment pass when a new track is first
loaded on a deck.

ADR-006: Master-deck-only cursor for Milestone 2 — only the on-air deck
produces a TrackCursor. Non-on-air decks are tracked internally but return
None from on_player_update().
"""

import logging

from ..bridge.adapter import PlayerState
from .cursor import build_cursor
from .enrichment import run_enrichment_pass
from .models import TrackAnalysis, TrackCursor
from .storage import TrackStore, TrackCache

log = logging.getLogger(__name__)


class PlaybackTracker:
    """Converts raw PlayerState changes into TrackCursor updates.

    For each bridge adapter player update:
    1. Check if track changed on this player (rekordbox_id)
    2. If changed: look up stored TrackAnalysis, trigger enrichment if needed
    3. Build TrackCursor from analysis + player state
    4. Return cursor only for on-air player
    """

    def __init__(self, store: TrackStore, cache: TrackCache) -> None:
        self._store = store
        self._cache = cache
        # Per-player state: rekordbox_id currently loaded
        self._player_track: dict[int, int] = {}
        # Per-player cached analysis (avoids repeated lookups)
        self._player_analysis: dict[int, TrackAnalysis | None] = {}
        # Tracks that have already been enriched this session
        self._enriched: set[str] = set()
        # Per-player last known position (ms) from player_status
        self._player_position_ms: dict[int, float] = {}

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

            if current_rb_id > 0:
                self._load_track_for_player(player)
            else:
                log.debug("Player %d: track unloaded", pn)

        # Only on-air player produces a cursor
        if not player.is_on_air:
            return None

        analysis = self._player_analysis.get(pn)
        if analysis is None:
            return None

        position_ms = self._player_position_ms.get(pn, 0.0)
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

    def _load_track_for_player(self, player: PlayerState) -> None:
        """Look up analysis for a newly loaded track and trigger enrichment."""
        pn = player.player_number
        rb_id = player.rekordbox_id

        # Look up fingerprint from rekordbox_id via cache
        fp = self._cache.lookup_fingerprint(rb_id)
        if fp is None:
            log.info(
                "Player %d: rekordbox_id=%d has no fingerprint mapping — "
                "analysis unavailable until track is manually linked",
                pn, rb_id,
            )
            return

        analysis = self._store.load_latest(fp)
        if analysis is None:
            log.info("Player %d: no analysis found for fp=%s", pn, fp[:12])
            return

        # Trigger enrichment on first load with Pioneer BPM
        if fp not in self._enriched and player.bpm > 0:
            enriched = run_enrichment_pass(
                analysis,
                pioneer_bpm=player.bpm,
                store=self._store,
                cache=self._cache,
                pioneer_key=player.key,
            )
            self._enriched.add(fp)
            analysis = enriched
            log.info(
                "Player %d: enriched fp=%s with Pioneer BPM=%.2f",
                pn, fp[:12], player.bpm,
            )

        self._player_analysis[pn] = analysis
        log.info("Player %d: loaded analysis fp=%s v%d", pn, fp[:12], analysis.version)
