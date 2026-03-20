"""Eval harness for event detection strategies.

Compares detector output against labeled ground truth files, computing
precision, recall, and F1 per event type with configurable time tolerance.

Usage:
    python -m scue.layer1.eval_detectors <audio_path> --ground-truth <gt.json>
    python -m scue.layer1.eval_detectors <audio_path> --compare heuristic,random_forest

Ground truth format (JSON):
    [
        {"type": "kick", "timestamp": 1.234},
        {"type": "riser", "timestamp": 30.5, "duration": 4.2},
        ...
    ]
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ScoreCard:
    """Per-event-type scoring results."""
    event_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


@dataclass
class EvalResult:
    """Full evaluation result for a strategy."""
    strategy: str
    scores: dict[str, ScoreCard] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def summary_table(self) -> str:
        """Format scores as a readable table."""
        lines = [
            f"Strategy: {self.strategy}",
            f"{'Type':<15} {'Prec':>6} {'Recall':>6} {'F1':>6}  {'TP':>4} {'FP':>4} {'FN':>4}",
            "-" * 55,
        ]
        for event_type, sc in sorted(self.scores.items()):
            lines.append(
                f"{event_type:<15} {sc.precision:>6.3f} {sc.recall:>6.3f} {sc.f1:>6.3f}  "
                f"{sc.true_positives:>4} {sc.false_positives:>4} {sc.false_negatives:>4}"
            )
        return "\n".join(lines)


def load_ground_truth(gt_path: str | Path) -> list[dict]:
    """Load ground truth events from a JSON file."""
    with open(gt_path) as f:
        data = json.load(f)
    return data


def score_events(
    detected: list[dict],
    ground_truth: list[dict],
    percussion_tolerance: float = 0.05,
    tonal_tolerance: float = 0.5,
) -> dict[str, ScoreCard]:
    """Score detected events against ground truth.

    Args:
        detected: List of detected events (dicts with 'type', 'timestamp').
        ground_truth: List of ground truth events.
        percussion_tolerance: Time tolerance for percussion matching (seconds).
        tonal_tolerance: Time tolerance for tonal event matching (seconds).

    Returns:
        Dict mapping event type → ScoreCard.
    """
    tonal_types = {"riser", "faller", "stab"}
    all_types = set(e["type"] for e in detected) | set(e["type"] for e in ground_truth)

    scores: dict[str, ScoreCard] = {}

    for event_type in all_types:
        tolerance = tonal_tolerance if event_type in tonal_types else percussion_tolerance
        det = [e for e in detected if e["type"] == event_type]
        gt = [e for e in ground_truth if e["type"] == event_type]

        sc = ScoreCard(event_type=event_type)
        matched_gt: set[int] = set()

        for d in det:
            matched = False
            for i, g in enumerate(gt):
                if i in matched_gt:
                    continue
                if abs(d["timestamp"] - g["timestamp"]) <= tolerance:
                    sc.true_positives += 1
                    matched_gt.add(i)
                    matched = True
                    break
            if not matched:
                sc.false_positives += 1

        sc.false_negatives = len(gt) - len(matched_gt)
        scores[event_type] = sc

    return scores


def evaluate_strategy(
    audio_path: str | Path,
    ground_truth_path: str | Path,
    strategy_overrides: dict[str, str] | None = None,
) -> EvalResult:
    """Run a detection strategy on a track and score against ground truth.

    Args:
        audio_path: Path to the audio file.
        ground_truth_path: Path to ground truth JSON.
        strategy_overrides: Optional dict to override active_strategies in config.

    Returns:
        EvalResult with per-event-type scores.
    """
    from .analysis import run_analysis
    from .detectors.events import load_detector_config
    from .models import event_to_dict

    # Load and optionally override config
    config = load_detector_config()
    if strategy_overrides:
        config.active_strategies.update(strategy_overrides)

    strategy_name = "_".join(f"{k}={v}" for k, v in sorted(config.active_strategies.items()))

    # Run analysis
    analysis = run_analysis(
        audio_path=audio_path,
        skip_waveform=True,
        force=True,
    )

    # Convert events to dicts for scoring
    detected = [event_to_dict(e) for e in analysis.events]

    # Expand drum patterns to events for scoring
    if analysis.drum_patterns:
        from .detectors.events import expand_patterns
        expanded = expand_patterns(
            analysis.drum_patterns,
            analysis.beats,
            analysis.downbeats,
        )
        detected.extend([event_to_dict(e) for e in expanded])

    # Score
    gt = load_ground_truth(ground_truth_path)
    scores = score_events(detected, gt)

    return EvalResult(
        strategy=strategy_name,
        scores=scores,
        metadata={
            "audio_path": str(audio_path),
            "ground_truth_path": str(ground_truth_path),
            "total_detected": len(detected),
            "total_ground_truth": len(gt),
        },
    )


def compare_strategies(
    audio_path: str | Path,
    ground_truth_path: str | Path,
    strategies: list[dict[str, str]],
) -> list[EvalResult]:
    """Run multiple strategies and compare their scores.

    Args:
        audio_path: Path to the audio file.
        ground_truth_path: Path to ground truth JSON.
        strategies: List of strategy override dicts.

    Returns:
        List of EvalResult, one per strategy.
    """
    results = []
    for overrides in strategies:
        result = evaluate_strategy(audio_path, ground_truth_path, overrides)
        results.append(result)
    return results


def main() -> None:
    """CLI entry point for eval harness."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Evaluate event detection strategies")
    parser.add_argument("audio_path", help="Path to audio file")
    parser.add_argument("--ground-truth", "-g", required=True, help="Path to ground truth JSON")
    parser.add_argument(
        "--compare", "-c",
        help="Comma-separated percussion strategies to compare (e.g., heuristic,random_forest)",
    )
    args = parser.parse_args()

    if args.compare:
        strategy_names = args.compare.split(",")
        strategies = [{"percussion": s.strip()} for s in strategy_names]
        results = compare_strategies(args.audio_path, args.ground_truth, strategies)

        print("\n" + "=" * 60)
        print("COMPARISON RESULTS")
        print("=" * 60)
        for result in results:
            print()
            print(result.summary_table())
            print()
    else:
        result = evaluate_strategy(args.audio_path, args.ground_truth)
        print()
        print(result.summary_table())


if __name__ == "__main__":
    main()
