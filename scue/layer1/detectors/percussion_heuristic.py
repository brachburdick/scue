"""Heuristic percussion detector — beat-synchronous slot classification.

Classifies percussion at 16th-note resolution using sub-band energy analysis,
onset strength, spectral centroid, and section-aware priors. Produces compact
DrumPattern objects instead of individual MusicalEvent instances.

This is the baseline strategy. The Random Forest strategy (percussion_rf.py)
uses the same slot classification but replaces threshold rules with a trained
model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from ..models import Section
from .events import DetectorConfig, DetectorResult, DrumPattern
from .features import AudioFeatures

logger = logging.getLogger(__name__)


# Sub-band frequency ranges (Hz) for percussion classification
KICK_BAND = (20, 150)
SNARE_BAND = (150, 1000)
HIHAT_BAND = (4000, 16000)
CLAP_BAND = (1000, 4000)

# Slots per bar (16th-note resolution)
SLOTS_PER_BAR = 16


@dataclass
class SlotFeatures:
    """Feature vector for a single 16th-note slot."""
    kick_energy: float       # sub-band energy in kick range
    snare_energy: float      # sub-band energy in snare range
    clap_energy: float       # sub-band energy in clap range
    hihat_energy: float      # sub-band energy in hihat range
    onset_strength: float    # onset strength at this slot
    spectral_centroid: float # centroid at this slot
    beat_position: int       # 0-15 position within the bar
    is_downbeat: bool        # True if slot 0


class PercussionHeuristicDetector:
    """Heuristic beat-synchronous percussion detector.

    Implements DetectorProtocol. Classifies each 16th-note slot as containing
    kick, snare, clap, or nothing, based on sub-band energy thresholds.
    Hi-hat is detected at the pattern level (type, density, open_ratio).
    """

    name: str = "heuristic"
    event_types: list[str] = ["kick", "snare", "clap", "hihat"]

    def detect(
        self,
        features: AudioFeatures,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult:
        """Run heuristic percussion detection.

        Args:
            features: Extracted audio features (must include y_percussive from HPSS).
            beats: Beat timestamps in seconds.
            downbeats: Downbeat timestamps in seconds.
            sections: Section labels for section-aware priors.
            config: Detector configuration with thresholds.

        Returns:
            DetectorResult with DrumPattern objects.
        """
        if not beats or not downbeats:
            logger.warning("No beats/downbeats available — skipping percussion detection")
            return DetectorResult(metadata={"skipped": "no_beatgrid"})

        params = config.params.get("heuristic", {})
        kick_thresh = params.get("kick_low_band_threshold", 0.6)
        snare_thresh = params.get("snare_mid_band_threshold", 0.5)
        hihat_thresh = params.get("hihat_high_band_threshold", 0.4)

        # Use percussive component if available (HPSS), else fall back to full signal
        signal = features.y_percussive if features.y_percussive is not None else features.signal
        sr = features.sr

        # Compute sub-band energies via STFT
        n_fft = 2048
        hop = features.hop_length
        S = np.abs(np.fft.rfft(
            np.lib.stride_tricks.sliding_window_view(signal, n_fft)[::hop],
            axis=1,
        ))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

        # Build band masks
        kick_mask = (freqs >= KICK_BAND[0]) & (freqs < KICK_BAND[1])
        snare_mask = (freqs >= SNARE_BAND[0]) & (freqs < SNARE_BAND[1])
        clap_mask = (freqs >= CLAP_BAND[0]) & (freqs < CLAP_BAND[1])
        hihat_mask = (freqs >= HIHAT_BAND[0]) & (freqs < HIHAT_BAND[1])

        # Sub-band energy per frame
        kick_energy = S[:, kick_mask].mean(axis=1) if kick_mask.any() else np.zeros(S.shape[0])
        snare_energy = S[:, snare_mask].mean(axis=1) if snare_mask.any() else np.zeros(S.shape[0])
        clap_energy = S[:, clap_mask].mean(axis=1) if clap_mask.any() else np.zeros(S.shape[0])
        hihat_energy = S[:, hihat_mask].mean(axis=1) if hihat_mask.any() else np.zeros(S.shape[0])

        # Normalize per-band to 0-1
        for arr in [kick_energy, snare_energy, clap_energy, hihat_energy]:
            mx = arr.max()
            if mx > 0:
                arr /= mx

        # Compute 16th-note timestamps from downbeats
        avg_beat_dur = (beats[-1] - beats[0]) / (len(beats) - 1) if len(beats) >= 2 else 0.5
        sixteenth_dur = avg_beat_dur / 4.0

        # Build patterns per bar
        patterns: list[DrumPattern] = []
        current_pattern_start = 0
        current_kick: list[int] = []
        current_snare: list[int] = []
        current_clap: list[int] = []
        hihat_hits = 0
        hihat_total_slots = 0
        hihat_open_count = 0

        for bar_idx, bar_time in enumerate(downbeats):
            bar_kick: list[int] = []
            bar_snare: list[int] = []
            bar_clap: list[int] = []

            for slot in range(SLOTS_PER_BAR):
                slot_time = bar_time + slot * sixteenth_dur
                # Map slot_time to frame index
                frame = int(slot_time * sr / hop)
                frame = min(frame, len(kick_energy) - 1)

                if frame < 0:
                    bar_kick.append(0)
                    bar_snare.append(0)
                    bar_clap.append(0)
                    continue

                # Get energies at this frame
                ke = kick_energy[frame]
                se = snare_energy[frame]
                ce = clap_energy[frame]
                he = hihat_energy[frame]

                # Apply onset strength gating — only classify if there's an onset
                onset_frame = min(frame, len(features.onset_strength) - 1)
                onset_val = features.onset_strength[onset_frame]
                onset_mean = features.onset_strength.mean()
                has_onset = onset_val > onset_mean * 0.5

                # Classify
                bar_kick.append(1 if has_onset and ke > kick_thresh else 0)
                bar_snare.append(1 if has_onset and se > snare_thresh and ke < kick_thresh else 0)
                bar_clap.append(1 if has_onset and ce > snare_thresh and se < snare_thresh else 0)

                # Hi-hat counting
                hihat_total_slots += 1
                if has_onset and he > hihat_thresh:
                    hihat_hits += 1
                    # Estimate open vs closed: higher spectral centroid = more open
                    centroid_frame = min(frame, len(features.spectral_centroid) - 1)
                    if features.spectral_centroid[centroid_frame] > 8000:
                        hihat_open_count += 1

            current_kick.extend(bar_kick)
            current_snare.extend(bar_snare)
            current_clap.extend(bar_clap)

            # Check if we should close the current pattern (every 4 bars or end)
            bars_in_pattern = bar_idx - current_pattern_start + 1
            is_last_bar = bar_idx == len(downbeats) - 1
            at_section_boundary = any(
                abs(bar_time - s.start) < sixteenth_dur or abs(bar_time - s.end) < sixteenth_dur
                for s in sections
            ) and bars_in_pattern >= 2

            if bars_in_pattern >= 4 or is_last_bar or at_section_boundary:
                # Classify hi-hat pattern for this group
                if hihat_total_slots > 0:
                    density = hihat_hits / hihat_total_slots
                    open_ratio = hihat_open_count / max(hihat_hits, 1)
                else:
                    density = 0.0
                    open_ratio = 0.0

                hihat_type = _classify_hihat_type(density)

                # Compute pattern confidence from section context
                section_label = _get_section_at(bar_time, sections)
                conf = _pattern_confidence(
                    current_kick, current_snare, section_label,
                )

                patterns.append(DrumPattern(
                    bar_start=current_pattern_start,
                    bar_end=bar_idx + 1,
                    kick=current_kick,
                    snare=current_snare,
                    clap=current_clap,
                    hihat_type=hihat_type,
                    hihat_density=round(density, 3),
                    hihat_open_ratio=round(open_ratio, 3),
                    confidence=round(conf, 3),
                ))

                # Reset for next pattern
                current_pattern_start = bar_idx + 1
                current_kick = []
                current_snare = []
                current_clap = []
                hihat_hits = 0
                hihat_total_slots = 0
                hihat_open_count = 0

        total_kicks = sum(sum(p.kick) for p in patterns)
        total_snares = sum(sum(p.snare) for p in patterns)
        total_claps = sum(sum(p.clap) for p in patterns)
        logger.info(
            "Heuristic percussion: %d patterns, %d kicks, %d snares, %d claps across %d bars",
            len(patterns), total_kicks, total_snares, total_claps, len(downbeats),
        )

        return DetectorResult(
            patterns=patterns,
            metadata={
                "strategy": "heuristic",
                "total_bars": len(downbeats),
                "total_patterns": len(patterns),
                "total_kicks": total_kicks,
                "total_snares": total_snares,
                "total_claps": total_claps,
                "thresholds": {
                    "kick": kick_thresh,
                    "snare": snare_thresh,
                    "hihat": hihat_thresh,
                },
            },
        )


def _classify_hihat_type(density: float) -> str:
    """Classify hi-hat pattern type from hit density."""
    if density < 0.05:
        return "none"
    elif density < 0.2:
        return "offbeat"    # sparse, likely offbeat 8ths
    elif density < 0.4:
        return "8ths"       # typical 8th-note pattern
    elif density < 0.7:
        return "16ths"      # busy 16th-note pattern
    else:
        return "roll"       # very dense, probably rolls


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

    Higher confidence for patterns that match common EDM conventions:
    - Kicks on beats 1 and 3 (slots 0, 8 in 16th-note grid)
    - Snares on beats 2 and 4 (slots 4, 12)
    - Drop sections expected to have strong kick patterns
    """
    conf = 0.5  # base

    if not kick:
        return conf

    bars = len(kick) // SLOTS_PER_BAR
    if bars == 0:
        return conf

    # Check for 4-on-the-floor kick pattern (common in EDM)
    four_on_floor_hits = 0
    four_on_floor_total = 0
    for bar in range(bars):
        offset = bar * SLOTS_PER_BAR
        for beat_slot in [0, 4, 8, 12]:  # quarter-note positions
            idx = offset + beat_slot
            if idx < len(kick):
                four_on_floor_total += 1
                if kick[idx]:
                    four_on_floor_hits += 1

    if four_on_floor_total > 0:
        four_ratio = four_on_floor_hits / four_on_floor_total
        if four_ratio > 0.7:
            conf += 0.2  # strong 4otf pattern

    # Check snare on 2 and 4
    snare_backbeat = 0
    snare_backbeat_total = 0
    for bar in range(bars):
        offset = bar * SLOTS_PER_BAR
        for beat_slot in [4, 12]:  # beats 2 and 4
            idx = offset + beat_slot
            if idx < len(snare):
                snare_backbeat_total += 1
                if snare[idx]:
                    snare_backbeat += 1

    if snare_backbeat_total > 0 and snare_backbeat / snare_backbeat_total > 0.5:
        conf += 0.1

    # Section prior
    section_boost = {
        "drop": 0.15,
        "build": 0.05,
        "verse": 0.0,
        "breakdown": -0.1,
        "intro": -0.05,
        "outro": -0.1,
    }
    conf += section_boost.get(section_label, 0.0)

    return max(0.0, min(1.0, conf))
