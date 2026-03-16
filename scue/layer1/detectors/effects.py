"""Effect sweep detection — Tier 2 (Milestone 7).

Detects filter sweeps, panning oscillations, and similar modulation effects.

Status: STUB — not yet implemented (Milestone 7).
"""

from ..models import MusicalEvent


def detect_effect_sweeps(features: dict) -> list[MusicalEvent]:
    """Detect filter sweeps, panning sweeps, and similar modulation events.

    Args:
        features: output of detectors/features.py::extract_all()

    Returns:
        List of MusicalEvent with type="sweep" and payload describing
        the parameter (filter_cutoff, pan, etc.), start/end times, and curve shape.

    TODO(milestone-7):
      - Filter sweep: track spectral centroid trajectory over 2–32 bar windows.
        A sustained monotonic rise or fall in centroid = filter sweep.
      - Panning: use stereo width / channel difference if stereo input is supported.
    """
    # TODO: implement
    return []
