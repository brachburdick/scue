"""Tests for source-aware Strata storage.

Verifies:
- Source-qualified file naming: {fp}.{tier}.{source}.json
- Backward compat: legacy {fp}.{tier}.json loads as source="analysis"
- load_all returns nested {tier: {source: formula}} structure
- list_tracks includes source info
"""

from pathlib import Path

import json
import pytest

from scue.layer1.strata.models import ArrangementFormula, formula_to_dict
from scue.layer1.strata.storage import DEFAULT_SOURCE, StrataStore, VALID_SOURCES


def _make_formula(fp: str = "abc123", tier: str = "quick", source: str = "analysis") -> ArrangementFormula:
    """Create a minimal ArrangementFormula for testing."""
    return ArrangementFormula(
        fingerprint=fp,
        pipeline_tier=tier,
        analysis_source=source,
        compute_time_seconds=0.1,
    )


class TestSourceQualifiedPaths:
    """Test that save/load use source-qualified filenames."""

    def test_save_creates_source_qualified_file(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        formula = _make_formula()
        path = store.save(formula, "quick", source="analysis")
        assert path.name == "abc123.quick.analysis.json"
        assert path.exists()

    def test_save_reanalyzed_source(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        formula = _make_formula(source="pioneer_reanalyzed")
        path = store.save(formula, "quick", source="pioneer_reanalyzed")
        assert path.name == "abc123.quick.pioneer_reanalyzed.json"
        assert path.exists()

    def test_load_source_qualified(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        formula = _make_formula(source="pioneer_reanalyzed")
        store.save(formula, "quick", source="pioneer_reanalyzed")

        loaded = store.load("abc123", "quick", source="pioneer_reanalyzed")
        assert loaded is not None
        assert loaded.analysis_source == "pioneer_reanalyzed"

    def test_load_wrong_source_returns_none(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        formula = _make_formula(source="analysis")
        store.save(formula, "quick", source="analysis")

        # Loading with a different source should not find it
        loaded = store.load("abc123", "quick", source="pioneer_reanalyzed")
        assert loaded is None

    def test_multiple_sources_coexist(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)

        # Save same tier with different sources
        f1 = _make_formula(source="analysis")
        f2 = _make_formula(source="pioneer_reanalyzed")
        f2.arrangement_complexity = 0.9  # distinguish them

        store.save(f1, "quick", source="analysis")
        store.save(f2, "quick", source="pioneer_reanalyzed")

        loaded1 = store.load("abc123", "quick", source="analysis")
        loaded2 = store.load("abc123", "quick", source="pioneer_reanalyzed")

        assert loaded1 is not None
        assert loaded2 is not None
        assert loaded1.arrangement_complexity != loaded2.arrangement_complexity

    def test_invalid_source_raises(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        formula = _make_formula()
        with pytest.raises(ValueError, match="Invalid source"):
            store.save(formula, "quick", source="bogus")


class TestBackwardCompat:
    """Test that legacy files without source suffix work."""

    def test_legacy_file_loads_as_default_source(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)

        # Write a legacy file manually: {fp}.{tier}.json (no source)
        formula = _make_formula()
        legacy_path = tmp_path / "abc123.quick.json"
        legacy_path.write_text(json.dumps(formula_to_dict(formula), indent=2))

        # Load with default source should find it
        loaded = store.load("abc123", "quick")
        assert loaded is not None
        assert loaded.fingerprint == "abc123"

    def test_source_qualified_takes_precedence_over_legacy(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)

        # Write both legacy and source-qualified
        f_legacy = _make_formula()
        f_legacy.arrangement_complexity = 0.1
        legacy_path = tmp_path / "abc123.quick.json"
        legacy_path.write_text(json.dumps(formula_to_dict(f_legacy), indent=2))

        f_new = _make_formula()
        f_new.arrangement_complexity = 0.9
        store.save(f_new, "quick", source="analysis")

        # Source-qualified should win
        loaded = store.load("abc123", "quick")
        assert loaded is not None
        assert loaded.arrangement_complexity == 0.9


class TestLoadAll:
    """Test load_all returns nested tier→source structure."""

    def test_load_all_nested_structure(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)

        store.save(_make_formula(source="analysis"), "quick", source="analysis")
        store.save(
            _make_formula(source="pioneer_reanalyzed"),
            "quick",
            source="pioneer_reanalyzed",
        )
        store.save(_make_formula(source="analysis"), "standard", source="analysis")

        results = store.load_all("abc123")

        assert "quick" in results
        assert "standard" in results
        assert "analysis" in results["quick"]
        assert "pioneer_reanalyzed" in results["quick"]
        assert "analysis" in results["standard"]

    def test_load_all_empty(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        results = store.load_all("nonexistent")
        assert results == {}


class TestListTracks:
    """Test list_tracks includes source info."""

    def test_list_tracks_with_sources(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        store.save(_make_formula(source="analysis"), "quick", source="analysis")
        store.save(
            _make_formula(source="pioneer_reanalyzed"),
            "quick",
            source="pioneer_reanalyzed",
        )

        tracks = store.list_tracks()
        assert len(tracks) == 1
        assert tracks[0]["fingerprint"] == "abc123"
        assert "quick" in tracks[0]["tiers"]
        assert "analysis" in tracks[0]["tiers"]["quick"]
        assert "pioneer_reanalyzed" in tracks[0]["tiers"]["quick"]

    def test_list_tracks_with_legacy_file(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)

        # Write a legacy file
        formula = _make_formula()
        legacy_path = tmp_path / "abc123.quick.json"
        legacy_path.write_text(json.dumps(formula_to_dict(formula), indent=2))

        tracks = store.list_tracks()
        assert len(tracks) == 1
        assert tracks[0]["fingerprint"] == "abc123"
        assert "quick" in tracks[0]["tiers"]
        assert "analysis" in tracks[0]["tiers"]["quick"]


class TestDelete:
    """Test source-aware deletion."""

    def test_delete_specific_source(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        store.save(_make_formula(source="analysis"), "quick", source="analysis")
        store.save(
            _make_formula(source="pioneer_reanalyzed"),
            "quick",
            source="pioneer_reanalyzed",
        )

        # Delete only the reanalyzed source
        deleted = store.delete("abc123", "quick", source="pioneer_reanalyzed")
        assert deleted is True

        # Original still exists
        assert store.load("abc123", "quick", source="analysis") is not None
        # Reanalyzed is gone
        assert store.load("abc123", "quick", source="pioneer_reanalyzed") is None


class TestAnalysisSourceField:
    """Test that analysis_source field round-trips through serialization."""

    def test_analysis_source_serialization(self, tmp_path: Path) -> None:
        store = StrataStore(tmp_path)
        formula = _make_formula(source="pioneer_reanalyzed")
        store.save(formula, "quick", source="pioneer_reanalyzed")

        loaded = store.load("abc123", "quick", source="pioneer_reanalyzed")
        assert loaded is not None
        assert loaded.analysis_source == "pioneer_reanalyzed"

    def test_legacy_formula_gets_default_source(self, tmp_path: Path) -> None:
        """Old formulas without analysis_source field default to 'analysis'."""
        store = StrataStore(tmp_path)

        # Write a formula dict without analysis_source field
        formula = _make_formula()
        d = formula_to_dict(formula)
        del d["analysis_source"]  # simulate old data
        path = tmp_path / "abc123.quick.analysis.json"
        path.write_text(json.dumps(d, indent=2))

        loaded = store.load("abc123", "quick")
        assert loaded is not None
        assert loaded.analysis_source == "analysis"
