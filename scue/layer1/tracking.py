"""Live playback tracking — Layer 1B.

Translates incoming DeckState updates from ProDJLinkClient into PlaybackState
updates on the TrackCursor, and triggers the Pioneer enrichment pass when a
new track is first loaded on a deck.

Status: STUB — not yet implemented (Milestone 2).
The ProDJLinkClient currently feeds deck updates directly to the WebSocket
bridge in scue/main.py. This module will sit in between once the cursor is built.
"""

from .models import DeckState, TrackCursor, PlaybackState


class PlaybackTracker:
    """Converts raw DeckState changes into TrackCursor updates.

    For each Pioneer deck update:
    1. Update PlaybackState
    2. If track changed: look up stored TrackAnalysis (or trigger analysis)
    3. If track changed and no enrichment yet: schedule enrichment pass
    4. Update TrackCursor with current position mapped into TrackAnalysis

    TODO(milestone-2): implement.
    """

    def __init__(self):
        # TODO: inject db reference, cursor reference
        pass

    def on_deck_update(self, channel: int, deck_state: DeckState) -> TrackCursor | None:
        """Process a DeckState update and return an updated TrackCursor, or None.

        Args:
            channel: Pioneer player number (1–4)
            deck_state: current deck state

        Returns:
            Updated TrackCursor if a track is loaded and analysis is available,
            else None.

        TODO(milestone-2): implement.
        """
        # TODO: implement
        return None
