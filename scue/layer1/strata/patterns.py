"""Pattern discovery for the quick tier.

Converts M7 DrumPattern objects into Strata Pattern objects, detects
repetition across bars, and auto-generates descriptive names.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict

import numpy as np

from ..detectors.events import DrumPattern as M7DrumPattern
from .models import (
    AtomicEvent,
    Pattern,
    PatternInstance,
    PatternTemplate,
    PatternType,
    StemType,
)

logger = logging.getLogger(__name__)


def discover_patterns(
    drum_patterns: list[M7DrumPattern],
    downbeats: list[float],
    beats: list[float],
    similarity_threshold: float = 0.85,
    min_repeats: int = 2,
) -> list[Pattern]:
    """Discover repeating patterns from M7 drum pattern data.

    Converts M7 DrumPatterns into Strata Patterns by:
    1. Extracting per-bar slot vectors from each DrumPattern
    2. Comparing bars for similarity (cosine similarity)
    3. Grouping identical/near-identical bars into Pattern instances
    4. Auto-naming based on content

    Args:
        drum_patterns: M7 drum patterns from TrackAnalysis.
        downbeats: Downbeat timestamps.
        beats: Beat timestamps.
        similarity_threshold: Cosine similarity threshold for "same pattern".
        min_repeats: Minimum instances to call it a pattern.

    Returns:
        List of discovered Pattern objects.
    """
    if not drum_patterns or not downbeats:
        return []

    # Step 1: Extract per-bar slot vectors
    bar_vectors = _extract_bar_vectors(drum_patterns)
    if not bar_vectors:
        return []

    # Step 2: Cluster bars by similarity
    clusters = _cluster_bars(bar_vectors, similarity_threshold)

    # Step 3: Convert clusters to Patterns
    patterns: list[Pattern] = []
    pattern_idx = 0

    for cluster_bars in clusters:
        if len(cluster_bars) < min_repeats:
            continue

        # Build the template from the first bar in the cluster
        first_bar = cluster_bars[0]
        vector = bar_vectors[first_bar]
        template_events = _vector_to_events(vector)
        signature = _compute_signature(vector)
        name = _auto_name(vector)

        # Compute bar duration
        if first_bar + 1 < len(downbeats):
            bar_duration = downbeats[first_bar + 1] - downbeats[first_bar]
        elif len(beats) >= 5:
            bar_duration = (beats[-1] - beats[0]) / (len(beats) - 1) * 4
        else:
            bar_duration = 2.0  # fallback

        template = PatternTemplate(
            events=template_events,
            duration_bars=1,
            duration_seconds=bar_duration,
            signature=signature,
        )

        # Build instances — merge consecutive bars
        instances = _merge_consecutive_bars(
            cluster_bars, downbeats, len(downbeats) - 1, bar_vectors, vector,
        )

        pattern_id = f"drum-{pattern_idx:02d}-{signature[:8]}"
        patterns.append(Pattern(
            id=pattern_id,
            name=name,
            pattern_type=PatternType.DRUM_GROOVE,
            stem=StemType.DRUMS.value,
            template=template,
            instances=instances,
            tags=_compute_tags(vector),
        ))
        pattern_idx += 1

    logger.info("Discovered %d drum patterns from %d bars", len(patterns), len(bar_vectors))
    return patterns


def _extract_bar_vectors(drum_patterns: list[M7DrumPattern]) -> dict[int, np.ndarray]:
    """Extract per-bar slot vectors from M7 DrumPatterns.

    Returns dict mapping bar_index → 48-dim vector (16 kick + 16 snare + 16 clap slots).
    """
    bar_vectors: dict[int, np.ndarray] = {}

    for pattern in drum_patterns:
        for local_bar in range(pattern.bar_end - pattern.bar_start):
            bar_idx = pattern.bar_start + local_bar
            offset = local_bar * 16

            kick_slots = pattern.kick[offset:offset + 16] if offset + 16 <= len(pattern.kick) else [0] * 16
            snare_slots = pattern.snare[offset:offset + 16] if offset + 16 <= len(pattern.snare) else [0] * 16
            clap_slots = pattern.clap[offset:offset + 16] if offset + 16 <= len(pattern.clap) else [0] * 16

            # Pad if shorter than 16
            kick_slots = (kick_slots + [0] * 16)[:16]
            snare_slots = (snare_slots + [0] * 16)[:16]
            clap_slots = (clap_slots + [0] * 16)[:16]

            vec = np.array(kick_slots + snare_slots + clap_slots, dtype=np.float32)
            bar_vectors[bar_idx] = vec

    return bar_vectors


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0 if norm_a == 0 and norm_b == 0 else 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _cluster_bars(
    bar_vectors: dict[int, np.ndarray],
    threshold: float,
) -> list[list[int]]:
    """Cluster bars by cosine similarity. Simple greedy approach."""
    if not bar_vectors:
        return []

    sorted_bars = sorted(bar_vectors.keys())
    assigned: set[int] = set()
    clusters: list[list[int]] = []

    for bar_idx in sorted_bars:
        if bar_idx in assigned:
            continue

        vec = bar_vectors[bar_idx]
        cluster = [bar_idx]
        assigned.add(bar_idx)

        for other_idx in sorted_bars:
            if other_idx in assigned:
                continue
            if _cosine_similarity(vec, bar_vectors[other_idx]) >= threshold:
                cluster.append(other_idx)
                assigned.add(other_idx)

        clusters.append(cluster)

    # Sort clusters by size (largest first)
    clusters.sort(key=len, reverse=True)
    return clusters


def _merge_consecutive_bars(
    bar_indices: list[int],
    downbeats: list[float],
    total_bars: int,
    bar_vectors: dict[int, np.ndarray],
    template_vector: np.ndarray,
) -> list[PatternInstance]:
    """Merge consecutive bar indices into PatternInstances."""
    if not bar_indices:
        return []

    sorted_bars = sorted(bar_indices)
    instances: list[PatternInstance] = []
    run_start = sorted_bars[0]
    run_end = sorted_bars[0]

    for i in range(1, len(sorted_bars)):
        if sorted_bars[i] == run_end + 1:
            run_end = sorted_bars[i]
        else:
            instances.append(_make_instance(
                run_start, run_end + 1, downbeats, total_bars,
                bar_vectors, template_vector,
            ))
            run_start = sorted_bars[i]
            run_end = sorted_bars[i]

    instances.append(_make_instance(
        run_start, run_end + 1, downbeats, total_bars,
        bar_vectors, template_vector,
    ))

    return instances


def _make_instance(
    bar_start: int,
    bar_end: int,
    downbeats: list[float],
    total_bars: int,
    bar_vectors: dict[int, np.ndarray],
    template_vector: np.ndarray,
) -> PatternInstance:
    """Create a PatternInstance from a bar range."""
    start = downbeats[bar_start] if bar_start < len(downbeats) else 0.0
    end = downbeats[bar_end] if bar_end < len(downbeats) else (
        downbeats[-1] if downbeats else 0.0
    )

    # Check for variation: if any bar differs slightly from template
    min_sim = 1.0
    for b in range(bar_start, bar_end):
        if b in bar_vectors:
            sim = _cosine_similarity(bar_vectors[b], template_vector)
            min_sim = min(min_sim, sim)

    if min_sim >= 0.99:
        variation = "exact"
    elif min_sim >= 0.85:
        variation = "minor"
    else:
        variation = "major"

    return PatternInstance(
        bar_start=bar_start,
        bar_end=bar_end,
        start=start,
        end=end,
        variation=variation,
        confidence=min_sim,
    )


def _vector_to_events(vector: np.ndarray) -> list[AtomicEvent]:
    """Convert a 48-dim bar vector back to AtomicEvent objects."""
    events: list[AtomicEvent] = []
    kick = vector[:16]
    snare = vector[16:32]
    clap = vector[32:48]

    for slot in range(16):
        if kick[slot] > 0:
            events.append(AtomicEvent(
                type="kick", timestamp=0.0, beat_position=slot,
                stem=StemType.DRUMS.value, source="pattern",
            ))
        if snare[slot] > 0:
            events.append(AtomicEvent(
                type="snare", timestamp=0.0, beat_position=slot,
                stem=StemType.DRUMS.value, source="pattern",
            ))
        if clap[slot] > 0:
            events.append(AtomicEvent(
                type="clap", timestamp=0.0, beat_position=slot,
                stem=StemType.DRUMS.value, source="pattern",
            ))

    return events


def _compute_signature(vector: np.ndarray) -> str:
    """Compute a short hash signature for a bar vector."""
    raw = vector.tobytes()
    return hashlib.md5(raw).hexdigest()[:12]


def _auto_name(vector: np.ndarray) -> str:
    """Auto-generate a descriptive name for a drum pattern.

    Examples: "kick-4otf-clap-2+4", "kick-half-snare-2+4-hat"
    """
    kick = vector[:16]
    snare = vector[16:32]
    clap = vector[32:48]

    parts: list[str] = []

    # Kick description
    kick_hits = [i for i in range(16) if kick[i] > 0]
    if kick_hits:
        if kick_hits == [0, 4, 8, 12]:
            parts.append("kick-4otf")
        elif kick_hits == [0, 8]:
            parts.append("kick-half")
        elif len(kick_hits) == 1:
            parts.append(f"kick-{_beat_name(kick_hits[0])}")
        else:
            parts.append(f"kick-x{len(kick_hits)}")

    # Snare description
    snare_hits = [i for i in range(16) if snare[i] > 0]
    if snare_hits:
        if snare_hits == [4, 12]:
            parts.append("snare-2+4")
        elif len(snare_hits) == 1:
            parts.append(f"snare-{_beat_name(snare_hits[0])}")
        else:
            parts.append(f"snare-x{len(snare_hits)}")

    # Clap description
    clap_hits = [i for i in range(16) if clap[i] > 0]
    if clap_hits:
        if clap_hits == [4, 12]:
            parts.append("clap-2+4")
        elif len(clap_hits) == 1:
            parts.append(f"clap-{_beat_name(clap_hits[0])}")
        else:
            parts.append(f"clap-x{len(clap_hits)}")

    if not parts:
        return "silent"

    return "-".join(parts)


def _beat_name(slot: int) -> str:
    """Convert a 16th-note slot to a readable beat name."""
    beat = slot // 4 + 1
    sub = slot % 4
    if sub == 0:
        return str(beat)
    return f"{beat}.{sub}"


def _compute_tags(vector: np.ndarray) -> list[str]:
    """Compute descriptive tags for a pattern."""
    tags: list[str] = []
    kick = vector[:16]
    snare = vector[16:32]
    clap = vector[32:48]

    kick_hits = [i for i in range(16) if kick[i] > 0]
    if kick_hits == [0, 4, 8, 12]:
        tags.append("four-on-the-floor")
    if [i for i in range(16) if snare[i] > 0] == [4, 12]:
        tags.append("backbeat-snare")
    if [i for i in range(16) if clap[i] > 0] == [4, 12]:
        tags.append("backbeat-clap")

    total_hits = int(np.sum(kick > 0) + np.sum(snare > 0) + np.sum(clap > 0))
    if total_hits <= 4:
        tags.append("sparse")
    elif total_hits >= 10:
        tags.append("dense")

    return tags
