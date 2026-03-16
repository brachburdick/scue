"""Tests for EDM flow model labeler."""

from scue.layer1.detectors.flow_model import (
    classify_sections,
    _energy_classify,
    _detect_builds,
    _detect_fakeouts,
    _enforce_structure,
)
from scue.layer1.models import Section


def _make_section(label: str, start: float, end: float, bar_count: int = 8,
                  original_label: str = "") -> Section:
    return Section(
        label=label,
        start=start,
        end=end,
        bar_count=bar_count,
        expected_bar_count=8,
        original_label=original_label or label,
    )


def _make_features(rms_mean: float, centroid_mean: float = 2000.0,
                   rms_slope: float = 0.0, centroid_slope: float = 0.0) -> dict:
    return {
        "rms_mean": rms_mean,
        "rms_max": rms_mean * 1.5,
        "rms_slope": rms_slope,
        "centroid_mean": centroid_mean,
        "centroid_slope": centroid_slope,
        "flux_mean": rms_mean * 0.5,
        "onset_density": 2.0,
    }


class TestEnergyClassify:
    """Tests for energy-based section classification."""

    def test_high_energy_is_drop(self) -> None:
        """High RMS ratio sections should be classified as drops."""
        sections = [_make_section("chorus", 0.0, 30.0, original_label="chorus")]
        feats = [_make_features(rms_mean=0.15)]
        track_stats = {"rms_mean": 0.1, "centroid_mean": 2000.0}

        result = _energy_classify(sections, feats, track_stats)
        assert result[0].label == "drop"

    def test_low_energy_is_breakdown(self) -> None:
        """Low RMS ratio sections (from break label) should be breakdowns."""
        sections = [_make_section("break", 0.0, 30.0, original_label="break")]
        feats = [_make_features(rms_mean=0.05)]
        track_stats = {"rms_mean": 0.1, "centroid_mean": 2000.0}

        result = _energy_classify(sections, feats, track_stats)
        assert result[0].label == "breakdown"

    def test_intro_preserved(self) -> None:
        """Intro label should be preserved regardless of energy."""
        sections = [_make_section("intro", 0.0, 16.0, original_label="intro")]
        feats = [_make_features(rms_mean=0.15)]
        track_stats = {"rms_mean": 0.1, "centroid_mean": 2000.0}

        result = _energy_classify(sections, feats, track_stats)
        assert result[0].label == "intro"


class TestBuildDetection:
    """Tests for build section detection."""

    def test_rising_energy_before_drop(self) -> None:
        """Section with rising RMS before a drop should become a build."""
        sections = [
            _make_section("verse", 0.0, 16.0),
            _make_section("drop", 16.0, 48.0),
        ]
        feats = [
            _make_features(rms_mean=0.08, rms_slope=0.002),
            _make_features(rms_mean=0.15),
        ]
        track_stats = {"rms_mean": 0.1, "centroid_mean": 2000.0}

        result = _detect_builds(sections, feats, track_stats)
        assert result[0].label == "build"
        assert result[1].label == "drop"

    def test_no_build_without_drop(self) -> None:
        """Rising energy without a following drop should not become build."""
        sections = [
            _make_section("verse", 0.0, 16.0),
            _make_section("verse", 16.0, 32.0),
        ]
        feats = [
            _make_features(rms_mean=0.08, rms_slope=0.002),
            _make_features(rms_mean=0.09),
        ]
        track_stats = {"rms_mean": 0.1, "centroid_mean": 2000.0}

        result = _detect_builds(sections, feats, track_stats)
        assert result[0].label == "verse"


class TestFakeoutDetection:
    """Tests for fakeout drop detection."""

    def test_short_drop_before_build(self) -> None:
        """Short drop (≤4 bars) followed by build is a fakeout."""
        sections = [
            _make_section("drop", 0.0, 8.0, bar_count=4),
            _make_section("build", 8.0, 24.0),
        ]

        result = _detect_fakeouts(sections)
        assert result[0].label == "fakeout"
        assert result[0].fakeout is True

    def test_long_drop_not_fakeout(self) -> None:
        """Normal-length drop should not be a fakeout."""
        sections = [
            _make_section("drop", 0.0, 30.0, bar_count=16),
            _make_section("breakdown", 30.0, 60.0),
        ]

        result = _detect_fakeouts(sections)
        assert result[0].label == "drop"
        assert result[0].fakeout is False


class TestEnforceStructure:
    """Tests for structural constraint enforcement."""

    def test_first_section_is_intro(self) -> None:
        """First section should be relabeled to intro."""
        sections = [
            _make_section("verse", 0.0, 16.0),
            _make_section("drop", 16.0, 48.0),
        ]

        result = _enforce_structure(sections)
        assert result[0].label == "intro"

    def test_last_section_is_outro(self) -> None:
        """Last section should be relabeled to outro."""
        sections = [
            _make_section("intro", 0.0, 16.0),
            _make_section("verse", 16.0, 48.0),
        ]

        result = _enforce_structure(sections)
        assert result[-1].label == "outro"

    def test_confidence_reduced_on_relabel(self) -> None:
        """Relabeled sections should have reduced confidence."""
        sections = [
            _make_section("drop", 0.0, 16.0),
        ]
        sections[0] = Section(
            label="drop", start=0.0, end=16.0, confidence=0.9,
            bar_count=8, expected_bar_count=8, original_label="chorus",
        )

        result = _enforce_structure(sections)
        # Both intro and outro forced — confidence should be capped
        assert result[0].confidence <= 0.6


class TestClassifySections:
    """Integration tests for the full flow model."""

    def test_typical_edm_flow(self) -> None:
        """A typical EDM arrangement should produce a valid flow."""
        sections = [
            _make_section("intro", 0.0, 15.0, original_label="intro"),
            _make_section("verse", 15.0, 30.0, original_label="verse"),
            _make_section("chorus", 30.0, 60.0, original_label="chorus"),
            _make_section("break", 60.0, 75.0, original_label="break"),
            _make_section("chorus", 75.0, 105.0, original_label="chorus"),
            _make_section("outro", 105.0, 120.0, original_label="outro"),
        ]
        feats = [
            _make_features(0.04),   # intro: low energy
            _make_features(0.06, rms_slope=0.001),  # verse: moderate, rising
            _make_features(0.15),   # chorus → drop: high energy
            _make_features(0.05),   # break → breakdown: low
            _make_features(0.14),   # chorus → drop: high
            _make_features(0.03),   # outro: low
        ]
        track_stats = {"rms_mean": 0.08, "centroid_mean": 2000.0}

        result = classify_sections(sections, feats, track_stats)
        labels = [s.label for s in result]

        assert labels[0] == "intro"
        assert labels[-1] == "outro"
        assert "drop" in labels
        # Should have some valid EDM structure
        assert len(result) == 6
