"""Transition detection for the quick tier.

Detects arrangement transitions at section boundaries by analyzing
energy deltas, onset density changes, and band-level shifts.
"""

from __future__ import annotations

import logging

import numpy as np

from ..models import Section
from .energy import EnergyAnalysis, compute_energy_trend
from .models import ArrangementTransition, StemType, TransitionType

logger = logging.getLogger(__name__)


def detect_transitions(
    sections: list[Section],
    energy: EnergyAnalysis,
    downbeats: list[float],
    energy_threshold: float = 0.15,
) -> list[ArrangementTransition]:
    """Detect arrangement transitions at section boundaries.

    Analyzes the energy change across each section boundary and
    classifies the transition type based on direction and magnitude.

    Args:
        sections: Track sections from analysis.
        energy: Per-bar energy analysis.
        downbeats: Downbeat timestamps.
        energy_threshold: Minimum energy delta to flag a transition.

    Returns:
        List of ArrangementTransition objects sorted by timestamp.
    """
    if len(sections) < 2 or not energy.bar_energies_total:
        return []

    n_bars = len(energy.bar_energies_total)
    transitions: list[ArrangementTransition] = []

    for i in range(1, len(sections)):
        prev_section = sections[i - 1]
        curr_section = sections[i]
        boundary_time = curr_section.start

        # Find the bar index closest to this boundary
        bar_idx = _time_to_bar(boundary_time, downbeats)
        if bar_idx is None or bar_idx >= n_bars:
            continue

        # Compute energy deltas across the boundary (2 bars before vs 2 bars after)
        window = 2
        before_start = max(0, bar_idx - window)
        after_end = min(n_bars, bar_idx + window)

        if before_start >= bar_idx or bar_idx >= after_end:
            continue

        before_total = float(np.mean(energy.bar_energies_total[before_start:bar_idx]))
        after_total = float(np.mean(energy.bar_energies_total[bar_idx:after_end]))

        # Normalize delta to -1..+1 range
        max_energy = max(energy.bar_energies_total) if max(energy.bar_energies_total) > 0 else 1.0
        energy_delta = (after_total - before_total) / max_energy

        # Per-band deltas for layer attribution
        before_low = float(np.mean(energy.bar_energies_low[before_start:bar_idx]))
        after_low = float(np.mean(energy.bar_energies_low[bar_idx:after_end]))
        before_mid = float(np.mean(energy.bar_energies_mid[before_start:bar_idx]))
        after_mid = float(np.mean(energy.bar_energies_mid[bar_idx:after_end]))
        before_high = float(np.mean(energy.bar_energies_high[before_start:bar_idx]))
        after_high = float(np.mean(energy.bar_energies_high[bar_idx:after_end]))

        low_delta = (after_low - before_low) / max_energy
        mid_delta = (after_mid - before_mid) / max_energy
        high_delta = (after_high - before_high) / max_energy

        # Skip if below threshold
        if abs(energy_delta) < energy_threshold:
            continue

        # Classify transition type
        transition_type, description, layers = _classify_transition(
            prev_section.label, curr_section.label,
            energy_delta, low_delta, mid_delta, high_delta,
        )

        transitions.append(ArrangementTransition(
            type=transition_type,
            timestamp=boundary_time,
            bar_index=bar_idx,
            section_label=curr_section.label,
            layers_affected=layers,
            energy_delta=round(energy_delta, 3),
            description=description,
            confidence=min(1.0, abs(energy_delta) * 2),
        ))

    # Also detect within-section transitions from onset density spikes
    fill_transitions = _detect_fills(energy, downbeats, sections)
    transitions.extend(fill_transitions)

    transitions.sort(key=lambda t: t.timestamp)
    logger.info("Detected %d transitions (%d at boundaries, %d fills)",
                len(transitions), len(transitions) - len(fill_transitions), len(fill_transitions))
    return transitions


def _time_to_bar(timestamp: float, downbeats: list[float]) -> int | None:
    """Find the bar index closest to a timestamp."""
    if not downbeats:
        return None
    # Binary search
    idx = int(np.searchsorted(downbeats, timestamp))
    if idx >= len(downbeats):
        return len(downbeats) - 1
    if idx > 0 and abs(downbeats[idx - 1] - timestamp) < abs(downbeats[idx] - timestamp):
        return idx - 1
    return idx


