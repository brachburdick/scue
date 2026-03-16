"""Tests for Layer 1 data models and serialization."""

from scue.layer1.models import (
    RGBWaveform,
    Section,
    TrackAnalysis,
    TrackFeatures,
    MusicalEvent,
    analysis_from_dict,
    analysis_to_dict,
    section_from_dict,
    section_to_dict,
)


class TestSection:
    """Tests for the Section dataclass."""

    def test_create_section(self) -> None:
        section = Section(label="drop", start=32.0, end=64.0)
        assert section.label == "drop"
        assert section.start == 32.0
        assert section.end == 64.0
        assert section.confidence == 0.5
        assert section.bar_count == 0
        assert section.fakeout is False
        assert section.source == "analysis"

    def test_section_duration(self) -> None:
        section = Section(label="intro", start=0.0, end=16.0)
        assert section.duration == 16.0

    def test_section_roundtrip(self) -> None:
        section = Section(
            label="build",
            start=16.0,
            end=32.0,
            confidence=0.85,
            bar_count=8,
            expected_bar_count=8,
            irregular_phrase=False,
            fakeout=False,
            original_label="verse",
            source="analysis",
        )
        data = section_to_dict(section)
        restored = section_from_dict(data)
        assert restored.label == section.label
        assert restored.start == section.start
        assert restored.end == section.end
        assert restored.confidence == section.confidence
        assert restored.bar_count == section.bar_count
        assert restored.original_label == section.original_label

    def test_section_from_dict_defaults(self) -> None:
        """Minimal dict should fill defaults."""
        data = {"label": "drop", "start": 10.0, "end": 20.0}
        section = section_from_dict(data)
        assert section.confidence == 0.5
        assert section.bar_count == 0
        assert section.irregular_phrase is False


class TestTrackAnalysis:
    """Tests for TrackAnalysis serialization."""

    def _make_analysis(self) -> TrackAnalysis:
        return TrackAnalysis(
            fingerprint="abc123" * 10,
            audio_path="/test/track.mp3",
            title="Test Track",
            bpm=128.0,
            beats=[0.0, 0.469, 0.938],
            downbeats=[0.0, 1.875],
            sections=[
                Section(label="intro", start=0.0, end=16.0, bar_count=8,
                        expected_bar_count=8, original_label="intro"),
                Section(label="drop", start=16.0, end=48.0, bar_count=16,
                        expected_bar_count=16, original_label="chorus"),
            ],
            features=TrackFeatures(
                energy_curve=[0.1, 0.5, 0.9],
                mood="euphoric",
                key="Am",
            ),
            duration=180.0,
        )

    def test_roundtrip(self) -> None:
        analysis = self._make_analysis()
        data = analysis_to_dict(analysis)
        restored = analysis_from_dict(data)

        assert restored.fingerprint == analysis.fingerprint
        assert restored.bpm == analysis.bpm
        assert len(restored.sections) == 2
        assert restored.sections[0].label == "intro"
        assert restored.sections[1].label == "drop"
        assert restored.features.mood == "euphoric"
        assert restored.features.key == "Am"
        assert restored.duration == 180.0

    def test_enrichment_fields_nullable(self) -> None:
        """Enrichment fields should be None by default."""
        analysis = self._make_analysis()
        assert analysis.pioneer_bpm is None
        assert analysis.pioneer_key is None
        assert analysis.pioneer_beatgrid is None
        assert analysis.rekordbox_id is None
        assert analysis.enrichment_timestamp is None

    def test_enrichment_fields_roundtrip(self) -> None:
        analysis = self._make_analysis()
        analysis.pioneer_bpm = 128.5
        analysis.pioneer_key = "Am"
        analysis.rekordbox_id = 42

        data = analysis_to_dict(analysis)
        restored = analysis_from_dict(data)
        assert restored.pioneer_bpm == 128.5
        assert restored.pioneer_key == "Am"
        assert restored.rekordbox_id == 42

    def test_waveform_roundtrip(self) -> None:
        analysis = self._make_analysis()
        analysis.waveform = RGBWaveform(
            sample_rate=60,
            duration=180.0,
            low=[0.1, 0.5],
            mid=[0.3, 0.7],
            high=[0.2, 0.8],
        )
        data = analysis_to_dict(analysis)
        restored = analysis_from_dict(data)
        assert restored.waveform is not None
        assert restored.waveform.sample_rate == 60
        assert restored.waveform.low == [0.1, 0.5]

    def test_empty_events(self) -> None:
        """Events list should be empty for Tier 1."""
        analysis = self._make_analysis()
        assert analysis.events == []
        data = analysis_to_dict(analysis)
        restored = analysis_from_dict(data)
        assert restored.events == []


class TestMusicalEvent:
    """Tests for MusicalEvent (Tier 2 stub)."""

    def test_create_event(self) -> None:
        event = MusicalEvent(type="kick", timestamp=1.0, intensity=0.9)
        assert event.type == "kick"
        assert event.duration is None
        assert event.payload == {}
