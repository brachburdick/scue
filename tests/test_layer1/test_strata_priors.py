"""Tests for the EDM priors registry."""

from __future__ import annotations

import json

import pytest

from scue.layer1.strata.priors import (
    EDMPriors,
    EDMStructurePrior,
    EnergyPrior,
    PatternPrior,
    PhraseMapping,
    PriorKind,
    SectionEnergyPrior,
    SectionTrendPrior,
    StemActivityPrior,
    TransitionPrior,
    load_default_priors,
    priors_from_dict,
    priors_to_dict,
)


class TestLoadDefaultPriors:
    """Test that load_default_priors returns a fully populated EDMPriors."""

    def test_returns_edm_priors(self) -> None:
        priors = load_default_priors()
        assert isinstance(priors, EDMPriors)

    def test_version(self) -> None:
        priors = load_default_priors()
        assert priors.version == "1.0.0"

    def test_all_sub_priors_populated(self) -> None:
        priors = load_default_priors()
        assert isinstance(priors.section_energy, SectionEnergyPrior)
        assert isinstance(priors.section_trend, SectionTrendPrior)
        assert isinstance(priors.phrase_mapping, PhraseMapping)
        assert isinstance(priors.transitions, TransitionPrior)
        assert isinstance(priors.patterns, PatternPrior)
        assert isinstance(priors.energy, EnergyPrior)
        assert isinstance(priors.stem_activity, StemActivityPrior)
        assert isinstance(priors.edm_structure, EDMStructurePrior)


class TestSectionEnergyPriorMatchesLiveAnalyzer:
    """Verify priors match the hardcoded values in live_analyzer.py."""

    def test_section_energy_values(self) -> None:
        """Must match SECTION_ENERGY dict in live_analyzer.py."""
        priors = load_default_priors()
        energy = priors.section_energy.as_dict()
        assert energy["intro"] == 0.3
        assert energy["verse"] == 0.5
        assert energy["chorus"] == 0.75
        assert energy["bridge"] == 0.5
        assert energy["breakdown"] == 0.3
        assert energy["build"] == 0.6
        assert energy["drop"] == 0.9
        assert energy["outro"] == 0.25

    def test_section_trend_values(self) -> None:
        """Must match SECTION_TREND dict in live_analyzer.py."""
        priors = load_default_priors()
        trend = priors.section_trend.as_dict()
        assert trend["intro"] == "rising"
        assert trend["verse"] == "stable"
        assert trend["chorus"] == "peak"
        assert trend["bridge"] == "stable"
        assert trend["breakdown"] == "valley"
        assert trend["build"] == "rising"
        assert trend["drop"] == "peak"
        assert trend["outro"] == "falling"

    def test_phrase_mapping_values(self) -> None:
        """Must match PHRASE_KIND_MAP in live_analyzer.py."""
        priors = load_default_priors()
        mapping = priors.phrase_mapping.mapping
        assert mapping["intro"] == "intro"
        assert mapping["buildup"] == "build"
        assert mapping["drop"] == "drop"
        assert mapping["breakdown"] == "breakdown"
        assert len(mapping) == 9


class TestTransitionPriorMatchesTransitions:
    """Verify priors match the hardcoded values in transitions.py."""

    def test_energy_threshold(self) -> None:
        priors = load_default_priors()
        assert priors.transitions.energy_threshold == 0.15

    def test_drop_delta(self) -> None:
        priors = load_default_priors()
        assert priors.transitions.drop_energy_delta == 0.2

    def test_breakdown_delta(self) -> None:
        priors = load_default_priors()
        assert priors.transitions.breakdown_energy_delta == -0.2

    def test_fill_spike_ratio(self) -> None:
        priors = load_default_priors()
        assert priors.transitions.fill_spike_ratio == 1.8

    def test_comparison_window(self) -> None:
        priors = load_default_priors()
        assert priors.transitions.comparison_window_bars == 2


class TestPatternPriorMatchesPatterns:
    """Verify priors match the hardcoded values in patterns.py."""

    def test_similarity_threshold(self) -> None:
        priors = load_default_priors()
        assert priors.patterns.similarity_threshold == 0.85

    def test_min_repeats(self) -> None:
        priors = load_default_priors()
        assert priors.patterns.min_repeats == 2


class TestEnergyPriorMatchesEnergy:
    """Verify priors match the hardcoded values in energy.py."""

    def test_frequency_bands(self) -> None:
        priors = load_default_priors()
        assert priors.energy.low_band == (20, 200)
        assert priors.energy.mid_band == (200, 2500)
        assert priors.energy.high_band == (2500, 11025)

    def test_pseudo_activity_threshold(self) -> None:
        priors = load_default_priors()
        assert priors.energy.threshold_ratio == 0.15

    def test_min_span_bars(self) -> None:
        priors = load_default_priors()
        assert priors.energy.min_span_bars == 2

    def test_band_stem_mapping(self) -> None:
        priors = load_default_priors()
        assert priors.energy.band_stem_mapping["low"] == "bass"
        assert priors.energy.band_stem_mapping["mid"] == "other"
        assert priors.energy.band_stem_mapping["high"] == "other"


