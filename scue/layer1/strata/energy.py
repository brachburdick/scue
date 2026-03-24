"""Energy and pseudo-layer activity analysis for the quick tier.

Computes per-band (low/mid/high) RMS envelopes at bar resolution and
derives pseudo-layer activity by thresholding band energy. No stem
separation needed — this works on the full mix using frequency bands
as a proxy for layers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from .models import ActivitySpan, StemType

logger = logging.getLogger(__name__)

# Frequency band boundaries (Hz) — aligned with Pioneer mixer EQ
LOW_BAND = (20, 200)
MID_BAND = (200, 2500)
HIGH_BAND = (2500, 11025)

# Pseudo-layer mapping
BAND_TO_STEM: dict[str, str] = {
    "low": StemType.BASS.value,
    "mid": StemType.OTHER.value,
    "high": StemType.OTHER.value,
}


@dataclass
class EnergyAnalysis:
    """Per-bar energy analysis for the quick tier."""
    bar_energies_low: list[float] = field(default_factory=list)
    bar_energies_mid: list[float] = field(default_factory=list)
    bar_energies_high: list[float] = field(default_factory=list)
    bar_energies_total: list[float] = field(default_factory=list)
    bar_onset_density: list[float] = field(default_factory=list)
    overall_energy_curve: list[float] = field(default_factory=list)
    pseudo_activity: dict[str, list[ActivitySpan]] = field(default_factory=dict)


def _compute_band_energy(
    signal: np.ndarray,
    sr: int,
    band_low: float,
    band_high: float,
    hop_length: int = 512,
) -> np.ndarray:
    """Compute RMS energy in a frequency band using bandpass filtering."""
    import librosa

    # Use STFT to isolate frequency band
    S = np.abs(librosa.stft(signal, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr)

    # Mask frequencies outside the band
    mask = (freqs >= band_low) & (freqs <= band_high)
    S_band = S[mask, :]

    # RMS across frequency bins per frame
    if S_band.size == 0:
        return np.zeros(S.shape[1])
    return np.sqrt(np.mean(S_band ** 2, axis=0))


def _frames_for_bar(
    bar_idx: int,
    downbeats: list[float],
    duration: float,
    sr: int,
    hop_length: int,
) -> tuple[int, int]:
    """Get frame range [start, end) for a bar."""
    bar_start = downbeats[bar_idx]
    bar_end = downbeats[bar_idx + 1] if bar_idx + 1 < len(downbeats) else duration

    import librosa
    frame_start = librosa.time_to_frames(bar_start, sr=sr, hop_length=hop_length)
    frame_end = librosa.time_to_frames(bar_end, sr=sr, hop_length=hop_length)
    return int(frame_start), int(frame_end)


def compute_energy_analysis(
    signal: np.ndarray,
    sr: int,
    downbeats: list[float],
    onset_strength: np.ndarray | None,
    duration: float,
    hop_length: int = 512,
) -> EnergyAnalysis:
    """Compute per-bar energy in three frequency bands plus onset density.

    Args:
        signal: Audio waveform (mono).
        sr: Sample rate.
        downbeats: Downbeat timestamps in seconds.
        onset_strength: Onset strength envelope (from AudioFeatures).
        duration: Track duration in seconds.
        hop_length: Hop length used for frame conversion.

    Returns:
        EnergyAnalysis with per-bar energy and pseudo-layer activity.
    """
    if len(downbeats) < 2:
        logger.warning("Not enough downbeats for energy analysis")
        return EnergyAnalysis()

    # Compute per-band energy envelopes (frame-level)
    energy_low = _compute_band_energy(signal, sr, *LOW_BAND, hop_length)
    energy_mid = _compute_band_energy(signal, sr, *MID_BAND, hop_length)
    energy_high = _compute_band_energy(signal, sr, *HIGH_BAND, hop_length)

    n_bars = len(downbeats) - 1
    bar_low: list[float] = []
    bar_mid: list[float] = []
    bar_high: list[float] = []
    bar_total: list[float] = []
    bar_onset: list[float] = []

    for bar_idx in range(n_bars):
        f_start, f_end = _frames_for_bar(bar_idx, downbeats, duration, sr, hop_length)
        f_end = min(f_end, len(energy_low))
        f_start = min(f_start, f_end)

        if f_start >= f_end:
            bar_low.append(0.0)
            bar_mid.append(0.0)
            bar_high.append(0.0)
            bar_total.append(0.0)
            bar_onset.append(0.0)
            continue

        lo = float(np.mean(energy_low[f_start:f_end]))
        mi = float(np.mean(energy_mid[f_start:f_end]))
        hi = float(np.mean(energy_high[f_start:f_end]))
        bar_low.append(lo)
        bar_mid.append(mi)
        bar_high.append(hi)
        bar_total.append(lo + mi + hi)

        # Onset density: count peaks above threshold in this bar
        if onset_strength is not None:
            os_end = min(f_end, len(onset_strength))
            os_start = min(f_start, os_end)
            if os_start < os_end:
                bar_os = onset_strength[os_start:os_end]
                threshold = np.mean(onset_strength) * 0.5
                bar_onset.append(float(np.sum(bar_os > threshold)))
            else:
                bar_onset.append(0.0)
        else:
            bar_onset.append(0.0)

    # Normalize energy curves to 0-1
    max_total = max(bar_total) if bar_total and max(bar_total) > 0 else 1.0
    overall = [e / max_total for e in bar_total]

    # Compute pseudo-layer activity via thresholding
    pseudo_activity = _compute_pseudo_activity(
        bar_low, bar_mid, bar_high, downbeats, duration,
    )

    return EnergyAnalysis(
        bar_energies_low=bar_low,
        bar_energies_mid=bar_mid,
        bar_energies_high=bar_high,
        bar_energies_total=bar_total,
        bar_onset_density=bar_onset,
        overall_energy_curve=overall,
        pseudo_activity=pseudo_activity,
    )


def _compute_pseudo_activity(
    bar_low: list[float],
    bar_mid: list[float],
    bar_high: list[float],
    downbeats: list[float],
    duration: float,
    threshold_ratio: float = 0.15,
    min_span_bars: int = 2,
) -> dict[str, list[ActivitySpan]]:
    """Derive pseudo-layer activity from per-band bar energy.

    Thresholds each band relative to its max. Consecutive active bars
    are merged into ActivitySpans.
    """
    result: dict[str, list[ActivitySpan]] = {}

    for band_name, bar_energies in [
        ("low", bar_low),
        ("mid", bar_mid),
        ("high", bar_high),
    ]:
        if not bar_energies:
            continue

        max_e = max(bar_energies) if max(bar_energies) > 0 else 1.0
        threshold = max_e * threshold_ratio

        # Find active bars
        active = [e > threshold for e in bar_energies]

        # Merge consecutive active bars into spans
        spans: list[ActivitySpan] = []
        span_start: int | None = None

        for i, is_active in enumerate(active):
            if is_active and span_start is None:
                span_start = i
            elif not is_active and span_start is not None:
                if i - span_start >= min_span_bars:
                    avg_energy = float(np.mean(bar_energies[span_start:i]))
                    spans.append(ActivitySpan(
                        start=downbeats[span_start],
                        end=downbeats[i] if i < len(downbeats) else duration,
                        bar_start=span_start,
                        bar_end=i,
                        energy=avg_energy / max_e,
                        confidence=0.6,
                    ))
                span_start = None

        # Close final span
        if span_start is not None:
            n = len(active)
            if n - span_start >= min_span_bars:
                avg_energy = float(np.mean(bar_energies[span_start:n]))
                spans.append(ActivitySpan(
                    start=downbeats[span_start],
                    end=downbeats[n] if n < len(downbeats) else duration,
                    bar_start=span_start,
                    bar_end=n,
                    energy=avg_energy / max_e,
                    confidence=0.6,
                ))

        stem_key = BAND_TO_STEM.get(band_name, StemType.OTHER.value)
        if stem_key not in result:
            result[stem_key] = spans
        else:
            result[stem_key].extend(spans)

    return result


def compute_energy_trend(bar_energies: list[float], window: int = 4) -> str:
    """Classify the energy trend over a window of bars.

    Returns: "rising" | "falling" | "stable" | "peak" | "valley"
    """
    if len(bar_energies) < 2:
        return "stable"

    recent = bar_energies[-window:] if len(bar_energies) >= window else bar_energies
    slope = recent[-1] - recent[0]
    avg = float(np.mean(recent))
    overall_avg = float(np.mean(bar_energies))

    if abs(slope) < 0.05:
        if avg > overall_avg * 1.3:
            return "peak"
        if avg < overall_avg * 0.7:
            return "valley"
        return "stable"
    return "rising" if slope > 0 else "falling"
