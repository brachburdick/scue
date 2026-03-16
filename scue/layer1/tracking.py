"""Live playback tracking — Layer 1B.

Translates incoming DeckState updates from ProDJLinkClient into TrackCursor
snapshots, and triggers the Pioneer enrichment pass when a new track is first
loaded on a deck.

ADR-005: Master-deck-only cursor for Milestone 2 — only the deck with
is_master=True produces a TrackCursor. Non-master decks are tracked internally
but return None from on_deck_update().
"""

import logging
from pathlib import Path
from typing import Optional

from .models import DeckState, TrackCursor, TrackAnalysis
from .cursor import build_cursor
from .enrichment import run_enrichment_pass
from . import db as _db

log = logging.getLogger(__name__)


class PlaybackTracker:
    """Converts raw DeckState changes into TrackCursor updates.

    For each Pioneer deck update:
    1. Check if track changed on this channel (rekordbox_id)
    2. If changed: look up stored TrackAnalysis, trigger enrichment if needed
    3. Build TrackCursor from analysis + deck state
    4. Return cursor only for master deck (ADR-005)
    """

    def __init__(self, db_path: Path = _db.DB_PATH) -> None:
        self._db_path = db_path
        # Per-channel state: rekordbox_id currently loaded
        self._channel_track: dict[int, int] = {}
        # Per-channel cached analysis (avoids repeated DB lookups)
        self._channel_analysis: dict[int, TrackAnalysis | None] = {}
        # Tracks that have already been enriched this session
        self._enriched: set[str] = set()

    def on_deck_update(self, channel: int, deck_state: DeckState) -> TrackCursor | None:
        """Process a DeckState update and return an updated TrackCursor, or None.

        Args:
            channel: Pioneer player number (1-4)
            deck_state: current deck state

        Returns:
            Updated TrackCursor if this is the master deck and analysis is available,
            else None.
        """
        # Track changes: detect when a new track is loaded
        current_rb_id = deck_state.rekordbox_id
        prev_rb_id = self._channel_track.get(channel)

        if current_rb_id != prev_rb_id:
            self._channel_track[channel] = current_rb_id
            self._channel_analysis[channel] = None  # invalidate cache

            if current_rb_id > 0:
                self._load_track_for_channel(channel, deck_state)
            else:
                log.debug("Channel %d: track unloaded", channel)

        # ADR-005: only master deck produces a cursor
        if not deck_state.is_master:
            return None

        analysis = self._channel_analysis.get(channel)
        if analysis is None:
            return None

        return build_cursor(analysis, deck_state)

    def _load_track_for_channel(self, channel: int, deck_state: DeckState) -> None:
        """Look up analysis for a newly loaded track and trigger enrichment."""
        rb_id = deck_state.rekordbox_id
        fp = _db.lookup_fingerprint(rb_id, db_path=self._db_path)

        if fp is None:
            log.info(
                "Channel %d: rekordbox_id=%d has no fingerprint mapping — "
                "analysis unavailable until track is manually linked",
                channel, rb_id,
            )
            return

        analysis = _db.load_analysis(fp, db_path=self._db_path)
        if analysis is None:
            log.info("Channel %d: no analysis found for fp=%s", channel, fp[:12])
            return

        # Trigger enrichment on first load (BPM-only for now, since we only
        # get BPM from status packets — beatgrid/key require DBSERVER)
        if fp not in self._enriched and deck_state.original_bpm > 0:
            enriched = run_enrichment_pass(
                analysis,
                pioneer_bpm=deck_state.original_bpm,
                pioneer_key=deck_state.track_key,
                db_path=self._db_path,
            )
            _db.store_analysis(enriched, db_path=self._db_path)
            self._enriched.add(fp)
            analysis = enriched
            log.info(
                "Channel %d: enriched fp=%s with Pioneer BPM=%.2f",
                channel, fp[:12], deck_state.original_bpm,
            )

        self._channel_analysis[channel] = analysis
        log.info("Channel %d: loaded analysis fp=%s v%d", channel, fp[:12], analysis.version)

    def get_analysis(self, channel: int) -> TrackAnalysis | None:
        """Get the currently loaded analysis for a channel (for debugging)."""
        return self._channel_analysis.get(channel)
