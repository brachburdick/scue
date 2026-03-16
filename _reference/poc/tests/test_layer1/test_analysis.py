"""Tests for the Layer 1A analysis pipeline.

These are integration tests that require audio test fixtures.
Place test audio files in tests/fixtures/audio/.

Tests marked @pytest.mark.slow require real audio files and take minutes to run.
Run fast tests only: pytest tests/test_layer1/ -m "not slow"
"""

import pytest


@pytest.mark.slow
def test_analysis_returns_required_keys(tmp_path):
    """Smoke test: run_analysis on a real audio file returns the expected keys."""
    from scue.layer1.analysis import run_analysis
    import pathlib

    fixtures = pathlib.Path("tests/fixtures/audio")
    audio_files = list(fixtures.glob("*.mp3")) + list(fixtures.glob("*.wav"))
    if not audio_files:
        pytest.skip("No test audio fixtures found in tests/fixtures/audio/")

    result = run_analysis(str(audio_files[0]))
    assert "bpm" in result
    assert "sections" in result
    assert "beats" in result
    assert "downbeats" in result
    assert "waveform" in result
    assert isinstance(result["sections"], list)
    assert len(result["sections"]) > 0


@pytest.mark.slow
def test_analysis_sections_have_required_fields(tmp_path):
    """Each section in the result must have label, start, end, confidence."""
    from scue.layer1.analysis import run_analysis
    import pathlib

    fixtures = pathlib.Path("tests/fixtures/audio")
    audio_files = list(fixtures.glob("*.mp3")) + list(fixtures.glob("*.wav"))
    if not audio_files:
        pytest.skip("No test audio fixtures found in tests/fixtures/audio/")

    result = run_analysis(str(audio_files[0]))
    for section in result["sections"]:
        assert "label" in section
        assert "start" in section
        assert "end" in section
        assert "confidence" in section
        assert section["end"] > section["start"]
        assert 0.0 <= section["confidence"] <= 1.0
