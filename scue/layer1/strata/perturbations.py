"""Perturbation suites for testing Strata methods under degraded conditions.

Two families of perturbations:

1. **Grid perturbations** — deliberately degrade beat-grid data to test
   how grid-dependent methods handle errors. Used before promoting methods
   into standard, live, or deep tiers.

2. **Live perturbations** — simulate DJ operations (tempo shift, loop,
   cue jump, missing metadata) to test live-tier robustness.

Usage:
    from scue.layer1.strata.perturbations import (
        shift_downbeat, halve_tempo, run_sensitivity_suite,
    )

    degraded_grid = shift_downbeat(beat_grid, shift_beats=1)
    results = run_sensitivity_suite(my_engine_fn, gold, beat_grid, DEFAULT_GRID_PACK)
"""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass, field
from typing import Callable

from .evaluation import GoldAnnotation, StrataScorecard, evaluate_formula
from .models import ArrangementFormula

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Grid perturbation functions
# ---------------------------------------------------------------------------


def shift_downbeat(
    beat_grid: list[dict],
    shift_beats: int = 1,
) -> list[dict]:
    """Shift all beat numbers by a fixed amount.

    Simulates a downbeat offset error (e.g., beat 1 marked at beat 2).
    Time values stay the same — only beat_number changes.

    Args:
        beat_grid: Original beat grid entries.
        shift_beats: Number of beats to shift (positive = later).

    Returns:
        New beat grid with shifted beat numbers.
    """
    if not beat_grid:
        return []

    result = copy.deepcopy(beat_grid)
    for entry in result:
        entry["beat_number"] = entry["beat_number"] + shift_beats
    return result


def halve_tempo(beat_grid: list[dict]) -> list[dict]:
    """Double beat spacing to simulate half-tempo interpretation.

    Keeps every other beat entry and halves the BPM. Simulates a grid
    where the analyzer detected half the actual tempo.

    Args:
        beat_grid: Original beat grid entries.

    Returns:
        New beat grid at half tempo.
    """
    if not beat_grid:
        return []

    result = []
    for i, entry in enumerate(beat_grid):
        if i % 2 == 0:
            new_entry = copy.deepcopy(entry)
            bpm = new_entry.get("bpm", 120.0)
            new_entry["bpm"] = bpm / 2.0
            result.append(new_entry)
    return result


def double_tempo(beat_grid: list[dict]) -> list[dict]:
    """Halve beat spacing to simulate double-tempo interpretation.

    Interpolates between existing entries to create twice as many beats
    at double the BPM.

    Args:
        beat_grid: Original beat grid entries.

    Returns:
        New beat grid at double tempo.
    """
    if not beat_grid:
        return []

    result = []
    for i in range(len(beat_grid)):
        entry = copy.deepcopy(beat_grid[i])
        bpm = entry.get("bpm", 120.0)
        entry["bpm"] = bpm * 2.0
        # Renumber: original beat i becomes beat i*2
        entry["beat_number"] = entry["beat_number"] * 2
        result.append(entry)

        # Insert an interpolated beat halfway to the next entry
        if i + 1 < len(beat_grid):
            next_entry = beat_grid[i + 1]
            mid_time = (entry["time_ms"] + next_entry["time_ms"]) / 2.0
            mid_beat = entry["beat_number"] + 1
            result.append({
                "beat_number": mid_beat,
                "time_ms": mid_time,
                "bpm": bpm * 2.0,
            })

    return result


def add_drift(
    beat_grid: list[dict],
    max_drift_ms: float = 800.0,
) -> list[dict]:
    """Add gradual cumulative drift to beat timing.

    Simulates a grid that starts accurate but drifts over time (e.g.,
    tempo estimation that's slightly off).

    Args:
        beat_grid: Original beat grid entries.
        max_drift_ms: Total drift at the end of the track.

    Returns:
        New beat grid with accumulated timing drift.
    """
    if not beat_grid:
        return []

    n = len(beat_grid)
    result = copy.deepcopy(beat_grid)
    for i, entry in enumerate(result):
        # Linear drift: 0 at start, max_drift_ms at end
        drift = (i / max(1, n - 1)) * max_drift_ms
        entry["time_ms"] = entry["time_ms"] + drift

    return result


def create_sparse_gaps(
    beat_grid: list[dict],
    gap_ratio: float = 0.2,
    seed: int = 42,
) -> list[dict]:
    """Remove a fraction of grid entries to simulate sparse/missing regions.

    Args:
        beat_grid: Original beat grid entries.
        gap_ratio: Fraction of entries to remove (0.0–1.0).
        seed: Random seed for reproducibility.

    Returns:
        New beat grid with entries randomly removed.
    """
    if not beat_grid or gap_ratio <= 0:
        return copy.deepcopy(beat_grid)

    rng = random.Random(seed)
    result = []
    for entry in beat_grid:
        if rng.random() >= gap_ratio:
            result.append(copy.deepcopy(entry))

    # Always keep the first entry for anchor
    if result and beat_grid and result[0] != beat_grid[0]:
        result.insert(0, copy.deepcopy(beat_grid[0]))

    return result


