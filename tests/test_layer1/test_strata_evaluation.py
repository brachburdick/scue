"""Tests for the Strata evaluation harness."""

from __future__ import annotations

import json

import pytest

from scue.layer1.strata.evaluation import (
    GoldAnnotation,
    GoldSection,
    GoldTransition,
    StrataScorecard,
    compare_scorecards,
    evaluate_batch,
    evaluate_formula,
)
from scue.layer1.strata.models import (
    ArrangementFormula,
    ArrangementTransition,
    SectionArrangement,
    TransitionType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_gold() -> GoldAnnotation:
    """Standard gold annotation: intro(0-30), build(30-60), drop(60-120), outro(120-150)."""
    return GoldAnnotation(
        fingerprint="test_fp",
        sections=[
            GoldSection(label="intro", start=0.0, end=30.0),
            GoldSection(label="build", start=30.0, end=60.0),
            GoldSection(label="drop", start=60.0, end=120.0),
            GoldSection(label="outro", start=120.0, end=150.0),
        ],
        transitions=[
            GoldTransition(type="energy_shift", timestamp=30.0),
            GoldTransition(type="drop_impact", timestamp=60.0),
            GoldTransition(type="energy_shift", timestamp=120.0),
        ],
        active_layers_per_section=[
            ["drums"],
            ["drums", "bass"],
            ["drums", "bass", "other"],
            ["drums"],
        ],
        notes="Test track",
    )


def _make_perfect_formula() -> ArrangementFormula:
    """Formula that perfectly matches the gold annotation."""
    return ArrangementFormula(
        fingerprint="test_fp",
        sections=[
            SectionArrangement(
                section_label="intro", section_start=0.0, section_end=30.0,
                active_layers=["drums"], active_patterns=[], transitions=[],
                energy_level=0.3, energy_trend="rising", layer_count=1,
            ),
            SectionArrangement(
                section_label="build", section_start=30.0, section_end=60.0,
                active_layers=["drums", "bass"], active_patterns=[], transitions=[],
                energy_level=0.6, energy_trend="rising", layer_count=2,
            ),
            SectionArrangement(
                section_label="drop", section_start=60.0, section_end=120.0,
                active_layers=["drums", "bass", "other"], active_patterns=[], transitions=[],
                energy_level=0.9, energy_trend="peak", layer_count=3,
            ),
            SectionArrangement(
                section_label="outro", section_start=120.0, section_end=150.0,
                active_layers=["drums"], active_patterns=[], transitions=[],
                energy_level=0.25, energy_trend="falling", layer_count=1,
            ),
        ],
        transitions=[
            ArrangementTransition(
                type=TransitionType.ENERGY_SHIFT, timestamp=30.0, bar_index=0,
                section_label="build", layers_affected=[], patterns_affected=[],
                energy_delta=0.3, description="", confidence=0.8,
            ),
            ArrangementTransition(
                type=TransitionType.DROP_IMPACT, timestamp=60.0, bar_index=0,
                section_label="drop", layers_affected=[], patterns_affected=[],
                energy_delta=0.5, description="", confidence=0.9,
            ),
            ArrangementTransition(
                type=TransitionType.ENERGY_SHIFT, timestamp=120.0, bar_index=0,
                section_label="outro", layers_affected=[], patterns_affected=[],
                energy_delta=-0.65, description="", confidence=0.8,
            ),
        ],
        compute_time_seconds=2.5,
    )


def _make_offset_formula(offset_s: float = 5.0) -> ArrangementFormula:
    """Formula with all boundaries shifted by offset_s seconds."""
    perfect = _make_perfect_formula()
    for sec in perfect.sections:
        sec.section_start += offset_s
        sec.section_end += offset_s
    for t in perfect.transitions:
        t.timestamp += offset_s
    return perfect


# ---------------------------------------------------------------------------
# Structure metrics tests
# ---------------------------------------------------------------------------


class TestStructureMetrics:

    def test_perfect_match(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.structure.boundary_hit_rate == 1.0
        assert sc.structure.label_agreement == 1.0
        assert sc.structure.section_count_delta == 0

    def test_offset_boundaries_within_tolerance(self) -> None:
        gold = _make_gold()
        formula = _make_offset_formula(offset_s=3.0)  # Within 4s tolerance
        sc = evaluate_formula(formula, gold)
        assert sc.structure.boundary_hit_rate == 1.0

    def test_offset_boundaries_outside_tolerance(self) -> None:
        gold = _make_gold()
        formula = _make_offset_formula(offset_s=10.0)  # Outside 4s tolerance
        sc = evaluate_formula(formula, gold)
        assert sc.structure.boundary_hit_rate < 1.0

    def test_wrong_labels(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        # Change all labels to "verse"
        for sec in formula.sections:
            sec.section_label = "verse"
        sc = evaluate_formula(formula, gold)
        assert sc.structure.label_agreement == 0.0

    def test_extra_sections(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        formula.sections.append(SectionArrangement(
            section_label="extra", section_start=150.0, section_end=180.0,
            active_layers=[], active_patterns=[], transitions=[],
            energy_level=0.1, energy_trend="stable", layer_count=0,
        ))
        sc = evaluate_formula(formula, gold)
        assert sc.structure.section_count_delta == 1

    def test_empty_gold(self) -> None:
        gold = GoldAnnotation(fingerprint="test")
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.structure.section_count_delta == 4


# ---------------------------------------------------------------------------
# Layer metrics tests
# ---------------------------------------------------------------------------


class TestLayerMetrics:

    def test_perfect_layers(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.layers.layer_f1 == 1.0
        assert sc.layers.false_enter_count == 0
        assert sc.layers.false_exit_count == 0

    def test_missing_layers(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        # Remove all layers from prediction
        for sec in formula.sections:
            sec.active_layers = []
        sc = evaluate_formula(formula, gold)
        assert sc.layers.layer_f1 == 0.0
        assert sc.layers.false_exit_count > 0

    def test_extra_layers(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        # Add spurious layers
        for sec in formula.sections:
            sec.active_layers.append("vocals")
        sc = evaluate_formula(formula, gold)
        assert sc.layers.layer_f1 < 1.0
        assert sc.layers.false_enter_count > 0

    def test_no_gold_layers(self) -> None:
        gold = _make_gold()
        gold.active_layers_per_section = []
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.layers.layer_f1 == 0.0  # Default


# ---------------------------------------------------------------------------
# Transition metrics tests
# ---------------------------------------------------------------------------


class TestTransitionMetrics:

    def test_perfect_transitions(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.transitions.transition_precision == 1.0
        assert sc.transitions.transition_recall == 1.0

    def test_no_predicted_transitions(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        formula.transitions = []
        sc = evaluate_formula(formula, gold)
        assert sc.transitions.transition_recall == 0.0

    def test_extra_predicted_transitions(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        formula.transitions.append(ArrangementTransition(
            type=TransitionType.FILL, timestamp=45.0, bar_index=0,
            section_label="", layers_affected=[], patterns_affected=[],
            energy_delta=0.0, description="spurious", confidence=0.5,
        ))
        sc = evaluate_formula(formula, gold)
        assert sc.transitions.transition_precision < 1.0
        assert sc.transitions.transition_recall == 1.0


# ---------------------------------------------------------------------------
# Stability metrics tests
# ---------------------------------------------------------------------------


class TestStabilityMetrics:

    def test_perfect_jitter(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.stability.boundary_jitter_seconds == 0.0

    def test_offset_jitter(self) -> None:
        gold = _make_gold()
        formula = _make_offset_formula(offset_s=2.0)
        sc = evaluate_formula(formula, gold)
        assert sc.stability.boundary_jitter_seconds > 0.0

    def test_jitter_in_beats_with_grid(self) -> None:
        gold = _make_gold()
        formula = _make_offset_formula(offset_s=1.0)
        beat_grid = [
            {"beat_number": 1, "time_ms": 0.0, "bpm": 120.0},
            {"beat_number": 2, "time_ms": 500.0, "bpm": 120.0},
        ]
        sc = evaluate_formula(formula, gold, beat_grid=beat_grid)
        # 1.0 second at 120 BPM = 2 beats
        assert sc.stability.boundary_jitter_beats > 0.0

    def test_false_positive_rate(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        # Add spurious transitions
        for t_sec in [15.0, 45.0, 90.0, 135.0]:
            formula.transitions.append(ArrangementTransition(
                type=TransitionType.FILL, timestamp=t_sec, bar_index=0,
                section_label="", layers_affected=[], patterns_affected=[],
                energy_delta=0.0, description="spurious", confidence=0.3,
            ))
        sc = evaluate_formula(formula, gold)
        assert sc.stability.transition_false_positives_per_minute > 0.0


# ---------------------------------------------------------------------------
# Grid and latency metrics
# ---------------------------------------------------------------------------


class TestGridAndLatencyMetrics:

    def test_grid_trust_extracted(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        formula.grid_trust = {"tier": "A", "confidence": 1.0}
        sc = evaluate_formula(formula, gold)
        assert sc.grid.grid_trust_tier == "A"
        assert sc.grid.grid_source_confidence == 1.0

    def test_no_grid_trust(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        assert sc.grid.grid_trust_tier == ""

    def test_latency_from_formula(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        formula.compute_time_seconds = 3.14
        sc = evaluate_formula(formula, gold)
        assert sc.latency.total_analysis_seconds == 3.14


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------


class TestBatchEvaluation:

    def test_batch_same_length(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        results = evaluate_batch([formula, formula], [gold, gold])
        assert len(results) == 2
        assert all(r.structure.boundary_hit_rate == 1.0 for r in results)

    def test_batch_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="Formula count"):
            evaluate_batch([_make_perfect_formula()], [_make_gold(), _make_gold()])


# ---------------------------------------------------------------------------
# Scorecard comparison
# ---------------------------------------------------------------------------


class TestScorecardComparison:

    def test_same_scorecards(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        comparison = compare_scorecards(sc, sc)
        for group_name, metrics in comparison.items():
            for metric_name, detail in metrics.items():
                assert detail["delta"] == 0.0

    def test_improvement_detected(self) -> None:
        gold = _make_gold()
        baseline = evaluate_formula(_make_offset_formula(5.0), gold)
        candidate = evaluate_formula(_make_perfect_formula(), gold)
        comparison = compare_scorecards(baseline, candidate)
        # Boundary hit rate should improve
        bhr = comparison["structure"]["boundary_hit_rate"]
        assert bhr["delta"] > 0
        assert bhr["better"] is True

    def test_regression_detected(self) -> None:
        gold = _make_gold()
        baseline = evaluate_formula(_make_perfect_formula(), gold)
        candidate = evaluate_formula(_make_offset_formula(10.0), gold)
        comparison = compare_scorecards(baseline, candidate)
        bhr = comparison["structure"]["boundary_hit_rate"]
        assert bhr["delta"] < 0
        assert bhr["better"] is False


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:

    def test_gold_round_trip(self) -> None:
        gold = _make_gold()
        data = gold.to_dict()
        restored = GoldAnnotation.from_dict(data)
        assert len(restored.sections) == 4
        assert restored.sections[0].label == "intro"
        assert len(restored.transitions) == 3
        assert restored.fingerprint == "test_fp"

    def test_gold_json_safe(self) -> None:
        gold = _make_gold()
        data = gold.to_dict()
        json_str = json.dumps(data)
        assert isinstance(json_str, str)

    def test_scorecard_round_trip(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        data = sc.to_dict()
        restored = StrataScorecard.from_dict(data)
        assert restored.structure.boundary_hit_rate == sc.structure.boundary_hit_rate
        assert restored.fingerprint == "test_fp"

    def test_scorecard_json_safe(self) -> None:
        gold = _make_gold()
        formula = _make_perfect_formula()
        sc = evaluate_formula(formula, gold)
        data = sc.to_dict()
        json_str = json.dumps(data)
        assert isinstance(json_str, str)