def _classify_transition(
    prev_label: str,
    curr_label: str,
    energy_delta: float,
    low_delta: float,
    mid_delta: float,
    high_delta: float,
) -> tuple[TransitionType, str, list[str]]:
    """Classify a transition based on section context and energy changes."""
    layers: list[str] = []
    parts: list[str] = []

    # Track which bands changed significantly
    if abs(low_delta) > 0.1:
        layers.append(StemType.BASS.value)
        if low_delta > 0:
            parts.append("bass enters")
        else:
            parts.append("bass drops")

    if abs(mid_delta) > 0.1:
        layers.append(StemType.OTHER.value)
        if mid_delta > 0:
            parts.append("mid-range enters")
        else:
            parts.append("mid-range drops")

    if abs(high_delta) > 0.1:
        if high_delta > 0:
            parts.append("highs enter")
        else:
            parts.append("highs drop")

    # Classify by section transition pattern
    if curr_label in ("drop",) and energy_delta > 0.2:
        t_type = TransitionType.DROP_IMPACT
        if not parts:
            parts.append("drop impact")
    elif curr_label in ("breakdown",) and energy_delta < -0.2:
        t_type = TransitionType.BREAKDOWN
        if not parts:
            parts.append("breakdown")
    elif energy_delta > 0.15 and len(layers) >= 2:
        t_type = TransitionType.LAYER_ENTER
    elif energy_delta < -0.15 and len(layers) >= 2:
        t_type = TransitionType.LAYER_EXIT
    elif energy_delta > 0:
        t_type = TransitionType.ENERGY_SHIFT
        if not parts:
            parts.append("energy rises")
    else:
        t_type = TransitionType.ENERGY_SHIFT
        if not parts:
            parts.append("energy falls")

    description = ", ".join(parts) if parts else f"{prev_label} → {curr_label}"
    return t_type, description, layers


def _detect_fills(
    energy: EnergyAnalysis,
    downbeats: list[float],
    sections: list[Section],
) -> list[ArrangementTransition]:
    """Detect fill-like transitions from onset density spikes.

    A fill is a bar where onset density is significantly higher than
    its neighbors, typically just before a section boundary.
    """
    if not energy.bar_onset_density or len(downbeats) < 3:
        return []

    fills: list[ArrangementTransition] = []
    densities = energy.bar_onset_density
    n = len(densities)

    if n < 5:
        return []

    mean_density = float(np.mean(densities))
    if mean_density == 0:
        return []

    for bar_idx in range(2, n - 1):
        # Check for spike: this bar >> neighbors
        local_avg = float(np.mean(densities[max(0, bar_idx - 3):bar_idx]))
        if local_avg == 0:
            continue

        spike_ratio = densities[bar_idx] / local_avg
        if spike_ratio < 1.8:
            continue

        # Check if this bar is near a section boundary (within 2 bars)
        bar_time = downbeats[bar_idx] if bar_idx < len(downbeats) else 0.0
        near_boundary = False
        section_label = ""
        for section in sections:
            if abs(section.end - bar_time) < 5.0:  # within ~2 bars at 120bpm
                near_boundary = True
                section_label = section.label
                break

        if not near_boundary:
            continue

        fills.append(ArrangementTransition(
            type=TransitionType.FILL,
            timestamp=bar_time,
            bar_index=bar_idx,
            section_label=section_label,
            description=f"fill before {section_label} boundary",
            energy_delta=0.0,
            confidence=min(1.0, (spike_ratio - 1.0) / 2.0),
        ))

    return fills


def compute_section_energy(
    section: Section,
    energy: EnergyAnalysis,
    downbeats: list[float],
) -> tuple[float, str]:
    """Compute average energy and trend for a section.

    Returns: (energy_level 0-1, trend string)
    """
    if not energy.bar_energies_total or not downbeats:
        return 0.5, "stable"

    start_bar = _time_to_bar(section.start, downbeats)
    end_bar = _time_to_bar(section.end, downbeats)
    if start_bar is None or end_bar is None:
        return 0.5, "stable"

    end_bar = min(end_bar, len(energy.bar_energies_total))
    start_bar = min(start_bar, end_bar)

    if start_bar >= end_bar:
        return 0.5, "stable"

    section_energies = energy.bar_energies_total[start_bar:end_bar]
    max_total = max(energy.bar_energies_total) if max(energy.bar_energies_total) > 0 else 1.0
    avg_energy = float(np.mean(section_energies)) / max_total
    trend = compute_energy_trend(energy.overall_energy_curve[start_bar:end_bar])

    return round(avg_energy, 3), trend
