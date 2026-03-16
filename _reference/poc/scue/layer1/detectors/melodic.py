"""Melodic/tonal event detection — Tier 2 (Milestone 7).

Detects risers, fallers, stabs, and arpeggios.

Status: STUB — not yet implemented (Milestone 7).
"""

from ..models import MusicalEvent


def detect_melodic(features: dict, audio_path: str) -> list[MusicalEvent]:
    """Detect risers, fallers, stabs, and arp patterns.

    Args:
        features: output of detectors/features.py::extract_all()
        audio_path: path to the audio file (needed for pitch tracking)

    Returns:
        List of MusicalEvent with type in {"riser", "faller", "stab", "arp_note"}

    TODO(milestone-7):
      - Riser/faller: spectral flux over longer windows with direction detection.
      - Stab: high onset_strength + short duration + tonal content.
      - Arp: pitch tracking (librosa.pyin or crepe) + onset alignment
             → extract relative interval pattern (e.g. [0, 4, 7, 12]).
    """
    # TODO: implement
    return []