def conflict_sources(
    grid_a: list[dict],
    grid_b: list[dict],
) -> list[dict]:
    """Merge two beat grids to simulate conflicting source inputs.

    Alternates entries from each grid, producing a grid with inconsistent
    timing that a trust scorer should detect.

    Args:
        grid_a: First grid source.
        grid_b: Second grid source (may have different BPM/timing).

    Returns:
        Merged grid with alternating entries.
    """
    result = []
    max_len = max(len(grid_a), len(grid_b))
    for i in range(max_len):
        if i % 2 == 0 and i < len(grid_a):
            result.append(copy.deepcopy(grid_a[i]))
        elif i < len(grid_b):
            result.append(copy.deepcopy(grid_b[i]))

    # Sort by beat_number for consistency
    result.sort(key=lambda e: e.get("beat_number", 0))
    return result


# ---------------------------------------------------------------------------
# Live perturbation functions
# ---------------------------------------------------------------------------


def simulate_tempo_shift(
    phrases: list[dict],
    beat_grid: list[dict],
    shift_bpm: float = 4.0,
) -> tuple[list[dict], list[dict]]:
    """Simulate a DJ tempo adjustment by shifting BPM.

    Adjusts all BPM values in the grid and rescales phrase beat positions
    to reflect the new tempo.

    Args:
        phrases: Original phrase entries.
        beat_grid: Original beat grid.
        shift_bpm: BPM change (positive = faster).

    Returns:
        Tuple of (new_phrases, new_beat_grid).
    """
    new_grid = copy.deepcopy(beat_grid)
    for entry in new_grid:
        old_bpm = entry.get("bpm", 120.0)
        entry["bpm"] = old_bpm + shift_bpm
        # Rescale time_ms based on tempo ratio
        if old_bpm > 0:
            ratio = old_bpm / (old_bpm + shift_bpm)
            entry["time_ms"] = entry["time_ms"] * ratio

    # Phrases keep same beat numbers (DJ operation doesn't change structure)
    new_phrases = copy.deepcopy(phrases)
    return new_phrases, new_grid


def simulate_loop(
    phrases: list[dict],
    loop_start_beat: int = 65,
    loop_length_beats: int = 16,
) -> list[dict]:
    """Simulate a DJ loop by repeating a phrase region.

    Inserts a repeated copy of the looped region into the phrase list,
    pushing subsequent phrases later.

    Args:
        phrases: Original phrase entries.
        loop_start_beat: Beat where the loop begins.
        loop_length_beats: Length of the loop in beats.

    Returns:
        New phrase list with loop region duplicated.
    """
    if not phrases:
        return []

    result = copy.deepcopy(phrases)
    loop_end_beat = loop_start_beat + loop_length_beats

    # Find phrase containing the loop point
    loop_phrase = None
    loop_idx = -1
    for i, p in enumerate(result):
        if p["start_beat"] <= loop_start_beat < p["end_beat"]:
            loop_phrase = p
            loop_idx = i
            break

    if loop_phrase is None:
        return result

    # Insert a copy of the loop region
    loop_copy = {
        "start_beat": loop_end_beat,
        "end_beat": loop_end_beat + loop_length_beats,
        "kind": loop_phrase.get("kind", "unknown"),
    }

    # Shift all subsequent phrases by loop_length_beats
    for p in result[loop_idx + 1:]:
        p["start_beat"] += loop_length_beats
        p["end_beat"] += loop_length_beats

    result.insert(loop_idx + 1, loop_copy)
    return result


def simulate_cue_jump(
    phrases: list[dict],
    from_beat: int = 128,
    to_beat: int = 32,
) -> list[dict]:
    """Simulate a DJ cue jump by removing phrases between two points.

    Removes all phrases between from_beat and to_beat (the skipped region)
    and adjusts remaining phrase boundaries.

    Args:
        phrases: Original phrase entries.
        from_beat: Beat where the jump originates.
        to_beat: Beat where playback resumes.

    Returns:
        New phrase list with jumped region removed.
    """
    if not phrases:
        return []

    if from_beat <= to_beat:
        # Forward jump: remove phrases in the skipped region
        result = []
        for p in phrases:
            if p["end_beat"] <= from_beat or p["start_beat"] >= to_beat:
                result.append(copy.deepcopy(p))
            elif p["start_beat"] < from_beat:
                # Truncate phrase at jump point
                truncated = copy.deepcopy(p)
                truncated["end_beat"] = from_beat
                result.append(truncated)
        return result
    else:
        # Backward jump: duplicate the region we're jumping back to
        result = copy.deepcopy(phrases)
        # Find phrases in the [to_beat, from_beat] region
        replay = []
        for p in phrases:
            if p["start_beat"] >= to_beat and p["end_beat"] <= from_beat:
                replay.append(copy.deepcopy(p))

        # Append replay phrases after the jump point
        offset = from_beat - to_beat
        for p in replay:
            p["start_beat"] += offset
            p["end_beat"] += offset

        # Insert replay phrases at the right position
        insert_idx = len(result)
        for i, p in enumerate(result):
            if p["start_beat"] >= from_beat:
                insert_idx = i
                break

        for i, p in enumerate(replay):
            result.insert(insert_idx + i, p)

        return result


