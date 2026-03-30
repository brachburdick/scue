"""Tests for the hybrid Strata tier (Pioneer sections + audio detail)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestHybridRouting:
    """Test that analyze() routes to hybrid correctly."""

    def test_analyze_routes_to_hybrid(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tmp_path / "tracks", strata_store=store)

        with patch.object(engine, "analyze_hybrid") as mock_hybrid:
            mock_hybrid.return_value = MagicMock()
            result = engine.analyze("abc123", ["hybrid"])
            mock_hybrid.assert_called_once_with("abc123", analysis_version=None)
            assert "hybrid" in result


class TestHybridTierValidation:
    """Test hybrid tier error handling."""

    def test_hybrid_requires_pioneer_sidecar(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        tracks_dir = tmp_path / "tracks"
        (tracks_dir / "abc123").mkdir(parents=True)

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tracks_dir, strata_store=store)

        with pytest.raises(ValueError, match="No saved Pioneer data"):
            engine.analyze_hybrid("abc123")

    def test_hybrid_requires_phrases(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        tracks_dir = tmp_path / "tracks"
        fp_dir = tracks_dir / "abc123"
        fp_dir.mkdir(parents=True)

        # Pioneer sidecar with empty phrases
        sidecar = {"phrases": [], "beat_grid": [{"beat_number": 1, "time_ms": 0, "bpm": 128}]}
        (fp_dir / "live_pioneer.json").write_text(json.dumps(sidecar))

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tracks_dir, strata_store=store)

        with pytest.raises(ValueError, match="missing phrases"):
            engine.analyze_hybrid("abc123")

    def test_hybrid_requires_track_analysis(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        tracks_dir = tmp_path / "tracks"
        fp_dir = tracks_dir / "abc123"
        fp_dir.mkdir(parents=True)

        # Valid Pioneer sidecar
        sidecar = {
            "phrases": [{"start_beat": 1, "end_beat": 128, "kind": "intro"}],
            "beat_grid": [{"beat_number": 1, "time_ms": 0, "bpm": 128}],
        }
        (fp_dir / "live_pioneer.json").write_text(json.dumps(sidecar))

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tracks_dir, strata_store=store)

        with pytest.raises(ValueError, match="No track analysis"):
            engine.analyze_hybrid("abc123")


class TestHybridStorageRoundtrip:
    """Test that hybrid tier is stored and loaded correctly."""

    def test_hybrid_tier_in_valid_tiers(self) -> None:
        from scue.layer1.strata.storage import VALID_TIERS
        assert "hybrid" in VALID_TIERS

    def test_save_load_hybrid(self, tmp_path: Path) -> None:
        from scue.layer1.strata.models import ArrangementFormula
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        formula = ArrangementFormula(
            fingerprint="test_fp_hybrid",
            pipeline_tier="hybrid",
            analysis_source="pioneer_sections+audio_detail",
        )
        path = store.save(formula, "hybrid", source="pioneer_live")
        assert path.exists()

        loaded = store.load("test_fp_hybrid", "hybrid", source="pioneer_live")
        assert loaded is not None
        assert loaded.pipeline_tier == "hybrid"
        assert loaded.analysis_source == "pioneer_sections+audio_detail"

    def test_hybrid_appears_in_load_all(self, tmp_path: Path) -> None:
        from scue.layer1.strata.models import ArrangementFormula
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        formula = ArrangementFormula(
            fingerprint="test_fp_all",
            pipeline_tier="hybrid",
        )
        store.save(formula, "hybrid", source="pioneer_live")

        all_results = store.load_all("test_fp_all")
        assert "hybrid" in all_results
        assert "pioneer_live" in all_results["hybrid"]
