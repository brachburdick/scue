"""Tests for Strata perturbation suites."""

from __future__ import annotations

import pytest

from scue.layer1.strata.perturbations import (
    DEFAULT_GRID_PACK,
    PerturbationPack,
    add_drift,
    conflict_sources,
    create_sparse_gaps,
    double_tempo,
    halve_tempo,
    run_sensitivity_suite,
    shift_downbeat,
    simulate_cue_jump,
    simulate_loop,
    simulate_missing_metadata,
    simulate_tempo_shift,
)
from scue.layer1.strata.evaluation import (
    GoldAnnotation,
    GoldSection,
    GoldTransition,
    StrataScorecard,
)
from scue.layer1.strata.models import (
    ArrangementFormula,
    SectionArrangement,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_grid(bpm: float = 128.0, num_beats: int = 128) -> list[dict]:
    spacing = 60000.0 / bpm
    return [
        {"beat_number": i + 1, "time_ms": i * spacing, "bpm": bpm}
        for i in range(num_beats)
    ]


def _make_phrases() -> list[dict]:
    return [
        {"start_beat": 1, "end_beat": 33, "kind": "intro"},
        {"start_beat": 33, "end_beat": 65, "kind": "build"},
        {"start_beat": 65, "end_beat": 129, "kind": "drop"},
    ]


def _make_gold() -> GoldAnnotation:
    return GoldAnnotation(
        fingerprint="test",
        sections=[
            GoldSection(label="intro", start=0.0, end=15.0),
            GoldSection(label="build", start=15.0, end=30.0),
            GoldSection(label="drop", start=30.0, end=60.0),
        ],
        transitions=[
            GoldTransition(type="energy_shift", timestamp=15.0),
            GoldTransition(type="drop_impact", timestamp=30.0),
        ],
    )


# ---------------------------------------------------------------------------
# Grid perturbation tests
# ---------------------------------------------------------------------------


class TestShiftDownbeat:

    def test_shifts_all_beat_numbers(self) -> None:
        grid = _make_grid(num_beats=10)
        shifted = shift_downbeat(grid, shift_beats=1)
        for orig, new in zip(grid, shifted):
            assert new["beat_number"] == orig["beat_number"] + 1

    def test_preserves_timing(self) -> None:
        grid = _make_grid(num_beats=10)
        shifted = shift_downbeat(grid, shift_beats=2)
        for orig, new in zip(grid, shifted):
            assert new["time_ms"] == orig["time_ms"]

    def test_negative_shift(self) -> None:
        grid = _make_grid(num_beats=10)
        shifted = shift_downbeat(grid, shift_beats=-1)
        assert shifted[0]["beat_number"] == grid[0]["beat_number"] - 1

    def test_empty_grid(self) -> None:
        assert shift_downbeat([], 1) == []

    def test_does_not_mutate_original(self) -> None:
        grid = _make_grid(num_beats=5)
        original_first = grid[0]["beat_number"]
        shift_downbeat(grid, 3)
        assert grid[0]["beat_number"] == original_first


class TestHalveTempo:

    def test_halves_entry_count(self) -> None:
        grid = _make_grid(num_beats=20)
        halved = halve_tempo(grid)
        assert len(halved) == 10

    def test_halves_bpm(self) -> None:
        grid = _make_grid(bpm=128.0, num_beats=10)
        halved = halve_tempo(grid)
        assert halved[0]["bpm"] == 64.0

    def test_keeps_every_other_entry(self) -> None:
        grid = _make_grid(num_beats=10)
        halved = halve_tempo(grid)
        for i, entry in enumerate(halved):
            assert entry["beat_number"] == grid[i * 2]["beat_number"]

    def test_empty_grid(self) -> None:
        assert halve_tempo([]) == []


class TestDoubleTempo:

    def test_increases_entry_count(self) -> None:
        grid = _make_grid(num_beats=10)
        doubled = double_tempo(grid)
        # 10 original + 9 interpolated = 19
        assert len(doubled) == 19

    def test_doubles_bpm(self) -> None:
        grid = _make_grid(bpm=128.0, num_beats=5)
        doubled = double_tempo(grid)
        assert doubled[0]["bpm"] == 256.0

    def test_empty_grid(self) -> None:
        assert double_tempo([]) == []


class TestAddDrift:

    def test_no_drift_at_start(self) -> None:
        grid = _make_grid(num_beats=10)
        drifted = add_drift(grid, max_drift_ms=100.0)
        assert drifted[0]["time_ms"] == grid[0]["time_ms"]

    def test_max_drift_at_end(self) -> None:
        grid = _make_grid(num_beats=10)
        drifted = add_drift(grid, max_drift_ms=100.0)
        assert abs(drifted[-1]["time_ms"] - grid[-1]["time_ms"] - 100.0) < 0.01

    def test_monotonic_drift(self) -> None:
        grid = _make_grid(num_beats=20)
        drifted = add_drift(grid, max_drift_ms=500.0)
        drifts = [d["time_ms"] - o["time_ms"] for o, d in zip(grid, drifted)]
        for i in range(1, len(drifts)):
            assert drifts[i] >= drifts[i - 1]

    def test_empty_grid(self) -> None:
        assert add_drift([], 100.0) == []


class TestCreateSparseGaps:

    def test_reduces_entry_count(self) -> None:
        grid = _make_grid(num_beats=100)
        sparse = create_sparse_gaps(grid, gap_ratio=0.3, seed=42)
        assert len(sparse) < len(grid)

    def test_keeps_first_entry(self) -> None:
        grid = _make_grid(num_beats=100)
        sparse = create_sparse_gaps(grid, gap_ratio=0.5, seed=42)
        assert sparse[0]["beat_number"] == grid[0]["beat_number"]

    def test_reproducible(self) -> None:
        grid = _make_grid(num_beats=50)
        a = create_sparse_gaps(grid, gap_ratio=0.3, seed=42)
        b = create_sparse_gaps(grid, gap_ratio=0.3, seed=42)
        assert len(a) == len(b)

    def test_zero_gap_ratio(self) -> None:
        grid = _make_grid(num_beats=10)
        sparse = create_sparse_gaps(grid, gap_ratio=0.0)
        assert len(sparse) == len(grid)

    def test_empty_grid(self) -> None:
        assert create_sparse_gaps([], 0.5) == []


class TestConflictSources:

    def test_merges_two_grids(self) -> None:
        a = _make_grid(bpm=128.0, num_beats=10)
        b = _make_grid(bpm=130.0, num_beats=10)
        merged = conflict_sources(a, b)
        assert len(merged) > 0

    def test_sorted_by_beat_number(self) -> None:
        a = _make_grid(bpm=128.0, num_beats=10)
        b = _make_grid(bpm=130.0, num_beats=10)
        merged = conflict_sources(a, b)
        beats = [e["beat_number"] for e in merged]
        assert beats == sorted(beats)


# ---------------------------------------------------------------------------
# Live perturbation tests
# ---------------------------------------------------------------------------


class TestSimulateTempoShift:

    def test_increases_bpm(self) -> None:
        phrases = _make_phrases()
        grid = _make_grid(bpm=128.0, num_beats=128)
        new_phrases, new_grid = simulate_tempo_shift(phrases, grid, shift_bpm=4.0)
        assert new_grid[0]["bpm"] == 132.0

    def test_preserves_phrase_structure(self) -> None:
        phrases = _make_phrases()
        grid = _make_grid(bpm=128.0, num_beats=128)
        new_phrases, _ = simulate_tempo_shift(phrases, grid, shift_bpm=4.0)
        assert len(new_phrases) == len(phrases)


class TestSimulateLoop:

    def test_adds_extra_phrase(self) -> None:
        phrases = _make_phrases()
        looped = simulate_loop(phrases, loop_start_beat=33, loop_length_beats=16)
        assert len(looped) == len(phrases) + 1

    def test_shifts_subsequent_phrases(self) -> None:
        phrases = _make_phrases()
        original_last_end = phrases[-1]["end_beat"]
        looped = simulate_loop(phrases, loop_start_beat=33, loop_length_beats=16)
        assert looped[-1]["end_beat"] == original_last_end + 16

    def test_empty_phrases(self) -> None:
        assert simulate_loop([], 10, 16) == []


class TestSimulateCueJump:

    def test_forward_jump_removes_phrases(self) -> None:
        phrases = _make_phrases()
        jumped = simulate_cue_jump(phrases, from_beat=33, to_beat=65)
        # Should keep intro (ends at 33) and drop (starts at 65), skip build
        total_phrases = len(jumped)
        assert total_phrases < len(phrases)

    def test_empty_phrases(self) -> None:
        assert simulate_cue_jump([], 10, 20) == []


class TestSimulateMissingMetadata:

    def test_reduces_phrase_count(self) -> None:
        phrases = _make_phrases()
        dropped = simulate_missing_metadata(phrases, drop_fraction=0.5, seed=42)
        assert len(dropped) <= len(phrases)

    def test_keeps_first_phrase(self) -> None:
        phrases = _make_phrases()
        dropped = simulate_missing_metadata(phrases, drop_fraction=0.9, seed=42)
        assert dropped[0]["kind"] == phrases[0]["kind"]

    def test_reproducible(self) -> None:
        phrases = _make_phrases()
        a = simulate_missing_metadata(phrases, 0.3, seed=42)
        b = simulate_missing_metadata(phrases, 0.3, seed=42)
        assert len(a) == len(b)

    def test_zero_drop(self) -> None:
        phrases = _make_phrases()
        dropped = simulate_missing_metadata(phrases, drop_fraction=0.0)
        assert len(dropped) == len(phrases)


# ---------------------------------------------------------------------------
# Sensitivity suite runner
# ---------------------------------------------------------------------------


class TestRunSensitivitySuite:

    def _mock_engine(self, beat_grid: list[dict], phrases: list[dict]) -> ArrangementFormula:
        """Simple mock engine that creates sections from phrases."""
        sections = []
        for p in phrases:
            bpm = beat_grid[0]["bpm"] if beat_grid else 128.0
            spacing_s = 60.0 / bpm
            start_s = (p["start_beat"] - 1) * spacing_s
            end_s = (p["end_beat"] - 1) * spacing_s
            sections.append(SectionArrangement(
                section_label=p.get("kind", "unknown"),
                section_start=start_s,
                section_end=end_s,
                active_layers=["drums"],
                active_patterns=[],
                transitions=[],
                energy_level=0.5,
                energy_trend="stable",
                layer_count=1,
            ))
        return ArrangementFormula(
            fingerprint="test",
            sections=sections,
        )

    def test_returns_baseline_plus_perturbations(self) -> None:
        gold = _make_gold()
        grid = _make_grid(bpm=128.0, num_beats=256)
        phrases = _make_phrases()
        pack = PerturbationPack(
            name="test",
            perturbations={
                "shift_1": lambda bg, ph: (shift_downbeat(bg, 1), ph),
                "halve": lambda bg, ph: (halve_tempo(bg), ph),
            },
        )
        results = run_sensitivity_suite(
            self._mock_engine, gold, grid, phrases, pack=pack
        )
        assert "baseline" in results
        assert "shift_1" in results
        assert "halve" in results
        assert len(results) == 3

    def test_all_results_are_scorecards(self) -> None:
        gold = _make_gold()
        grid = _make_grid(bpm=128.0, num_beats=256)
        phrases = _make_phrases()
        pack = PerturbationPack(
            name="test",
            perturbations={
                "drift": lambda bg, ph: (add_drift(bg, 500.0), ph),
            },
        )
        results = run_sensitivity_suite(
            self._mock_engine, gold, grid, phrases, pack=pack
        )
        for name, sc in results.items():
            assert isinstance(sc, StrataScorecard), f"{name} is not a StrataScorecard"

    def test_default_pack_has_entries(self) -> None:
        assert len(DEFAULT_GRID_PACK.perturbations) >= 5

    def test_handles_engine_failure_gracefully(self) -> None:
        def failing_engine(bg, ph):
            raise RuntimeError("Engine crash")

        gold = _make_gold()
        grid = _make_grid(num_beats=128)
        phrases = _make_phrases()
        pack = PerturbationPack(
            name="test",
            perturbations={"crash": lambda bg, ph: (bg, ph)},
        )
        # The baseline itself will fail, but it should still return a scorecard
        results = run_sensitivity_suite(
            failing_engine, gold, grid, phrases, pack=pack
        )
        assert "baseline" in results or "crash" in results
