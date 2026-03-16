"""Percussion event detection — Tier 2 (Milestone 7).

Detects kick, snare, hihat, and clap onset times and velocities.
Each detected event becomes a MusicalEvent(type="kick"|"snare"|...) in the TrackAnalysis.

Status: STUB — not yet implemented (Milestone 7).
"""

from ..models import MusicalEvent


def detect_percussion(features: dict) -> list[MusicalEvent]:
    """Detect kick, snare, and hihat events from audio features.

    Args:
        features: output of detectors/features.py::extract_all()

    Returns:
        List of MusicalEvent objects with type in {"kick", "snare", "hihat", "clap"}

    TODO(milestone-7): implement using librosa.onset with percussive source separation.
    Separate percussive component first (librosa.effects.hpss), then run
    onset detection on sub-bands (low for kick, mid for snare, high for hihat).
    """
    # TODO: implement
    return []
