"""Stem-aware drum event detector — multi-band onset detection for isolated stems.

Purpose-built for detecting kick, snare, and hi-hat events from demucs-separated
drum stems. Uses independent onset detection in three frequency bands, avoiding
the classification problem entirely. Supports multi-label detection (simultaneous
kick+snare) and adaptive per-track thresholds.

This does NOT implement DetectorProtocol — it takes a raw signal, not AudioFeatures.
The M7 PercussionHeuristicDetector remains the fallback for full-mix analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from ..models import Section
from .events import DrumPattern, load_detector_config

logger = logging.getLogger(__name__)

# Default frequency bands (Hz) for isolated drum stem classification.
# Narrower than full-mix bands because there's no competing content.
DEFAULT_BANDS: dict[str, tuple[int, int]] = {
    "kick": (20, 200),
    "snare": (200, 5000),
    "hihat": (5000, 16000),
}

# Default sensitivity multipliers (higher = fewer detections)
DEFAULT_SENSITIVITY: dict[str, float] = {
    "kick": 1.5,
    "snare": 1.5,
    "hihat": 2.0,
}

# Default minimum inter-onset interval (ms)
DEFAULT_MIN_IOI_MS: dict[str, float] = {
    "kick": 60,
    "snare": 60,
    "hihat": 30,
}

# Slots per bar (16th-note resolution)
SLOTS_PER_BAR = 16

# Maximum snap error before an onset is discarded (ms)
DEFAULT_MAX_SNAP_ERROR_MS = 25.0

# Number of bars to use for adaptive threshold computation
DEFAULT_ADAPTIVE_WINDOW_BARS = 8


@dataclass
class StemDrumConfig:
    """Configuration for the stem drum detector."""
    bands: dict[str, tuple[int, int]] = field(default_factory=lambda: dict(DEFAULT_BANDS))
    sensitivity: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SENSITIVITY))
    min_ioi_ms: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_MIN_IOI_MS))
    max_snap_error_ms: float = DEFAULT_MAX_SNAP_ERROR_MS
    adaptive_window_bars: int = DEFAULT_ADAPTIVE_WINDOW_BARS


def _load_stem_config() -> StemDrumConfig:
    """Load stem percussion config from detectors.yaml, with defaults."""
    try:
        detector_config = load_detector_config()
        raw = detector_config.params.get("stem_percussion", {})
    except Exception:
        raw = {}

    if not raw:
        return StemDrumConfig()

    bands = {}
    for name, default in DEFAULT_BANDS.items():
        raw_band = raw.get("bands", {}).get(name, list(default))
        bands[name] = (int(raw_band[0]), int(raw_band[1]))

    sensitivity = {}
    for name, default in DEFAULT_SENSITIVITY.items():
        sensitivity[name] = float(raw.get("sensitivity", {}).get(name, default))

    min_ioi_ms = {}
    for name, default in DEFAULT_MIN_IOI_MS.items():
        min_ioi_ms[name] = float(raw.get("min_ioi_ms", {}).get(name, default))

    return StemDrumConfig(
        bands=bands,
        sensitivity=sensitivity,
        min_ioi_ms=min_ioi_ms,
        max_snap_error_ms=float(raw.get("max_snap_error_ms", DEFAULT_MAX_SNAP_ERROR_MS)),
        adaptive_window_bars=int(raw.get("adaptive_window_bars", DEFAULT_ADAPTIVE_WINDOW_BARS)),
    )


class StemDrumDetector:
    """Drum event detector optimized for isolated drum stems.

    Uses multi-band onset detection: computes STFT once, extracts sub-band
    spectral flux in three frequency bands, and runs independent peak detection
    on each band. This naturally handles simultaneous hits (kick+snare) and
    avoids the mutual-exclusion problem of single-pass classification.

    Produces both DrumPattern objects (for pattern discovery downstream) and
    AtomicEvent objects (for arrangement timeline).
    """

    name: str = "stem_multiband"
    event_types: list[str] = ["kick", "snare", "hihat"]

    def __init__(self, config: StemDrumConfig | None = None) -> None:
        self._config = config or _load_stem_config()

    def detect(
        self,
        signal: np.ndarray,
        sr: int,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
    ) -> tuple[list[DrumPattern], list["AtomicEvent"]]:
        """Detect drum events from an isolated drum stem.

        Args:
            signal: Mono audio signal (numpy array).
            sr: Sample rate.
            beats: Beat timestamps in seconds.
            downbeats: Downbeat timestamps in seconds.
            sections: Section objects for pattern grouping.

        Returns:
            Tuple of (DrumPattern list, AtomicEvent list).
        """
        from ..strata.models import AtomicEvent, StemType

        if not beats or not downbeats or len(signal) == 0:
            logger.warning("No beats/downbeats or empty signal — skipping stem drum detection")
            return [], []

        # Compute STFT once — shared across all bands.
        # Use librosa.stft with center=True for proper time alignment
        # (zero-pads so frame 0 is centered at t=0).
        import librosa

        n_fft = 2048
        hop_length = 512
        S = np.abs(librosa.stft(signal, n_fft=n_fft, hop_length=hop_length, center=True))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        # Compute 16th-note duration
        avg_beat_dur = (beats[-1] - beats[0]) / (len(beats) - 1) if len(beats) >= 2 else 0.5
        sixteenth_dur = avg_beat_dur / 4.0

        # Detect onsets per band
        band_onsets: dict[str, list[dict]] = {}
        for drum_type, (lo, hi) in self._config.bands.items():
            band_onsets[drum_type] = self._detect_band_onsets(
                S, freqs, sr, hop_length, drum_type, lo, hi, downbeats,
            )

        # Build DrumPattern objects by snapping onsets to grid
        patterns = self._build_patterns(
            band_onsets, downbeats, beats, sixteenth_dur, sections,
        )

        # Build AtomicEvent list
        events: list[AtomicEvent] = []
        for drum_type, onsets in band_onsets.items():
            for onset in onsets:
                bar_idx, slot, snap_error = _snap_to_grid(
                    onset["time"], downbeats, sixteenth_dur,
                )
                if snap_error > self._config.max_snap_error_ms:
                    continue

                intensity_map = {"kick": 0.8, "snare": 0.7, "hihat": 0.5}
                events.append(AtomicEvent(
                    type=drum_type,
                    timestamp=onset["time"],
                    intensity=intensity_map.get(drum_type, 0.5) * onset["strength"],
                    stem=StemType.DRUMS.value,
                    beat_position=slot,
                    bar_index=bar_idx,
                    confidence=max(0.0, 1.0 - snap_error / self._config.max_snap_error_ms),
                    source="detector",
                    payload={"snap_error_ms": round(snap_error, 2)},
                ))

        events.sort(key=lambda e: e.timestamp)

        total_per_type = {dt: len(ons) for dt, ons in band_onsets.items()}
        logger.info(
            "Stem drum detection: %d patterns, %s across %d bars",
            len(patterns), total_per_type, len(downbeats),
        )

        return patterns, events

    def _detect_band_onsets(
        self,
        S: np.ndarray,
        freqs: np.ndarray,
        sr: int,
        hop_length: int,
        drum_type: str,
        lo: int,
        hi: int,
        downbeats: list[float],
    ) -> list[dict]:
        """Detect onsets in a single frequency band.

        Uses sub-band spectral flux (half-wave rectified frame difference)
        with adaptive thresholding and peak picking.
        """
        # Extract sub-band spectrogram
        # S shape from librosa.stft: (n_freq_bins, n_frames)
        mask = (freqs >= lo) & (freqs < hi)
        if not mask.any():
            return []

        S_band = S[mask, :]  # (n_band_bins, n_frames)

        # Sub-band spectral flux: half-wave rectified frame-to-frame difference
        # diff along time axis (axis=1), then sum across frequency bins
        flux = np.sum(np.maximum(0, np.diff(S_band, axis=1)), axis=0)
        flux = np.concatenate([[0], flux])  # pad to match frame count

        if flux.max() <= 0:
            return []

        # Normalize flux to 0–1
        flux = flux / flux.max()

        # Adaptive threshold from first N bars
        threshold = self._compute_adaptive_threshold(
            flux, sr, hop_length, downbeats, drum_type,
        )

        # Minimum inter-onset interval in frames
        min_ioi_ms = self._config.min_ioi_ms.get(drum_type, 60)
        min_distance = max(1, int(min_ioi_ms / 1000.0 * sr / hop_length))

        # Peak picking
        peaks, props = find_peaks(
            flux,
            height=threshold,
            distance=min_distance,
        )

        if len(peaks) == 0:
            return []

        # Convert to onset dicts
        import librosa  # noqa: F811
        onset_times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)
        peak_heights = props["peak_heights"]

        # Normalize strengths relative to max peak
        max_height = peak_heights.max()
        strengths = peak_heights / max_height if max_height > 0 else peak_heights

        return [
            {"time": float(t), "strength": float(s)}
            for t, s in zip(onset_times, strengths)
        ]

    def _compute_adaptive_threshold(
        self,
        flux: np.ndarray,
        sr: int,
        hop_length: int,
        downbeats: list[float],
        drum_type: str,
    ) -> float:
        """Compute an adaptive detection threshold from the first N bars.

        Uses median + sensitivity * std of the flux in the calibration window.
        Falls back to a global threshold if not enough bars.
        """
        sensitivity = self._config.sensitivity.get(drum_type, 1.5)
        n_bars = min(self._config.adaptive_window_bars, len(downbeats) - 1)

        if n_bars >= 2:
            end_time = downbeats[n_bars]
            end_frame = min(int(end_time * sr / hop_length), len(flux))
            cal_flux = flux[:end_frame]
        else:
            cal_flux = flux

        if len(cal_flux) == 0:
            return 0.15

        threshold = float(np.median(cal_flux) + sensitivity * np.std(cal_flux))
        # Floor: never go below 0.1 to avoid noise
        return max(threshold, 0.10)

    def _build_patterns(
        self,
        band_onsets: dict[str, list[dict]],
        downbeats: list[float],
        beats: list[float],
        sixteenth_dur: float,
        sections: list[Section],
    ) -> list[DrumPattern]:
        """Build DrumPattern objects by snapping detected onsets to the 16th-note grid.

        Groups into patterns at 4-bar boundaries or section boundaries,
        matching the M7 heuristic's grouping logic.
        """
        if not downbeats:
            return []

        n_bars = len(downbeats)

        # Pre-compute per-bar per-slot hits for each drum type
        bar_slots: dict[str, dict[int, list[int]]] = {
            dt: {} for dt in ["kick", "snare", "hihat"]
        }

        # Also track hihat spectral info for open/closed classification
        hihat_onset_count = 0
        hihat_open_count = 0

        for drum_type, onsets in band_onsets.items():
            for onset in onsets:
                bar_idx, slot, snap_error = _snap_to_grid(
                    onset["time"], downbeats, sixteenth_dur,
                )
                if snap_error > self._config.max_snap_error_ms:
                    continue
                if bar_idx < 0 or bar_idx >= n_bars:
                    continue

                if bar_idx not in bar_slots[drum_type]:
                    bar_slots[drum_type][bar_idx] = [0] * SLOTS_PER_BAR
                bar_slots[drum_type][bar_idx][slot] = 1

                if drum_type == "hihat":
                    hihat_onset_count += 1

        # Group bars into patterns (4-bar chunks or at section boundaries)
        patterns: list[DrumPattern] = []
        pattern_start = 0

        for bar_idx in range(n_bars):
            bars_in_pattern = bar_idx - pattern_start + 1
            is_last_bar = bar_idx == n_bars - 1
            at_section_boundary = bars_in_pattern >= 2 and _at_section_boundary(
                downbeats[bar_idx] if bar_idx < len(downbeats) else 0.0,
                sections,
                sixteenth_dur,
            )

            if bars_in_pattern >= 4 or is_last_bar or at_section_boundary:
                # Collect slot arrays for this pattern range
                kick_slots: list[int] = []
                snare_slots: list[int] = []
                clap_slots: list[int] = []  # empty — snare subsumes clap on isolated stems

                hihat_hits_in_pattern = 0
                hihat_total_slots = 0

                for b in range(pattern_start, bar_idx + 1):
                    kick_slots.extend(bar_slots["kick"].get(b, [0] * SLOTS_PER_BAR))
                    snare_slots.extend(bar_slots["snare"].get(b, [0] * SLOTS_PER_BAR))
                    clap_slots.extend([0] * SLOTS_PER_BAR)

                    hihat_bar = bar_slots["hihat"].get(b, [0] * SLOTS_PER_BAR)
                    hihat_hits_in_pattern += sum(hihat_bar)
                    hihat_total_slots += SLOTS_PER_BAR

                # Hi-hat metadata
                hihat_density = hihat_hits_in_pattern / max(hihat_total_slots, 1)
                hihat_type = _classify_hihat_type(hihat_density)

                # Confidence from pattern conventions
                conf = _pattern_confidence(
                    kick_slots, snare_slots,
                    _get_section_at(
                        downbeats[pattern_start] if pattern_start < len(downbeats) else 0.0,
                        sections,
                    ),
                )

                patterns.append(DrumPattern(
                    bar_start=pattern_start,
                    bar_end=bar_idx + 1,
                    kick=kick_slots,
                    snare=snare_slots,
                    clap=clap_slots,
                    hihat_type=hihat_type,
                    hihat_density=round(hihat_density, 3),
                    hihat_open_ratio=0.0,  # TODO: spectral centroid classification
                    confidence=round(conf, 3),
                ))

                pattern_start = bar_idx + 1

        return patterns


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _snap_to_grid(
    onset_time: float,
    downbeats: list[float],
    sixteenth_dur: float,
) -> tuple[int, int, float]:
    """Snap an onset to the nearest 16th-note slot.

    Returns:
        (bar_index, slot_index 0-15, snap_error_ms)
    """
    if not downbeats:
        return 0, 0, 0.0

    # Find the bar this onset falls in
    bar_idx = int(np.searchsorted(downbeats, onset_time)) - 1
    bar_idx = max(0, min(bar_idx, len(downbeats) - 1))

    bar_time = downbeats[bar_idx]
    offset = onset_time - bar_time

    slot = round(offset / sixteenth_dur) if sixteenth_dur > 0 else 0
    slot = max(0, min(slot, SLOTS_PER_BAR - 1))

    snapped_time = bar_time + slot * sixteenth_dur
    snap_error_ms = abs(onset_time - snapped_time) * 1000

    return bar_idx, slot, snap_error_ms


def _at_section_boundary(
    bar_time: float,
    sections: list[Section],
    tolerance: float,
) -> bool:
    """Check if a bar time is near a section boundary."""
    for s in sections:
        if abs(bar_time - s.start) < tolerance or abs(bar_time - s.end) < tolerance:
            return True
    return False


def _classify_hihat_type(density: float) -> str:
    """Classify hi-hat pattern type from hit density."""
    if density < 0.05:
        return "none"
    elif density < 0.2:
        return "offbeat"
    elif density < 0.4:
        return "8ths"
    elif density < 0.7:
        return "16ths"
    else:
        return "roll"


def _get_section_at(time: float, sections: list[Section]) -> str:
    """Get the section label at a given timestamp."""
    for s in sections:
        if s.start <= time < s.end:
            return s.label
    return "unknown"


def _pattern_confidence(
    kick: list[int],
    snare: list[int],
    section_label: str,
) -> float:
    """Compute confidence for a percussion pattern.

    Same convention-based scoring as the M7 heuristic but with higher
    base confidence (isolated stem = more reliable).
    """
    conf = 0.6  # higher base than M7's 0.5 — cleaner signal

    if not kick:
        return conf

    bars = len(kick) // SLOTS_PER_BAR
    if bars == 0:
        return conf

    # 4-on-the-floor kick check
    four_on_floor_hits = 0
    four_on_floor_total = 0
    for bar in range(bars):
        offset = bar * SLOTS_PER_BAR
        for beat_slot in [0, 4, 8, 12]:
            idx = offset + beat_slot
            if idx < len(kick):
                four_on_floor_total += 1
                if kick[idx]:
                    four_on_floor_hits += 1

    if four_on_floor_total > 0 and four_on_floor_hits / four_on_floor_total > 0.7:
        conf += 0.2

    # Snare on 2 and 4 check
    snare_backbeat = 0
    snare_backbeat_total = 0
    for bar in range(bars):
        offset = bar * SLOTS_PER_BAR
        for beat_slot in [4, 12]:
            idx = offset + beat_slot
            if idx < len(snare):
                snare_backbeat_total += 1
                if snare[idx]:
                    snare_backbeat += 1

    if snare_backbeat_total > 0 and snare_backbeat / snare_backbeat_total > 0.5:
        conf += 0.1

    # Section prior
    section_boost = {
        "drop": 0.1,
        "build": 0.05,
        "verse": 0.0,
        "breakdown": -0.05,
        "intro": -0.05,
        "outro": -0.05,
    }
    conf += section_boost.get(section_label, 0.0)

    return max(0.0, min(1.0, conf))