class TestStemActivityPriorMatchesPerStem:
    """Verify priors match the hardcoded values in per_stem.py."""

    def test_activity_threshold(self) -> None:
        priors = load_default_priors()
        assert priors.stem_activity.activity_threshold == 0.08

    def test_min_activity_bars(self) -> None:
        priors = load_default_priors()
        assert priors.stem_activity.min_activity_bars == 2

    def test_merge_window(self) -> None:
        priors = load_default_priors()
        assert priors.stem_activity.merge_window_seconds == 2.0


class TestPriorKinds:
    """Verify each prior has the correct kind tag."""

    def test_section_energy_is_hard(self) -> None:
        priors = load_default_priors()
        assert priors.section_energy.kind == PriorKind.HARD

    def test_section_trend_is_hard(self) -> None:
        priors = load_default_priors()
        assert priors.section_trend.kind == PriorKind.HARD

    def test_phrase_mapping_is_hard(self) -> None:
        priors = load_default_priors()
        assert priors.phrase_mapping.kind == PriorKind.HARD

    def test_transitions_is_soft(self) -> None:
        priors = load_default_priors()
        assert priors.transitions.kind == PriorKind.SOFT

    def test_patterns_is_soft(self) -> None:
        priors = load_default_priors()
        assert priors.patterns.kind == PriorKind.SOFT

    def test_energy_is_soft(self) -> None:
        priors = load_default_priors()
        assert priors.energy.kind == PriorKind.SOFT

    def test_stem_activity_is_soft(self) -> None:
        priors = load_default_priors()
        assert priors.stem_activity.kind == PriorKind.SOFT

    def test_edm_structure_is_diagnostic(self) -> None:
        priors = load_default_priors()
        assert priors.edm_structure.kind == PriorKind.DIAGNOSTIC


class TestSerializationRoundTrip:
    """Test priors_to_dict / priors_from_dict round-trip."""

    def test_round_trip_preserves_values(self) -> None:
        original = load_default_priors()
        data = priors_to_dict(original)
        restored = priors_from_dict(data)

        assert restored.version == original.version
        assert restored.section_energy.drop == original.section_energy.drop
        assert restored.transitions.energy_threshold == original.transitions.energy_threshold
        assert restored.energy.low_band == original.energy.low_band
        assert restored.edm_structure.typical_bpm_range == original.edm_structure.typical_bpm_range
        assert restored.stem_activity.activity_threshold == original.stem_activity.activity_threshold
        assert restored.phrase_mapping.mapping == original.phrase_mapping.mapping

    def test_serialized_is_json_compatible(self) -> None:
        priors = load_default_priors()
        data = priors_to_dict(priors)
        # Must not raise
        json_str = json.dumps(data)
        assert isinstance(json_str, str)
        # And must parse back
        parsed = json.loads(json_str)
        assert parsed["version"] == "1.0.0"

    def test_round_trip_kinds(self) -> None:
        original = load_default_priors()
        data = priors_to_dict(original)
        restored = priors_from_dict(data)

        assert restored.section_energy.kind == PriorKind.HARD
        assert restored.transitions.kind == PriorKind.SOFT
        assert restored.edm_structure.kind == PriorKind.DIAGNOSTIC

    def test_from_empty_dict_returns_defaults(self) -> None:
        restored = priors_from_dict({})
        defaults = load_default_priors()
        assert restored.section_energy.drop == defaults.section_energy.drop
        assert restored.energy.low_band == defaults.energy.low_band


class TestEDMStructurePrior:
    """Test the diagnostic EDM structure prior."""

    def test_typical_phrase_bars(self) -> None:
        priors = load_default_priors()
        assert 16 in priors.edm_structure.typical_phrase_bars
        assert 32 in priors.edm_structure.typical_phrase_bars

    def test_typical_bpm_range(self) -> None:
        priors = load_default_priors()
        low, high = priors.edm_structure.typical_bpm_range
        assert low == 100.0
        assert high == 180.0

    def test_section_vocabulary(self) -> None:
        priors = load_default_priors()
        vocab = priors.edm_structure.edm_section_vocabulary
        assert "drop" in vocab
        assert "breakdown" in vocab
        assert "build" in vocab

    def test_typical_meter(self) -> None:
        priors = load_default_priors()
        assert priors.edm_structure.typical_meter == (4, 4)
