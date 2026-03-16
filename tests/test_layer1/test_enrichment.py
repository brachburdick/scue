"""Tests for Layer 1B enrichment pass."""

from pathlib import Path

from scue.layer1.divergence import query_divergences
from scue.layer1.enrichment import run_enrichment_pass, _snap_time_to_grid, _compute_downbeats
from scue.layer1.models import Section, TrackAnalysis, TrackFeatures, MusicalEvent
from scue.layer1.storage import TrackCache, TrackStore


def _make_analysis(**overrides) -> TrackAnalysis:
    defaults = dict(
        fingerprint="abc123def456",
        audio_path="/test/track.mp3",
        bpm=128.0,
        beats=[i * 0.46875 for i in range(64)],
        downbeats=[i * 0.46875 * 4 for i in range(16)],
        sections=[
            Section(label="intro", start=0.0, end=15.0, bar_count=8, expected_bar_count=8, confidence=0.9),
            Section(label="drop", start=15.0, end=30.0, bar_count=8, expected_bar_count=8, confidence=0.95),
        ],
        features=TrackFeatures(
            energy_curve=[0.3, 0.5, 0.7, 0.9],
            mood="euphoric",
            danceability=0.8,
            key="Cm",
        ),
        duration=30.0,
    )
    defaults.update(overrides)
    return TrackAnalysis(**defaults)


def _make_storage(tmp_path: Path) -> tuple[TrackStore, TrackCache]:
    store = TrackStore(tmp_path / "tracks")
    cache = TrackCache(tmp_path / "cache.db")
    return store, cache


class TestSnapTimeToGrid:
    def test_exact_match(self) -> None:
        grid = [0.0, 0.5, 1.0, 1.5]
        assert _snap_time_to_grid(0.5, grid) == 0.5

    def test_snap_to_nearest(self) -> None:
        grid = [0.0, 0.5, 1.0, 1.5]
        assert _snap_time_to_grid(0.6, grid) == 0.5

    def test_snap_forward(self) -> None:
        grid = [0.0, 0.5, 1.0, 1.5]
        assert _snap_time_to_grid(0.8, grid) == 1.0

    def test_empty_grid(self) -> None:
        assert _snap_time_to_grid(5.0, []) == 5.0


class TestComputeDownbeats:
    def test_every_4th_beat(self) -> None:
        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        result = _compute_downbeats(beats)
        assert result == [0.0, 2.0]

    def test_empty(self) -> None:
        assert _compute_downbeats([]) == []


class TestEnrichmentPass:
    def test_bpm_enrichment(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, store=store, cache=cache)

        assert enriched.bpm == 130.0
        assert enriched.version == 2
        assert enriched.source == "pioneer_enriched"
        assert enriched.pioneer_bpm == 130.0
        # Original unchanged
        assert analysis.bpm == 128.0
        assert analysis.version == 1

    def test_no_bpm_change_when_similar(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        enriched = run_enrichment_pass(analysis, pioneer_bpm=128.02, store=store, cache=cache)

        # BPM not changed because diff < 0.05
        assert enriched.bpm == 128.0

    def test_beatgrid_enrichment(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()
        pioneer_grid = [i * 0.5 for i in range(60)]

        enriched = run_enrichment_pass(
            analysis, pioneer_bpm=128.0, store=store, cache=cache,
            pioneer_beatgrid=pioneer_grid,
        )

        assert enriched.beats == pioneer_grid
        assert enriched.pioneer_beatgrid == pioneer_grid
        assert len(enriched.downbeats) == 15  # 60 / 4

    def test_key_enrichment(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        enriched = run_enrichment_pass(
            analysis, pioneer_bpm=128.0, store=store, cache=cache,
            pioneer_key="Dm",
        )

        assert enriched.features.key == "Dm"
        assert enriched.features.key_source == "pioneer_enriched"
        assert enriched.pioneer_key == "Dm"

    def test_no_key_change_when_same(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        enriched = run_enrichment_pass(
            analysis, pioneer_bpm=128.0, store=store, cache=cache,
            pioneer_key="Cm",
        )

        # Same key — no change logged
        divergences = query_divergences(cache, divergence_field="key")
        assert len(divergences) == 0

    def test_section_timestamps_scaled(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        enriched = run_enrichment_pass(analysis, pioneer_bpm=256.0, store=store, cache=cache)

        # BPM ratio = 256/128 = 2.0, so times halved
        assert enriched.sections[0].start == 0.0
        assert abs(enriched.sections[0].end - 7.5) < 0.01
        assert enriched.sections[0].source == "pioneer_enriched"

    def test_event_timestamps_scaled(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        events = [MusicalEvent(type="kick", timestamp=10.0, duration=0.1)]
        analysis = _make_analysis(events=events)

        enriched = run_enrichment_pass(analysis, pioneer_bpm=256.0, store=store, cache=cache)

        assert abs(enriched.events[0].timestamp - 5.0) < 0.01
        assert abs(enriched.events[0].duration - 0.05) < 0.001

    def test_divergence_logged(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        run_enrichment_pass(analysis, pioneer_bpm=130.0, store=store, cache=cache, pioneer_key="Dm")

        divergences = query_divergences(cache)
        fields = {d.divergence_field for d in divergences}
        assert "bpm" in fields
        assert "key" in fields

    def test_persists_to_store(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()
        store.save(analysis)

        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, store=store, cache=cache)

        # Should be saved as v2
        loaded = store.load(analysis.fingerprint, version=2)
        assert loaded is not None
        assert loaded.bpm == 130.0
        assert loaded.source == "pioneer_enriched"

    def test_enrichment_timestamp_set(self, tmp_path: Path) -> None:
        store, cache = _make_storage(tmp_path)
        analysis = _make_analysis()

        enriched = run_enrichment_pass(analysis, pioneer_bpm=130.0, store=store, cache=cache)

        assert enriched.enrichment_timestamp is not None
        assert enriched.enrichment_timestamp > 0
