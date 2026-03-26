"""Per-stem analysis for the standard tier.

Runs energy analysis, event detection, pattern discovery, and activity
span detection on each separated stem audio file. Reuses existing
quick-tier modules (energy.py, patterns.py) and M7 detector infrastructure.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .energy import EnergyAnalysis, compute_energy_analysis
from .models import (
    ActivitySpan,
    ArrangementTransition,
    AtomicEvent,
    Pattern,
    PatternType,
    StemAnalysis,
    StemType,
    TransitionType,
)
from .patterns import discover_patterns

logger = logging.getLogger(__name__)

# Energy threshold for activity detection (fraction of stem's max energy)
ACTIVITY_THRESHOLD = 0.08
# Minimum consecutive bars to count as an activity span
MIN_ACTIVITY_BARS = 2


def analyze_stem(
    stem_path: Path,
    stem_type: StemType,
    downbeats: list[float],
    beats: list[float],
    duration: float,
    sections: list,
    drum_patterns: list | None = None,
) -> StemAnalysis:
    """Run full analysis on a single separated stem.

    Args:
        stem_path: Path to the stem WAV file.
        stem_type: Which stem this is (drums, bass, vocals, other).
        downbeats: Downbeat timestamps from the original track analysis.
        beats: Beat timestamps from the original track analysis.
        duration: Track duration in seconds.
        sections: Section objects from the original track analysis.
        drum_patterns: Original M7 drum patterns (only used for drums stem
            as a comparison baseline — the standard tier re-detects from the
            isolated stem).

    Returns:
        StemAnalysis with energy curve, activity spans, events, and patterns.
    """
    import librosa

    logger.info("Analyzing stem: %s (%s)", stem_type.value, stem_path.name)

    # Load the stem audio
    signal, sr = librosa.load(str(stem_path), sr=22050, mono=True)
    onset_strength = librosa.onset.onset_strength(y=signal, sr=sr)

    # 1. Energy analysis (same as quick tier but on isolated stem)
    energy = compute_energy_analysis(
        signal=signal,
        sr=sr,
        downbeats=downbeats,
        onset_strength=onset_strength,
        duration=duration,
    )

    # 2. Activity spans — where this stem is present vs silent
    activity = _compute_stem_activity(
        energy=energy,
        downbeats=downbeats,
        duration=duration,
        stem_type=stem_type,
    )

    # 3. Per-stem energy curve (normalized per-bar total energy)
    energy_curve = _normalize_energy_curve(energy.bar_energies_total)

    # 4. Event detection on the isolated stem
    events: list[AtomicEvent] = []
    patterns: list[Pattern] = []

    if stem_type == StemType.DRUMS:
        # Run percussion detection on the isolated drum stem
        detected_patterns, detected_events = _detect_drum_events(
            signal, sr, beats, downbeats, sections,
        )
        events.extend(detected_events)
        # Discover repeating patterns from detected drum patterns
        patterns = discover_patterns(detected_patterns, downbeats, beats)
        # Tag patterns with stem attribution
        for p in patterns:
            p.stem = stem_type.value

    elif stem_type == StemType.BASS:
        events = _detect_bass_events(signal, sr, downbeats, onset_strength)

    elif stem_type == StemType.VOCALS:
        events = _detect_vocal_events(signal, sr, downbeats, onset_strength)

    elif stem_type == StemType.OTHER:
        events = _detect_other_events(signal, sr, downbeats, onset_strength)

    # Determine layer role from stem type
    role_map = {
        StemType.DRUMS: "rhythm",
        StemType.BASS: "bassline",
        StemType.VOCALS: "vocal",
        StemType.OTHER: "unknown",
    }

    # 5. Compute RGB waveform for visualization
    from ..waveform import compute_rgb_waveform
    waveform = compute_rgb_waveform(signal, sr)
    logger.info("Stem %s waveform: %d frames", stem_type.value, len(waveform.low))

    return StemAnalysis(
        stem_type=stem_type.value,
        audio_path=str(stem_path),
        layer_role=role_map.get(stem_type, "unknown"),
        activity=activity,
        events=events,
        patterns=patterns,
        energy_curve=energy_curve,
        waveform=waveform,
    )


def _compute_stem_activity(
    energy: EnergyAnalysis,
    downbeats: list[float],
    duration: float,
    stem_type: StemType,
) -> list[ActivitySpan]:
    """Detect where a stem is active (audible) based on its energy.

    Thresholds the per-bar total energy and merges consecutive active
    bars into ActivitySpan objects. Uses a lower threshold than the
    quick tier's pseudo-activity since we have a clean isolated stem.
    """
    bar_energies = energy.bar_energies_total
    if not bar_energies:
        return []

    max_e = max(bar_energies)
    if max_e <= 0:
        return []

    threshold = max_e * ACTIVITY_THRESHOLD
    active = [e > threshold for e in bar_energies]

    spans: list[ActivitySpan] = []
    span_start: int | None = None

    for i, is_active in enumerate(active):
        if is_active and span_start is None:
            span_start = i
        elif not is_active and span_start is not None:
            if i - span_start >= MIN_ACTIVITY_BARS:
                avg_energy = float(np.mean(bar_energies[span_start:i]))
                spans.append(ActivitySpan(
                    start=downbeats[span_start] if span_start < len(downbeats) else 0.0,
                    end=downbeats[i] if i < len(downbeats) else duration,
                    bar_start=span_start,
                    bar_end=i,
                    energy=avg_energy / max_e,
                    confidence=0.85,  # higher confidence from isolated stem
                ))
            span_start = None

    # Close final span
    if span_start is not None:
        n = len(active)
        if n - span_start >= MIN_ACTIVITY_BARS:
            avg_energy = float(np.mean(bar_energies[span_start:n]))
            spans.append(ActivitySpan(
                start=downbeats[span_start] if span_start < len(downbeats) else 0.0,
                end=downbeats[n] if n < len(downbeats) else duration,
                bar_start=span_start,
                bar_end=n,
                energy=avg_energy / max_e,
                confidence=0.85,
            ))

    return spans


def _normalize_energy_curve(bar_energies: list[float]) -> list[float]:
    """Normalize per-bar energy to 0-1 range."""
    if not bar_energies:
        return []
    max_e = max(bar_energies)
    if max_e <= 0:
        return [0.0] * len(bar_energies)
    return [round(e / max_e, 4) for e in bar_energies]


def _detect_drum_events(
    signal: np.ndarray,
    sr: int,
    beats: list[float],
    downbeats: list[float],
    sections: list,
) -> tuple[list, list[AtomicEvent]]:
    """Run percussion detection on the isolated drum stem.

    Uses multi-band onset detection (StemDrumDetector) — purpose-built for
    isolated stems from demucs separation. Supports multi-label detection
    (simultaneous kick+snare) and adaptive per-track thresholds.

    Returns:
        Tuple of (DrumPattern list, AtomicEvent list).
    """
    from ..detectors.percussion_stem import StemDrumDetector

    detector = StemDrumDetector()
    return detector.detect(signal, sr, beats, downbeats, sections)


def _detect_bass_events(
    signal: np.ndarray,
    sr: int,
    downbeats: list[float],
    onset_strength: np.ndarray,
) -> list[AtomicEvent]:
    """Detect bass note onsets from the isolated bass stem.

    Simple onset-based detection — identifies note attacks in the bass stem.
    """
    import librosa

    # Find onsets in the bass stem
    onset_frames = librosa.onset.onset_detect(
        y=signal, sr=sr, units="frames",
        backtrack=True, hop_length=512,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)

    events: list[AtomicEvent] = []
    for t in onset_times:
        bar_idx = _time_to_bar(t, downbeats)
        events.append(AtomicEvent(
            type="bass_note",
            timestamp=float(t),
            intensity=0.6,
            stem=StemType.BASS.value,
            bar_index=bar_idx,
            source="detector",
        ))

    return events


def _detect_vocal_events(
    signal: np.ndarray,
    sr: int,
    downbeats: list[float],
    onset_strength: np.ndarray,
) -> list[AtomicEvent]:
    """Detect vocal phrase onsets from the isolated vocal stem.

    Uses energy-based phrase detection — identifies when vocal energy
    rises above a threshold after silence.
    """
    import librosa

    # Compute RMS energy at a coarser resolution for phrase detection
    rms = librosa.feature.rms(y=signal, hop_length=512)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)

    if len(rms) == 0:
        return []

    # Threshold: vocal is "present" when RMS > 10% of max
    max_rms = float(np.max(rms))
    if max_rms <= 0:
        return []

    threshold = max_rms * 0.10
    is_active = rms > threshold

    # Find phrase onsets: transitions from inactive to active
    events: list[AtomicEvent] = []
    prev_active = False
    for i, active in enumerate(is_active):
        if active and not prev_active:
            t = float(times[i]) if i < len(times) else 0.0
            bar_idx = _time_to_bar(t, downbeats)
            events.append(AtomicEvent(
                type="vocal_onset",
                timestamp=t,
                intensity=float(rms[i]) / max_rms,
                stem=StemType.VOCALS.value,
                bar_index=bar_idx,
                source="detector",
            ))
        prev_active = bool(active)

    return events


def _detect_other_events(
    signal: np.ndarray,
    sr: int,
    downbeats: list[float],
    onset_strength: np.ndarray,
) -> list[AtomicEvent]:
    """Detect notable onsets in the 'other' stem (synths, keys, fx).

    Uses onset detection with a higher threshold to avoid noise.
    """
    import librosa

    onset_frames = librosa.onset.onset_detect(
        y=signal, sr=sr, units="frames",
        backtrack=True, hop_length=512,
        delta=0.15,  # higher delta to reduce noise
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)

    events: list[AtomicEvent] = []
    for t in onset_times:
        bar_idx = _time_to_bar(t, downbeats)
        events.append(AtomicEvent(
            type="synth_onset",
            timestamp=float(t),
            intensity=0.5,
            stem=StemType.OTHER.value,
            bar_index=bar_idx,
            source="detector",
        ))

    return events


def _time_to_bar(timestamp: float, downbeats: list[float]) -> int | None:
    """Find the bar index for a given timestamp."""
    if not downbeats:
        return None
    idx = int(np.searchsorted(downbeats, timestamp))
    if idx > 0:
        idx -= 1
    return min(idx, len(downbeats) - 1)


def detect_cross_stem_transitions(
    stems: list[StemAnalysis],
    downbeats: list[float],
    sections: list,
) -> list[ArrangementTransition]:
    """Detect transitions from cross-stem layer entries and exits.

    Identifies moments where stems begin or end activity, which
    represent arrangement changes (e.g., bass drops out in breakdown,
    vocals enter in verse).

    Args:
        stems: Per-stem analysis results.
        downbeats: Downbeat timestamps.
        sections: Section objects.

    Returns:
        List of ArrangementTransition objects.
    """
    transitions: list[ArrangementTransition] = []

    for stem in stems:
        for span in stem.activity:
            # Layer enter: start of an activity span
            section_label = _find_section_at(span.start, sections)
            transitions.append(ArrangementTransition(
                type=TransitionType.LAYER_ENTER,
                timestamp=span.start,
                bar_index=span.bar_start,
                section_label=section_label,
                layers_affected=[stem.stem_type],
                energy_delta=span.energy,
                description=f"{stem.stem_type} enters",
                confidence=span.confidence,
            ))

            # Layer exit: end of an activity span
            exit_label = _find_section_at(span.end, sections)
            transitions.append(ArrangementTransition(
                type=TransitionType.LAYER_EXIT,
                timestamp=span.end,
                bar_index=span.bar_end,
                section_label=exit_label,
                layers_affected=[stem.stem_type],
                energy_delta=-span.energy,
                description=f"{stem.stem_type} exits",
                confidence=span.confidence,
            ))

    # Sort by timestamp and deduplicate near-simultaneous transitions
    transitions.sort(key=lambda t: t.timestamp)
    return transitions


def _find_section_at(timestamp: float, sections: list) -> str:
    """Find the section label at a given timestamp."""
    for s in sections:
        if s.start <= timestamp < s.end:
            return s.label
    return ""
