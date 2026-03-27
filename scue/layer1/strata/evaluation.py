"""Strata evaluation harness — shared scorecard for all experiments.

Computes metrics comparing an ArrangementFormula against a human-reviewed
GoldAnnotation. Every Strata experiment uses the same scorecard structure
to enable consistent comparison across tiers, sources, and methods.

Metric groups:
  - structure:   boundary accuracy, label agreement, section count
  - layers:      layer presence F1, false enter/exit
  - transitions: precision/recall by type
  - stability:   jitter, flip-rate, off-grid rate
  - latency:     total analysis time, per-update latency
  - grid:        trust tier and confidence (from grid_trust module)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .models import ArrangementFormula, ArrangementTransition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gold annotation — human-reviewed reference
# ---------------------------------------------------------------------------


@dataclass
class GoldSection:
    """A single section in a gold annotation."""

    label: str
    start: float  # seconds
    end: float  # seconds


@dataclass
class GoldTransition:
    """A single transition in a gold annotation."""

    type: str  # matches TransitionType values
    timestamp: float  # seconds


@dataclass
class GoldAnnotation:
    """Human-reviewed reference for evaluating a Strata formula.

    This is the ground truth against which ArrangementFormula outputs
    are scored. Annotations are stored as JSON files under
    research/gpt/strata-items/gold-set/annotations/.
    """

    fingerprint: str
    sections: list[GoldSection] = field(default_factory=list)
    transitions: list[GoldTransition] = field(default_factory=list)
    active_layers_per_section: list[list[str]] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "fingerprint": self.fingerprint,
            "sections": [
                {"label": s.label, "start": s.start, "end": s.end}
                for s in self.sections
            ],
            "transitions": [
                {"type": t.type, "timestamp": t.timestamp}
                for t in self.transitions
            ],
            "active_layers_per_section": self.active_layers_per_section,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> GoldAnnotation:
        """Deserialize from a dict."""
        return GoldAnnotation(
            fingerprint=d.get("fingerprint", ""),
            sections=[
                GoldSection(label=s["label"], start=s["start"], end=s["end"])
                for s in d.get("sections", [])
            ],
            transitions=[
                GoldTransition(type=t["type"], timestamp=t["timestamp"])
                for t in d.get("transitions", [])
            ],
            active_layers_per_section=d.get("active_layers_per_section", []),
            notes=d.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Scorecard — evaluation output
# ---------------------------------------------------------------------------


@dataclass
class StructureMetrics:
    """Section boundary and label accuracy."""

    boundary_hit_rate: float = 0.0  # fraction of gold boundaries matched
    label_agreement: float = 0.0  # fraction of overlapping sections with matching labels
    section_count_delta: int = 0  # predicted - gold count


@dataclass
class LayerMetrics:
    """Layer presence detection quality."""

    layer_f1: float = 0.0
    false_enter_count: int = 0
    false_exit_count: int = 0


@dataclass
class TransitionMetrics:
    """Transition detection precision and recall."""

    transition_precision: float = 0.0
    transition_recall: float = 0.0
    drop_precision: float = 0.0
    breakdown_precision: float = 0.0
    fill_precision: float = 0.0


@dataclass
class StabilityMetrics:
    """Output stability measures."""

    boundary_jitter_seconds: float = 0.0  # mean distance to nearest gold boundary
    boundary_jitter_beats: float = 0.0  # same in beats (if grid available)
    label_flip_rate: float = 0.0  # flips per minute
    off_grid_rate: float = 0.0  # fraction of boundaries not on beat grid
    transition_false_positives_per_minute: float = 0.0


@dataclass
class LatencyMetrics:
    """Performance timing."""

    total_analysis_seconds: float = 0.0
    per_update_latency_seconds: float = 0.0


@dataclass
class GridMetrics:
    """Beat-grid trust information."""

    grid_trust_tier: str = ""  # "A" | "B" | "C" | ""
    grid_source_confidence: float = 0.0


@dataclass
class StrataScorecard:
    """Complete evaluation of a Strata formula against a gold annotation.

    Every Strata experiment uses this same structure. Fields that are not
    applicable for a given tier/method are left at their defaults.
    """

    structure: StructureMetrics = field(default_factory=StructureMetrics)
    layers: LayerMetrics = field(default_factory=LayerMetrics)
    transitions: TransitionMetrics = field(default_factory=TransitionMetrics)
    stability: StabilityMetrics = field(default_factory=StabilityMetrics)
    latency: LatencyMetrics = field(default_factory=LatencyMetrics)
    grid: GridMetrics = field(default_factory=GridMetrics)

    # Meta
    fingerprint: str = ""
    tier: str = ""
    source: str = ""
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        from dataclasses import asdict
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> StrataScorecard:
        """Deserialize from dict."""
        return StrataScorecard(
            structure=StructureMetrics(**d.get("structure", {})),
            layers=LayerMetrics(**d.get("layers", {})),
            transitions=TransitionMetrics(**d.get("transitions", {})),
            stability=StabilityMetrics(**d.get("stability", {})),
            latency=LatencyMetrics(**d.get("latency", {})),
            grid=GridMetrics(**d.get("grid", {})),
            fingerprint=d.get("fingerprint", ""),
            tier=d.get("tier", ""),
            source=d.get("source", ""),
            evaluated_at=d.get("evaluated_at", 0.0),
        )


# ---------------------------------------------------------------------------
# Evaluation functions
# ---------------------------------------------------------------------------

# Default boundary tolerance in seconds
_DEFAULT_BOUNDARY_TOLERANCE_S = 4.0


def evaluate_formula(
    formula: ArrangementFormula,
    gold: GoldAnnotation,
    beat_grid: list[dict] | None = None,
    boundary_tolerance_s: float = _DEFAULT_BOUNDARY_TOLERANCE_S,
) -> StrataScorecard:
    """Evaluate a formula against a gold annotation.

    Args:
        formula: The predicted ArrangementFormula.
        gold: The human-reviewed reference.
        beat_grid: Optional beat grid for beat-space metrics.
        boundary_tolerance_s: Max distance (seconds) for a boundary hit.

    Returns:
        StrataScorecard with all applicable metrics filled in.
    """
    scorecard = StrataScorecard(
        fingerprint=formula.fingerprint,
        tier=formula.pipeline_tier,
        source=formula.analysis_source,
    )

    # --- Structure metrics ---
    scorecard.structure = _compute_structure_metrics(
        formula, gold, boundary_tolerance_s
    )

    # --- Layer metrics ---
    scorecard.layers = _compute_layer_metrics(formula, gold)

    # --- Transition metrics ---
    scorecard.transitions = _compute_transition_metrics(
        formula, gold, boundary_tolerance_s
    )

    # --- Stability metrics ---
    scorecard.stability = _compute_stability_metrics(
        formula, gold, beat_grid
    )

    # --- Latency metrics ---
    scorecard.latency = LatencyMetrics(
        total_analysis_seconds=formula.compute_time_seconds,
    )

    # --- Grid metrics ---
    if formula.grid_trust:
        scorecard.grid = GridMetrics(
            grid_trust_tier=formula.grid_trust.get("tier", ""),
            grid_source_confidence=formula.grid_trust.get("confidence", 0.0),
        )

    return scorecard


def evaluate_batch(
    formulas: list[ArrangementFormula],
    golds: list[GoldAnnotation],
    beat_grids: list[list[dict] | None] | None = None,
) -> list[StrataScorecard]:
    """Evaluate a batch of formulas against gold annotations.

    Args:
        formulas: Predicted formulas (matched by index with golds).
        golds: Gold annotations (same length as formulas).
        beat_grids: Optional per-track beat grids (same length, or None).

    Returns:
        List of scorecards, one per formula.
    """
    if len(formulas) != len(golds):
        raise ValueError(
            f"Formula count ({len(formulas)}) != gold count ({len(golds)})"
        )

    grids = beat_grids or [None] * len(formulas)
    return [
        evaluate_formula(f, g, bg)
        for f, g, bg in zip(formulas, golds, grids)
    ]


def compare_scorecards(
    baseline: StrataScorecard,
    candidate: StrataScorecard,
) -> dict:
    """Compare two scorecards and return per-metric deltas.

    Returns a dict with keys matching scorecard groups, each containing
    metric_name -> {"baseline": val, "candidate": val, "delta": val, "better": bool}.
    """
    result: dict[str, dict] = {}

    # Compare structure metrics
    result["structure"] = _compare_group(
        baseline.structure, candidate.structure,
        higher_is_better={"boundary_hit_rate", "label_agreement"},
        lower_is_better=set(),
        closer_to_zero={"section_count_delta"},
    )

    # Compare layer metrics
    result["layers"] = _compare_group(
        baseline.layers, candidate.layers,
        higher_is_better={"layer_f1"},
        lower_is_better={"false_enter_count", "false_exit_count"},
    )

    # Compare transition metrics
    result["transitions"] = _compare_group(
        baseline.transitions, candidate.transitions,
        higher_is_better={
            "transition_precision", "transition_recall",
            "drop_precision", "breakdown_precision", "fill_precision",
        },
    )

    # Compare stability metrics
    result["stability"] = _compare_group(
        baseline.stability, candidate.stability,
        lower_is_better={
            "boundary_jitter_seconds", "boundary_jitter_beats",
            "label_flip_rate", "off_grid_rate",
            "transition_false_positives_per_minute",
        },
    )

    # Compare latency metrics
    result["latency"] = _compare_group(
        baseline.latency, candidate.latency,
        lower_is_better={"total_analysis_seconds", "per_update_latency_seconds"},
    )

    return result


# ---------------------------------------------------------------------------
# Internal computation helpers
# ---------------------------------------------------------------------------


def _compute_structure_metrics(
    formula: ArrangementFormula,
    gold: GoldAnnotation,
    tolerance_s: float,
) -> StructureMetrics:
    """Compute boundary hit rate, label agreement, and section count delta."""
    pred_sections = formula.sections
    gold_sections = gold.sections

    if not gold_sections:
        return StructureMetrics(section_count_delta=len(pred_sections))

    # Boundary hit rate: fraction of gold boundaries matched by a pred boundary
    gold_boundaries = set()
    for s in gold_sections:
        gold_boundaries.add(s.start)
        gold_boundaries.add(s.end)
    # Remove 0.0 (track start) — it's always trivially matched
    gold_boundaries.discard(0.0)

    pred_boundaries = set()
    for s in pred_sections:
        pred_boundaries.add(s.section_start)
        pred_boundaries.add(s.section_end)

    hits = 0
    for gb in gold_boundaries:
        for pb in pred_boundaries:
            if abs(gb - pb) <= tolerance_s:
                hits += 1
                break

    boundary_hit_rate = hits / len(gold_boundaries) if gold_boundaries else 1.0

    # Label agreement: for each gold section, find best overlapping pred section
    label_matches = 0
    label_total = 0
    for gs in gold_sections:
        best_overlap = 0.0
        best_label = ""
        for ps in pred_sections:
            overlap = _overlap(gs.start, gs.end, ps.section_start, ps.section_end)
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = ps.section_label
        if best_overlap > 0:
            label_total += 1
            if best_label == gs.label:
                label_matches += 1

    label_agreement = label_matches / label_total if label_total > 0 else 0.0

    return StructureMetrics(
        boundary_hit_rate=round(boundary_hit_rate, 4),
        label_agreement=round(label_agreement, 4),
        section_count_delta=len(pred_sections) - len(gold_sections),
    )


def _compute_layer_metrics(
    formula: ArrangementFormula,
    gold: GoldAnnotation,
) -> LayerMetrics:
    """Compute layer presence F1 score."""
    if not gold.active_layers_per_section or not gold.sections:
        return LayerMetrics()

    # Build per-section predicted active layers
    pred_layers_per_section: list[set[str]] = []
    for gs in gold.sections:
        layers: set[str] = set()
        for ps in formula.sections:
            overlap = _overlap(gs.start, gs.end, ps.section_start, ps.section_end)
            if overlap > 0:
                layers.update(ps.active_layers)
        pred_layers_per_section.append(layers)

    # Compute micro-averaged F1
    tp = fp = fn = 0
    for pred_set, gold_list in zip(
        pred_layers_per_section, gold.active_layers_per_section
    ):
        gold_set = set(gold_list)
        tp += len(pred_set & gold_set)
        fp += len(pred_set - gold_set)
        fn += len(gold_set - pred_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return LayerMetrics(
        layer_f1=round(f1, 4),
        false_enter_count=fp,
        false_exit_count=fn,
    )


def _compute_transition_metrics(
    formula: ArrangementFormula,
    gold: GoldAnnotation,
    tolerance_s: float,
) -> TransitionMetrics:
    """Compute transition precision and recall."""
    pred_transitions = formula.transitions
    gold_transitions = gold.transitions

    if not gold_transitions and not pred_transitions:
        return TransitionMetrics(
            transition_precision=1.0, transition_recall=1.0,
        )
    if not gold_transitions:
        return TransitionMetrics(transition_precision=0.0, transition_recall=1.0)
    if not pred_transitions:
        return TransitionMetrics(transition_precision=1.0, transition_recall=0.0)

    # Overall precision: fraction of predicted transitions near a gold transition
    pred_hits = 0
    for pt in pred_transitions:
        for gt in gold_transitions:
            if abs(pt.timestamp - gt.timestamp) <= tolerance_s:
                pred_hits += 1
                break
    precision = pred_hits / len(pred_transitions)

    # Overall recall: fraction of gold transitions near a predicted transition
    gold_hits = 0
    for gt in gold_transitions:
        for pt in pred_transitions:
            if abs(gt.timestamp - pt.timestamp) <= tolerance_s:
                gold_hits += 1
                break
    recall = gold_hits / len(gold_transitions)

    # Per-type precision for specific transition types
    drop_precision = _type_precision(pred_transitions, gold_transitions, "drop_impact", tolerance_s)
    breakdown_precision = _type_precision(pred_transitions, gold_transitions, "breakdown", tolerance_s)
    fill_precision = _type_precision(pred_transitions, gold_transitions, "fill", tolerance_s)

    return TransitionMetrics(
        transition_precision=round(precision, 4),
        transition_recall=round(recall, 4),
        drop_precision=round(drop_precision, 4),
        breakdown_precision=round(breakdown_precision, 4),
        fill_precision=round(fill_precision, 4),
    )


def _compute_stability_metrics(
    formula: ArrangementFormula,
    gold: GoldAnnotation,
    beat_grid: list[dict] | None,
) -> StabilityMetrics:
    """Compute boundary jitter and related stability metrics."""
    gold_sections = gold.sections
    pred_sections = formula.sections

    if not gold_sections or not pred_sections:
        return StabilityMetrics()

    # Boundary jitter: mean distance from each gold boundary to nearest pred boundary
    gold_boundaries = []
    for s in gold_sections:
        gold_boundaries.append(s.start)
        gold_boundaries.append(s.end)
    # Deduplicate and remove track start
    gold_boundaries = sorted(set(b for b in gold_boundaries if b > 0.0))

    pred_boundaries = []
    for s in pred_sections:
        pred_boundaries.append(s.section_start)
        pred_boundaries.append(s.section_end)
    pred_boundaries = sorted(set(pred_boundaries))

    if not gold_boundaries or not pred_boundaries:
        return StabilityMetrics()

    jitters = []
    for gb in gold_boundaries:
        min_dist = min(abs(gb - pb) for pb in pred_boundaries)
        jitters.append(min_dist)

    jitter_s = sum(jitters) / len(jitters) if jitters else 0.0

    # Convert to beats if grid available
    jitter_beats = 0.0
    if beat_grid and len(beat_grid) >= 2:
        bpm = beat_grid[0].get("bpm", 120.0)
        if bpm > 0:
            beat_duration_s = 60.0 / bpm
            jitter_beats = jitter_s / beat_duration_s

    # Transition false positive rate (per minute)
    gold_transition_times = {gt.timestamp for gt in gold.transitions}
    pred_transition_times = [pt.timestamp for pt in formula.transitions]
    fp_count = 0
    for pt_time in pred_transition_times:
        if not any(abs(pt_time - gt) <= _DEFAULT_BOUNDARY_TOLERANCE_S for gt in gold_transition_times):
            fp_count += 1

    # Estimate track duration for per-minute rate
    track_duration_min = 0.0
    if pred_sections:
        track_end = max(s.section_end for s in pred_sections)
        track_duration_min = track_end / 60.0

    fp_per_min = fp_count / track_duration_min if track_duration_min > 0 else 0.0

    return StabilityMetrics(
        boundary_jitter_seconds=round(jitter_s, 4),
        boundary_jitter_beats=round(jitter_beats, 4),
        transition_false_positives_per_minute=round(fp_per_min, 4),
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Compute the overlap duration between two time ranges."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0.0, end - start)


def _type_precision(
    pred: list[ArrangementTransition],
    gold: list[GoldTransition],
    type_name: str,
    tolerance_s: float,
) -> float:
    """Compute precision for a specific transition type."""
    pred_of_type = [t for t in pred if t.type.value == type_name]
    gold_of_type = [t for t in gold if t.type == type_name]

    if not pred_of_type:
        return 1.0 if not gold_of_type else 0.0

    hits = 0
    for pt in pred_of_type:
        for gt in gold_of_type:
            if abs(pt.timestamp - gt.timestamp) <= tolerance_s:
                hits += 1
                break

    return hits / len(pred_of_type)


def _compare_group(
    baseline: object,
    candidate: object,
    higher_is_better: set[str] | None = None,
    lower_is_better: set[str] | None = None,
    closer_to_zero: set[str] | None = None,
) -> dict:
    """Compare two dataclass instances field by field."""
    higher_is_better = higher_is_better or set()
    lower_is_better = lower_is_better or set()
    closer_to_zero = closer_to_zero or set()

    result = {}
    for field_name in vars(baseline):
        b_val = getattr(baseline, field_name)
        c_val = getattr(candidate, field_name)

        if not isinstance(b_val, (int, float)):
            continue

        delta = c_val - b_val

        if field_name in higher_is_better:
            better = delta > 0
        elif field_name in lower_is_better:
            better = delta < 0
        elif field_name in closer_to_zero:
            better = abs(c_val) < abs(b_val)
        else:
            better = delta >= 0  # Default: higher is better

        result[field_name] = {
            "baseline": b_val,
            "candidate": c_val,
            "delta": round(delta, 6),
            "better": better,
        }

    return result
