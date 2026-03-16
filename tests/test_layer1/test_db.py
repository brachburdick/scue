"""Tests for scue.layer1.db — SQLite storage."""

import tempfile
from pathlib import Path

import pytest

from scue.layer1.db import (
    _get_conn,
    store_analysis,
    load_analysis,
    list_tracks,
    map_rekordbox_id,
    lookup_fingerprint,
    store_divergence,
    query_divergences_db,
    _analysis_to_json,
    _analysis_from_json,
)
from scue.layer1.models import TrackAnalysis, Section, MusicalEvent, TrackFeatures


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary database path."""
    return tmp_path / "test.db"


def _make_analysis(fp: str = "abc123", version: int = 1, bpm: float = 128.0) -> TrackAnalysis:
    return TrackAnalysis(
        fingerprint=fp,
        audio_path="/fake/track.wav",
        bpm=bpm,
        beats=[0.0, 0.47, 0.94],
        downbeats=[0.0, 1.88],
        sections=[
            Section(label="intro", start=0.0, end=16.0, confidence=0.8),
            Section(label="drop", start=16.0, end=48.0, confidence=0.9),
        ],
        events=[
            MusicalEvent(type="kick", timestamp=0.0),
        ],
        features=TrackFeatures(energy_curve=[0.3, 0.5, 0.8, 0.6]),
        version=version,
    )


class TestSerialization:
    def test_roundtrip(self):
        analysis = _make_analysis()
        raw = _analysis_to_json(analysis)
        restored = _analysis_from_json(raw)
        assert restored.fingerprint == analysis.fingerprint
        assert restored.bpm == analysis.bpm
        assert len(restored.sections) == 2
        assert restored.sections[0].label == "intro"
        assert len(restored.events) == 1
        assert restored.features.energy_curve == [0.3, 0.5, 0.8, 0.6]


class TestStoreAndLoad:
    def test_store_and_load(self, tmp_db):
        analysis = _make_analysis()
        store_analysis(analysis, db_path=tmp_db)
        loaded = load_analysis("abc123", db_path=tmp_db)
        assert loaded is not None
        assert loaded.fingerprint == "abc123"
        assert loaded.bpm == 128.0
        assert len(loaded.sections) == 2

    def test_load_nonexistent(self, tmp_db):
        assert load_analysis("nonexistent", db_path=tmp_db) is None

    def test_load_specific_version(self, tmp_db):
        v1 = _make_analysis(version=1, bpm=128.0)
        v2 = _make_analysis(version=2, bpm=130.0)
        store_analysis(v1, db_path=tmp_db)
        store_analysis(v2, db_path=tmp_db)

        loaded_v1 = load_analysis("abc123", version=1, db_path=tmp_db)
        assert loaded_v1.bpm == 128.0

        loaded_v2 = load_analysis("abc123", version=2, db_path=tmp_db)
        assert loaded_v2.bpm == 130.0

    def test_load_latest_version(self, tmp_db):
        store_analysis(_make_analysis(version=1, bpm=128.0), db_path=tmp_db)
        store_analysis(_make_analysis(version=2, bpm=130.0), db_path=tmp_db)
        loaded = load_analysis("abc123", db_path=tmp_db)
        assert loaded.version == 2
        assert loaded.bpm == 130.0

    def test_upsert(self, tmp_db):
        store_analysis(_make_analysis(version=1, bpm=128.0), db_path=tmp_db)
        store_analysis(_make_analysis(version=1, bpm=140.0), db_path=tmp_db)
        loaded = load_analysis("abc123", version=1, db_path=tmp_db)
        assert loaded.bpm == 140.0


class TestListTracks:
    def test_list_empty(self, tmp_db):
        assert list_tracks(db_path=tmp_db) == []

    def test_list_returns_latest_per_fingerprint(self, tmp_db):
        store_analysis(_make_analysis(fp="aaa", version=1), db_path=tmp_db)
        store_analysis(_make_analysis(fp="aaa", version=2), db_path=tmp_db)
        store_analysis(_make_analysis(fp="bbb", version=1), db_path=tmp_db)
        tracks = list_tracks(db_path=tmp_db)
        assert len(tracks) == 2
        fps = {t["fingerprint"] for t in tracks}
        assert fps == {"aaa", "bbb"}


class TestRekordboxMapping:
    def test_map_and_lookup(self, tmp_db):
        map_rekordbox_id(42, "fp_abc", db_path=tmp_db)
        assert lookup_fingerprint(42, db_path=tmp_db) == "fp_abc"

    def test_lookup_missing(self, tmp_db):
        assert lookup_fingerprint(999, db_path=tmp_db) is None

    def test_overwrite_mapping(self, tmp_db):
        map_rekordbox_id(42, "fp_old", db_path=tmp_db)
        map_rekordbox_id(42, "fp_new", db_path=tmp_db)
        assert lookup_fingerprint(42, db_path=tmp_db) == "fp_new"


class TestDivergenceLog:
    def test_store_and_query(self, tmp_db):
        store_divergence("fp1", "bpm", "128.0", "130.0", "pioneer_adopted", 1000.0, db_path=tmp_db)
        rows = query_divergences_db(track_fingerprint="fp1", db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["field"] == "bpm"

    def test_filter_by_field(self, tmp_db):
        store_divergence("fp1", "bpm", "128", "130", "pioneer_adopted", 1000.0, db_path=tmp_db)
        store_divergence("fp1", "key", "Am", "Cm", "pioneer_adopted", 1001.0, db_path=tmp_db)
        rows = query_divergences_db(field="key", db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["field"] == "key"
