"""Tonal event detectors — riser, faller, stab detection.

Signal-based detection for non-percussive musical events. Each detector
implements DetectorProtocol and returns individual MusicalEvent objects
(tonal events are not stored as compact patterns).

Riser/Faller: spectral centroid slope analysis over multi-bar windows.
Stab: HPSS harmonic ratio at onset points with centroid and duration filters.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy import stats as scipy_stats

from ..models import MusicalEvent, Section
from .events import DetectorConfig, DetectorResult
from .features import AudioFeatures

logger = logging.getLogger(__name__)


class RiserDetector:
    """Detects risers via rising spectral centroid slope.

    A riser is a sustained increase in spectral centroid (brightness)
    over ≥2 bars, typically leading into a section boundary (build→drop).
    Section priors boost confidence in build sections.
    """

    name: str = "centroid_slope"
    event_types: list[str] = ["riser"]

    def detect(
        self,
        features: AudioFeatures,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult:
        params = config.params.get("centroid_slope", {})
        min_slope = params.get("min_slope", 50.0)
        min_r2 = params.get("min_r_squared", 0.7)
        min_bars = params.get("min_bars", 2)
        section_priors = config.section_priors.get("riser", {})

        if features.spectral_centroid is None or not downbeats:
            return DetectorResult(metadata={"skipped": "missing_features"})

        sr = features.sr
        hop = features.hop_length
        centroid = features.spectral_centroid
        events: list[MusicalEvent] = []

        # Analyze each section for rising centroid
        for section in sections:
            start_frame = int(section.start * sr / hop)
            end_frame = int(section.end * sr / hop)
            start_frame = max(0, start_frame)
            end_frame = min(len(centroid), end_frame)

            if end_frame - start_frame < 10:
                continue

            section_centroid = centroid[start_frame:end_frame]
            n_frames = len(section_centroid)

            # Compute duration in bars
            section_bars = 0
            for db in downbeats:
                if section.start <= db < section.end:
                    section_bars += 1

            if section_bars < min_bars:
                continue

            # Sliding window analysis: look for sustained rises
            # Window size: roughly 2 bars worth of frames
            avg_beat_dur = (beats[-1] - beats[0]) / (len(beats) - 1) if len(beats) >= 2 else 0.5
            window_frames = int(min_bars * 4 * avg_beat_dur * sr / hop)
            step = window_frames // 2  # 50% overlap

            for win_start in range(0, n_frames - window_frames, step):
                win_end = win_start + window_frames
                window = section_centroid[win_start:win_end]

                x = np.arange(len(window), dtype=np.float64)
                slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, window)

                r_squared = r_value ** 2

                if slope > min_slope and r_squared > min_r2:
                    # Convert frame position to timestamp
                    event_start_frame = start_frame + win_start
                    event_end_frame = start_frame + win_end
                    event_start_time = event_start_frame * hop / sr
                    event_end_time = event_end_frame * hop / sr
                    duration = event_end_time - event_start_time

                    # Base intensity from slope magnitude
                    intensity = min(1.0, slope / (min_slope * 3))

                    # Apply section prior
                    prior = section_priors.get(section.label, 1.0)
                    intensity = min(1.0, intensity * prior)

                    events.append(MusicalEvent(
                        type="riser",
                        timestamp=event_start_time,
                        duration=duration,
                        intensity=round(intensity, 3),
                        payload={
                            "slope": round(float(slope), 2),
                            "r_squared": round(float(r_squared), 3),
                            "section": section.label,
                            "section_prior": prior,
                        },
                    ))

        # Deduplicate overlapping risers (keep highest intensity)
        events = _deduplicate_events(events, tolerance=1.0)

        logger.info("Riser detector: found %d risers", len(events))
        return DetectorResult(
            events=events,
            metadata={
                "strategy": "centroid_slope",
                "total_risers": len(events),
                "params": {"min_slope": min_slope, "min_r2": min_r2, "min_bars": min_bars},
            },
        )


class FallerDetector:
    """Detects fallers via falling spectral centroid with RMS decay.

    A faller is a sustained decrease in spectral centroid (brightness)
    combined with RMS energy decay, typically occurring post-drop or
    in breakdowns. Cymbal crashes are discriminated via spectral flatness.
    """

    name: str = "centroid_slope"
    event_types: list[str] = ["faller"]

    def detect(
        self,
        features: AudioFeatures,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult:
        params = config.params.get("centroid_slope", {})
        min_slope = params.get("min_slope", 50.0)
        min_r2 = params.get("min_r_squared", 0.7)
        min_bars = params.get("min_bars", 2)
        section_priors = config.section_priors.get("faller", {})

        if features.spectral_centroid is None or features.rms is None or not downbeats:
            return DetectorResult(metadata={"skipped": "missing_features"})

        sr = features.sr
        hop = features.hop_length
        centroid = features.spectral_centroid
        rms = features.rms
        flatness = features.spectral_flatness
        events: list[MusicalEvent] = []

        for section in sections:
            start_frame = int(section.start * sr / hop)
            end_frame = int(section.end * sr / hop)
            start_frame = max(0, start_frame)
            end_frame = min(len(centroid), end_frame)

            if end_frame - start_frame < 10:
                continue

            section_centroid = centroid[start_frame:end_frame]
            section_rms = rms[start_frame:min(end_frame, len(rms))]
            n_frames = len(section_centroid)

            avg_beat_dur = (beats[-1] - beats[0]) / (len(beats) - 1) if len(beats) >= 2 else 0.5
            window_frames = int(min_bars * 4 * avg_beat_dur * sr / hop)
            step = window_frames // 2

            for win_start in range(0, n_frames - window_frames, step):
                win_end = win_start + window_frames
                window_c = section_centroid[win_start:win_end]
                window_r = section_rms[win_start:min(win_end, len(section_rms))]

                if len(window_r) < 5:
                    continue

                x = np.arange(len(window_c), dtype=np.float64)
                slope, _, r_value, _, _ = scipy_stats.linregress(x, window_c)
                r_squared = r_value ** 2

                # Faller: negative slope (falling centroid) + decaying RMS
                if slope < -min_slope and r_squared > min_r2:
                    # Also check RMS is decaying
                    x_r = np.arange(len(window_r), dtype=np.float64)
                    rms_slope, _, _, _, _ = scipy_stats.linregress(x_r, window_r)

                    if rms_slope >= 0:
                        continue  # RMS not decaying — probably not a faller

                    # Discriminate cymbals via spectral flatness
                    if flatness is not None:
                        win_flatness = flatness[start_frame + win_start:start_frame + win_end]
                        if len(win_flatness) > 0 and win_flatness.mean() > 0.5:
                            continue  # Too noisy — likely cymbal crash, not a tonal faller

                    event_start_time = (start_frame + win_start) * hop / sr
                    event_end_time = (start_frame + win_end) * hop / sr

                    intensity = min(1.0, abs(slope) / (min_slope * 3))
                    prior = section_priors.get(section.label, 1.0)
                    intensity = min(1.0, intensity * prior)

                    events.append(MusicalEvent(
                        type="faller",
                        timestamp=event_start_time,
                        duration=event_end_time - event_start_time,
                        intensity=round(intensity, 3),
                        payload={
                            "centroid_slope": round(float(slope), 2),
                            "rms_slope": round(float(rms_slope), 6),
                            "r_squared": round(float(r_squared), 3),
                            "section": section.label,
                            "section_prior": prior,
                        },
                    ))

        events = _deduplicate_events(events, tolerance=1.0)
        logger.info("Faller detector: found %d fallers", len(events))
        return DetectorResult(
            events=events,
            metadata={"strategy": "centroid_slope", "total_fallers": len(events)},
        )


class StabDetector:
    """Detects stabs via HPSS harmonic ratio at onset points.

    A stab is a short (50-200ms) harmonic burst — typically a chord hit
    or synth stab. Identified by high harmonic-to-percussive ratio at
    onset points with spectral centroid > 500 Hz.
    """

    name: str = "hpss_harmonic"
    event_types: list[str] = ["stab"]

    def detect(
        self,
        features: AudioFeatures,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult:
        params = config.params.get("hpss_harmonic", {})
        harmonic_ratio_thresh = params.get("harmonic_ratio_threshold", 0.3)
        min_centroid = params.get("min_centroid_hz", 500)
        max_duration_ms = params.get("max_duration_ms", 200)
        section_priors = config.section_priors.get("stab", {})

        if features.y_harmonic is None or features.y_percussive is None:
            return DetectorResult(metadata={"skipped": "no_hpss"})

        sr = features.sr
        hop = features.hop_length
        events: list[MusicalEvent] = []

        # Find onset positions
        onset_frames = _find_onsets(features)
        if not onset_frames:
            return DetectorResult(metadata={"skipped": "no_onsets"})

        # Compute harmonic and percussive energy per frame
        h_energy = _frame_energy(features.y_harmonic, hop)
        p_energy = _frame_energy(features.y_percussive, hop)

        max_dur_samples = int(max_duration_ms * sr / 1000)
        max_dur_frames = max(1, max_dur_samples // hop)

        for onset_frame in onset_frames:
            if onset_frame >= len(h_energy) or onset_frame >= len(p_energy):
                continue

            # Check harmonic ratio at onset
            h = h_energy[onset_frame]
            p = p_energy[onset_frame]
            total = h + p
            if total == 0:
                continue

            ratio = h / total
            if ratio < harmonic_ratio_thresh:
                continue

            # Check spectral centroid
            centroid_frame = min(onset_frame, len(features.spectral_centroid) - 1)
            centroid_val = features.spectral_centroid[centroid_frame]
            if centroid_val < min_centroid:
                continue

            # Estimate stab duration: energy drops below 50% of onset
            onset_energy = h_energy[onset_frame]
            dur_frames = 1
            for f in range(onset_frame + 1, min(onset_frame + max_dur_frames, len(h_energy))):
                if h_energy[f] < onset_energy * 0.5:
                    break
                dur_frames += 1

            duration_ms = dur_frames * hop / sr * 1000
            if duration_ms > max_duration_ms:
                continue  # Too long for a stab

            timestamp = onset_frame * hop / sr
            duration_s = dur_frames * hop / sr

            # Get section context for prior
            section_label = _get_section_at(timestamp, sections)
            prior = section_priors.get(section_label, 1.0)

            intensity = min(1.0, ratio * prior)

            events.append(MusicalEvent(
                type="stab",
                timestamp=round(timestamp, 4),
                duration=round(duration_s, 4),
                intensity=round(intensity, 3),
                payload={
                    "harmonic_ratio": round(float(ratio), 3),
                    "centroid_hz": round(float(centroid_val), 1),
                    "duration_ms": round(duration_ms, 1),
                    "section": section_label,
                    "section_prior": prior,
                },
            ))

        events = _deduplicate_events(events, tolerance=0.05)
        logger.info("Stab detector: found %d stabs", len(events))
        return DetectorResult(
            events=events,
            metadata={"strategy": "hpss_harmonic", "total_stabs": len(events)},
        )


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _find_onsets(features: AudioFeatures) -> list[int]:
    """Find onset frame indices from onset strength envelope."""
    if features.onset_strength is None:
        return []

    onset = features.onset_strength
    threshold = onset.mean() + onset.std()

    # Simple peak-picking: frames where onset exceeds threshold
    # and is a local maximum
    onsets: list[int] = []
    for i in range(1, len(onset) - 1):
        if onset[i] > threshold and onset[i] > onset[i - 1] and onset[i] >= onset[i + 1]:
            onsets.append(i)

    return onsets


def _frame_energy(signal: np.ndarray, hop_length: int) -> np.ndarray:
    """Compute per-frame RMS energy from a time-domain signal."""
    n_frames = len(signal) // hop_length
    energy = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_length
        end = start + hop_length
        frame = signal[start:end]
        energy[i] = np.sqrt(np.mean(frame ** 2))
    return energy


def _get_section_at(time: float, sections: list[Section]) -> str:
    """Get the section label at a given timestamp."""
    for s in sections:
        if s.start <= time < s.end:
            return s.label
    return "unknown"


def _deduplicate_events(
    events: list[MusicalEvent],
    tolerance: float,
) -> list[MusicalEvent]:
    """Remove overlapping events of the same type, keeping highest intensity.

    Args:
        events: List of events to deduplicate.
        tolerance: Time tolerance in seconds for considering events as overlapping.

    Returns:
        Deduplicated list sorted by timestamp.
    """
    if not events:
        return events

    events.sort(key=lambda e: e.timestamp)
    result: list[MusicalEvent] = [events[0]]

    for event in events[1:]:
        prev = result[-1]
        if event.type == prev.type and abs(event.timestamp - prev.timestamp) < tolerance:
            # Keep the one with higher intensity
            if event.intensity > prev.intensity:
                result[-1] = event
        else:
            result.append(event)

    return result
