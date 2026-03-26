"""Stem separation via demucs (htdemucs).

Wraps the demucs library to separate a track into drums, bass, vocals,
and other stems. Caches results at strata/{fingerprint}/stems/{stem}.wav.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .models import StemType

logger = logging.getLogger(__name__)

# Default model — htdemucs is the best general-purpose model
DEFAULT_MODEL = "htdemucs"

# Stem names produced by htdemucs, mapped to our StemType
DEMUCS_STEM_MAP: dict[str, StemType] = {
    "drums": StemType.DRUMS,
    "bass": StemType.BASS,
    "vocals": StemType.VOCALS,
    "other": StemType.OTHER,
}


def is_demucs_available() -> bool:
    """Check if demucs and torch are importable."""
    try:
        import demucs  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


class StemSeparator:
    """Separates audio into stems using demucs.

    Caches stem WAV files in a per-fingerprint directory so separation
    is only run once per track.
    """

    def __init__(
        self,
        strata_dir: Path,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        self._strata_dir = strata_dir
        self._model_name = model_name

    def stems_dir(self, fingerprint: str) -> Path:
        """Return the stems directory for a fingerprint."""
        return self._strata_dir / fingerprint / "stems"

    def stems_exist(self, fingerprint: str) -> bool:
        """Check if all 4 stems already exist on disk."""
        d = self.stems_dir(fingerprint)
        if not d.exists():
            return False
        return all((d / f"{stem.value}.wav").exists() for stem in StemType)

    def get_stem_paths(self, fingerprint: str) -> dict[StemType, Path]:
        """Return paths to cached stem files. Does NOT check existence."""
        d = self.stems_dir(fingerprint)
        return {stem: d / f"{stem.value}.wav" for stem in StemType}

    def separate(
        self,
        audio_path: Path,
        fingerprint: str,
    ) -> dict[StemType, Path]:
        """Separate an audio file into stems.

        If stems already exist on disk, returns cached paths immediately.
        Otherwise runs demucs and saves the results.

        Args:
            audio_path: Path to the input audio file.
            fingerprint: Track fingerprint for cache key.

        Returns:
            Dict mapping StemType to the path of the separated WAV file.

        Raises:
            RuntimeError: If demucs/torch are not installed.
            FileNotFoundError: If the audio file does not exist.
        """
        # Check cache first
        if self.stems_exist(fingerprint):
            logger.info("Stems already cached for %s", fingerprint[:16])
            return self.get_stem_paths(fingerprint)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not is_demucs_available():
            raise RuntimeError(
                "demucs and/or torch are not installed. "
                "Install with: pip install demucs torch"
            )

        logger.info("Running stem separation for %s (model=%s)", fingerprint[:16], self._model_name)

        import torch
        from demucs.apply import apply_model
        from demucs.audio import AudioFile
        from demucs.pretrained import get_model

        model = get_model(self._model_name)
        model.eval()

        # Load audio as tensor: (channels, samples) at model's samplerate
        wav = AudioFile(audio_path).read(
            streams=0, samplerate=model.samplerate, channels=model.audio_channels,
        )
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()

        # Run the model
        with torch.no_grad():
            sources = apply_model(model, wav[None], progress=False)[0]

        # Map source index to stem name via model.sources
        source_names = model.sources  # e.g. ["drums", "bass", "other", "vocals"]

        # Save each stem as a WAV file
        out_dir = self.stems_dir(fingerprint)
        out_dir.mkdir(parents=True, exist_ok=True)

        result: dict[StemType, Path] = {}
        for i, demucs_name in enumerate(source_names):
            stem_type = DEMUCS_STEM_MAP.get(demucs_name)
            if stem_type is None:
                logger.warning("Unknown demucs stem name: %s", demucs_name)
                continue

            # De-normalize
            stem_tensor = sources[i] * ref.std() + ref.mean()
            stem_path = out_dir / f"{stem_type.value}.wav"

            _save_stem_wav(stem_tensor, stem_path, model.samplerate)
            result[stem_type] = stem_path
            logger.info("  Saved stem: %s (%s)", stem_type.value, stem_path.name)

        return result


def _save_stem_wav(tensor, path: Path, sample_rate: int) -> None:
    """Save a demucs stem tensor to a WAV file.

    Args:
        tensor: Torch tensor of shape (channels, samples).
        path: Output WAV file path.
        sample_rate: Sample rate of the audio.
    """
    import soundfile as sf

    # Convert torch tensor to numpy: (channels, samples) -> (samples, channels)
    audio = tensor.cpu().numpy().T
    sf.write(str(path), audio, sample_rate)