def simulate_missing_metadata(
    phrases: list[dict],
    drop_fraction: float = 0.3,
    seed: int = 42,
) -> list[dict]:
    """Simulate missing or delayed Pioneer metadata.

    Randomly removes a fraction of phrase entries to simulate network
    drops or delayed hardware data.

    Args:
        phrases: Original phrase entries.
        drop_fraction: Fraction of phrases to remove (0.0–1.0).
        seed: Random seed for reproducibility.

    Returns:
        New phrase list with entries randomly removed.
    """
    if not phrases or drop_fraction <= 0:
        return copy.deepcopy(phrases)

    rng = random.Random(seed)
    result = []
    for p in phrases:
        if rng.random() >= drop_fraction:
            result.append(copy.deepcopy(p))

    # Always keep the first phrase for anchor
    if phrases:
        first = copy.deepcopy(phrases[0])
        if not result:
            result = [first]
        elif result[0].get("start_beat") != first.get("start_beat"):
            result.insert(0, first)

    return result


# ---------------------------------------------------------------------------
# Perturbation packs and sensitivity suite runner
# ---------------------------------------------------------------------------


@dataclass
class PerturbationPack:
    """A named set of perturbations with expected degradation bounds.

    Each perturbation is a callable that takes (beat_grid, phrases) or
    similar args and returns modified data.
    """

    name: str
    perturbations: dict[str, Callable] = field(default_factory=dict)
    description: str = ""


# Default grid perturbation pack
DEFAULT_GRID_PACK = PerturbationPack(
    name="grid_error_sensitivity",
    description="Standard grid error sensitivity suite per Strata Process v1.1",
    perturbations={
        "downbeat_shift_1": lambda bg, _ph: (shift_downbeat(bg, 1), _ph),
        "halve_tempo": lambda bg, _ph: (halve_tempo(bg), _ph),
        "double_tempo": lambda bg, _ph: (double_tempo(bg), _ph),
        "gradual_drift_800ms": lambda bg, _ph: (add_drift(bg, 800.0), _ph),
        "sparse_gaps_20pct": lambda bg, _ph: (create_sparse_gaps(bg, 0.2), _ph),
    },
)

# Default live perturbation pack
DEFAULT_LIVE_PACK = PerturbationPack(
    name="live_dj_perturbations",
    description="Standard live DJ perturbation suite per Strata Process v1",
    perturbations={
        "tempo_shift_+4bpm": lambda bg, ph: simulate_tempo_shift(ph, bg, 4.0)[::-1],
        "tempo_shift_-4bpm": lambda bg, ph: simulate_tempo_shift(ph, bg, -4.0)[::-1],
        "loop_16beat": lambda _bg, ph: (_bg, simulate_loop(ph, 65, 16)),
        "cue_jump_forward": lambda _bg, ph: (_bg, simulate_cue_jump(ph, 64, 128)),
        "missing_metadata_30pct": lambda _bg, ph: (_bg, simulate_missing_metadata(ph, 0.3)),
    },
)


def run_sensitivity_suite(
    engine_fn: Callable[[list[dict], list[dict]], ArrangementFormula],
    gold: GoldAnnotation,
    beat_grid: list[dict],
    phrases: list[dict],
    pack: PerturbationPack | None = None,
) -> dict[str, StrataScorecard]:
    """Run the engine under each perturbation and collect scorecards.

    Args:
        engine_fn: Callable that takes (beat_grid, phrases) and returns
            an ArrangementFormula.
        gold: Gold annotation to evaluate against.
        beat_grid: Original beat grid.
        phrases: Original phrase analysis.
        pack: Perturbation pack to use. Defaults to DEFAULT_GRID_PACK.

    Returns:
        Dict mapping perturbation name to its scorecard.
    """
    if pack is None:
        pack = DEFAULT_GRID_PACK

    results: dict[str, StrataScorecard] = {}

    # Baseline (no perturbation)
    try:
        baseline_formula = engine_fn(beat_grid, phrases)
        results["baseline"] = evaluate_formula(baseline_formula, gold, beat_grid)
    except Exception:
        logger.exception("Baseline engine call failed")
        results["baseline"] = StrataScorecard(fingerprint=gold.fingerprint)

    # Each perturbation
    for name, perturb_fn in pack.perturbations.items():
        try:
            perturbed_grid, perturbed_phrases = perturb_fn(beat_grid, phrases)
            formula = engine_fn(perturbed_grid, perturbed_phrases)
            scorecard = evaluate_formula(formula, gold, perturbed_grid)
            results[name] = scorecard
        except Exception:
            logger.exception("Perturbation %s failed", name)
            results[name] = StrataScorecard(fingerprint=gold.fingerprint)

    return results
