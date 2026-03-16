"""Pioneer enrichment pass — Layer 1B.

When a track is first loaded on Pioneer hardware, SCUE receives Pioneer/rekordbox
metadata (beatgrid, BPM, key). This module uses that data to refine the offline
TrackAnalysis:

  1. Replace the librosa beatgrid with the Pioneer beatgrid
  2. Use Pioneer's BPM as the authoritative base BPM
  3. Use Pioneer's key detection as the reference key
  4. Re-align all section boundaries and Tier 2 event timestamps to the Pioneer grid
  5. Store the updated analysis as a new versioned entry in the database
  6. Log a DivergenceRecord for every field that differed

The original "analysis" version is NEVER overwritten — the enriched version
is stored alongside it, tagged source="pioneer_enriched".

Status: STUB — not yet implemented (Milestone 2).
"""

from .models import TrackAnalysis, DivergenceRecord
from .divergence import log_divergence


def run_enrichment_pass(
    analysis: TrackAnalysis,
    pioneer_bpm: float,
    pioneer_beatgrid: list[float],
    pioneer_key: str,
    pioneer_phrase_data: list[dict] | None = None,
) -> TrackAnalysis:
    """Enrich a TrackAnalysis with Pioneer/rekordbox metadata.

    Args:
        analysis: the existing TrackAnalysis (source="analysis")
        pioneer_bpm: BPM reported by Pioneer hardware
        pioneer_beatgrid: beat timestamps from the Pioneer/rekordbox beatgrid
        pioneer_key: key string from Pioneer (e.g. "Am", "F#")
        pioneer_phrase_data: rekordbox phrase labels if available, or None

    Returns:
        A new TrackAnalysis with version incremented and source="pioneer_enriched".
        The original analysis is not modified.

    TODO(milestone-2): implement.
    """
    # TODO: implement
    raise NotImplementedError(
        "enrichment.run_enrichment_pass not yet implemented — see Milestone 2"
    )
