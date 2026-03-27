"""Tests for Strata tier promotion rules and engine priors wiring."""

from __future__ import annotations

import pytest

from scue.layer1.strata.evaluation import (
    LatencyMetrics,
    LayerMetrics,
    StabilityMetrics,
    StrataScorecard,
    StructureMetrics,
    TransitionMetrics,
)
from scue.layer1.strata.promotion import (
    TIER_REQUIREMENTS,
    PromotionVerdict,
    TierRequirements,
    check_promotion,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _good_scorecard(**overrides) -> StrataScorecard:
    """Build a scorecard that passes all tier requirements."""
    sc = StrataScorecard(
        structure=StructureMetrics(
            boundary_hit_rate=0.9,
            label_agreement=0.85,
            section_count_delta=0,
        ),
        layers=LayerMetrics(
            layer_f1=0.8,
            false_enter_count=1,
            false_exit_count=1,
        ),
        transitions=TransitionMetrics(
            transition_precision=0.8,
            transition_recall=0.75,
            drop_precision=0.9,
            breakdown_precision=0.85,
            fill_precision=0.7,
        ),
        stability=StabilityMetrics(
            boundary_jitter_seconds=0.5,
            boundary_jitter_beats=1.0,
            label_flip_rate=0.05,
            off_grid_rate=0.1,
            transition_false_positives_per_minute=0.5,
        ),
        latency=LatencyMetrics(
            total_analysis_seconds=3.0,
            per_update_latency_seconds=0.05,
        ),
        fingerprint="test_fp",
        tier="standard",
        source="analysis",
    )
    # Apply overrides
    for key, value in overrides.items():
        parts = key.split(".")
        if len(parts) == 2:
            group = getattr(sc, parts[0])
            setattr(group, parts[1], value)
        else:
            setattr(sc, key, value)
    return sc


# ---------------------------------------------------------------------------
# Quick tier tests
# ---------------------------------------------------------------------------


class TestQuickPromotion:

    def test_good_scorecard_passes(self) -> None:
        sc = _good_scorecard()
        verdict = check_promotion(sc, "quick")
        assert verdict.eligible is True
        assert len(verdict.failing_checks) == 0

    def test_low_boundary_hit_rate_fails(self) -> None:
        sc = _good_scorecard(**{"structure.boundary_hit_rate": 0.4})
        verdict = check_promotion(sc, "quick")
        assert verdict.eligible is False
        assert any("boundary_hit_rate" in f for f in verdict.failing_checks)

    def test_slow_latency_fails(self) -> None:
        sc = _good_scorecard(**{"latency.total_analysis_seconds": 15.0})
        verdict = check_promotion(sc, "quick")
        assert verdict.eligible is False
        assert any("latency" in f for f in verdict.failing_checks)


# ---------------------------------------------------------------------------
# Standard tier tests
# ---------------------------------------------------------------------------


class TestStandardPromotion:

    def test_good_scorecard_passes(self) -> None:
        sc = _good_scorecard()
        verdict = check_promotion(sc, "standard")
        assert verdict.eligible is True

    def test_low_layer_f1_fails(self) -> None:
        sc = _good_scorecard(**{"layers.layer_f1": 0.3})
        verdict = check_promotion(sc, "standard")
        assert verdict.eligible is False
        assert any("layer_f1" in f for f in verdict.failing_checks)

    def test_low_boundary_fails(self) -> None:
        sc = _good_scorecard(**{"structure.boundary_hit_rate": 0.6})
        verdict = check_promotion(sc, "standard")
        assert verdict.eligible is False


# ---------------------------------------------------------------------------
# Live tier tests
# ---------------------------------------------------------------------------


class TestLivePromotion:

    def test_good_scorecard_with_perturbations_passes(self) -> None:
        sc = _good_scorecard(**{"latency.total_analysis_seconds": 0.05})
        perturbation_results = {
            "baseline": _good_scorecard(),
            "shift_1": _good_scorecard(),
            "halve": _good_scorecard(),
        }
        verdict = check_promotion(sc, "live", perturbation_results)
        assert verdict.eligible is True

    def test_missing_perturbation_suite_fails(self) -> None:
        sc = _good_scorecard()
        verdict = check_promotion(sc, "live", perturbation_results=None)
        assert verdict.eligible is False
        assert any("perturbation_suite" in f for f in verdict.failing_checks)

    def test_high_jitter_fails(self) -> None:
        sc = _good_scorecard(**{"stability.boundary_jitter_beats": 3.0})
        perturbation_results = {"baseline": _good_scorecard(), "test": _good_scorecard()}
        verdict = check_promotion(sc, "live", perturbation_results)
        assert verdict.eligible is False
        assert any("jitter_beats" in f for f in verdict.failing_checks)

    def test_high_flip_rate_fails(self) -> None:
        sc = _good_scorecard(**{"stability.label_flip_rate": 0.5})
        perturbation_results = {"baseline": _good_scorecard(), "test": _good_scorecard()}
        verdict = check_promotion(sc, "live", perturbation_results)
        assert verdict.eligible is False
        assert any("flip_rate" in f for f in verdict.failing_checks)

    def test_perturbation_collapse_fails(self) -> None:
        """If a perturbation run has 0 boundary_hit_rate, method collapsed."""
        sc = _good_scorecard()
        collapsed = _good_scorecard(**{"structure.boundary_hit_rate": 0.0})
        perturbation_results = {
            "baseline": _good_scorecard(),
            "bad_perturbation": collapsed,
        }
        verdict = check_promotion(sc, "live", perturbation_results)
        assert verdict.eligible is False
        assert any("bad_perturbation" in f for f in verdict.failing_checks)

    def test_high_latency_fails(self) -> None:
        sc = _good_scorecard(**{"latency.total_analysis_seconds": 1.0})
        perturbation_results = {"baseline": _good_scorecard(), "test": _good_scorecard()}
        verdict = check_promotion(sc, "live", perturbation_results)
        assert verdict.eligible is False
        assert any("latency" in f for f in verdict.failing_checks)


# ---------------------------------------------------------------------------
# Deep tier tests
# ---------------------------------------------------------------------------


class TestDeepPromotion:

    def test_good_scorecard_passes(self) -> None:
        sc = _good_scorecard()
        verdict = check_promotion(sc, "deep")
        assert verdict.eligible is True

    def test_needs_higher_boundary_than_standard(self) -> None:
        """Deep requires 0.8, standard only 0.75."""
        sc = _good_scorecard(**{"structure.boundary_hit_rate": 0.77})
        standard_verdict = check_promotion(sc, "standard")
        deep_verdict = check_promotion(sc, "deep")
        assert standard_verdict.eligible is True
        assert deep_verdict.eligible is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_unknown_tier(self) -> None:
        sc = _good_scorecard()
        verdict = check_promotion(sc, "nonexistent")
        assert verdict.eligible is False
        assert any("Unknown tier" in f for f in verdict.failing_checks)

    def test_custom_requirements(self) -> None:
        sc = _good_scorecard(**{"structure.boundary_hit_rate": 0.95})
        custom = TierRequirements(
            tier="custom",
            min_boundary_hit_rate=0.99,
        )
        verdict = check_promotion(sc, "custom", requirements=custom)
        assert verdict.eligible is False

    def test_all_tiers_have_requirements(self) -> None:
        for tier in ["quick", "standard", "live", "live_offline", "deep"]:
            assert tier in TIER_REQUIREMENTS

    def test_verdict_serialization(self) -> None:
        sc = _good_scorecard()
        verdict = check_promotion(sc, "quick")
        data = verdict.to_dict()
        assert data["eligible"] is True
        assert data["tier"] == "quick"
        assert isinstance(data["passing_checks"], list)


# ---------------------------------------------------------------------------
# Engine priors wiring tests
# ---------------------------------------------------------------------------


class TestEnginePriorsWiring:

    def test_engine_accepts_priors_param(self) -> None:
        """StrataEngine.__init__ should accept optional priors parameter."""
        from unittest.mock import MagicMock
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.priors import load_default_priors

        # Mock dependencies
        mock_store = MagicMock()
        priors = load_default_priors()

        # Should not raise
        engine = StrataEngine(
            tracks_dir=MagicMock(),
            strata_store=mock_store,
            priors=priors,
        )
        assert engine._priors is priors

    def test_engine_works_without_priors(self) -> None:
        """StrataEngine should work identically when priors=None (default)."""
        from unittest.mock import MagicMock
        from scue.layer1.strata.engine import StrataEngine

        mock_store = MagicMock()
        engine = StrataEngine(
            tracks_dir=MagicMock(),
            strata_store=mock_store,
        )
        assert engine._priors is None

    def test_live_analyzer_uses_priors_values(self) -> None:
        """Verify that priors match what LiveStrataAnalyzer hardcodes."""
        from scue.layer1.strata.priors import load_default_priors
        from scue.layer1.strata.live_analyzer import SECTION_ENERGY, SECTION_TREND

        priors = load_default_priors()
        # Every hardcoded value should match the priors registry
        for label, energy in SECTION_ENERGY.items():
            assert priors.section_energy.as_dict()[label] == energy, (
                f"Priors mismatch for section energy '{label}'"
            )
        for label, trend in SECTION_TREND.items():
            assert priors.section_trend.as_dict()[label] == trend, (
                f"Priors mismatch for section trend '{label}'"
            )
