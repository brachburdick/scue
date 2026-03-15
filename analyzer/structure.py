"""Wrapper around all-in-one-mlx for ML-based music structure analysis."""

import allin1_mlx


def analyze_structure(audio_path: str) -> dict:
    """Run allin1_mlx (Apple Silicon) structure analysis and return normalized result dict."""
    result = allin1_mlx.analyze(audio_path)

    return {
        "bpm": float(result.bpm),
        "beats": [float(b) for b in result.beats],
        "downbeats": [float(d) for d in result.downbeats],
        "segments": [
            {
                "label": seg.label,
                "start": float(seg.start),
                "end": float(seg.end),
            }
            for seg in result.segments
        ],
    }
