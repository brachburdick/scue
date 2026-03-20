"""Random Forest percussion detector — trained model for slot classification.

Uses the same beat-synchronous 16th-note slot classification as the heuristic
detector, but replaces threshold rules with a trained Random Forest classifier.
Falls back to heuristic if the model file is not present.

Training workflow:
1. Run heuristic detector on a set of tracks to generate seed labels
2. Manually review/correct labels in ground truth JSON files
3. Call train_from_labels() to train the RF model
4. Model saved to models/drum_classifier.joblib
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..models import Section
from .events import DetectorConfig, DetectorResult, DrumPattern
from .features import AudioFeatures

logger = logging.getLogger(__name__)

SLOTS_PER_BAR = 16

# Sub-band frequency ranges (Hz) — same as heuristic
KICK_BAND = (20, 150)
SNARE_BAND = (150, 1000)
HIHAT_BAND = (4000, 16000)
CLAP_BAND = (1000, 4000)


class PercussionRFDetector:
    """Random Forest beat-synchronous percussion detector.

    Implements DetectorProtocol. Extracts a feature vector per 16th-note slot
    and classifies using a trained scikit-learn Random Forest. Falls back to
    the heuristic detector if the model file is not found.
    """

    name: str = "random_forest"
    event_types: list[str] = ["kick", "snare", "clap", "hihat"]

    def __init__(self) -> None:
        self._model = None
        self._model_loaded = False

    def _load_model(self, model_path: str | Path) -> bool:
        """Attempt to load a trained RF model from disk."""
        model_path = Path(model_path)
        if not model_path.exists():
            logger.warning("RF model not found at %s — will fall back to heuristic", model_path)
            return False

        try:
            import joblib
            self._model = joblib.load(model_path)
            self._model_loaded = True
            logger.info("Loaded RF percussion model from %s", model_path)
            return True
        except Exception:
            logger.exception("Failed to load RF model from %s", model_path)
            return False

    def detect(
        self,
        features: AudioFeatures,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult:
        """Run RF percussion detection, falling back to heuristic if needed."""
        params = config.params.get("random_forest", {})
        model_path = params.get("model_path", "models/drum_classifier.joblib")

        # Try to load model if not already loaded
        if not self._model_loaded:
            if not self._load_model(model_path):
                # Fall back to heuristic
                logger.info("Falling back to heuristic percussion detector")
                from .percussion_heuristic import PercussionHeuristicDetector
                fallback = PercussionHeuristicDetector()
                result = fallback.detect(features, beats, downbeats, sections, config)
                result.metadata["strategy"] = "random_forest_fallback_heuristic"
                return result

        if not beats or not downbeats:
            return DetectorResult(metadata={"skipped": "no_beatgrid"})

        # Extract feature vectors per slot
        slot_features = _extract_slot_features(features, beats, downbeats)

        if not slot_features:
            return DetectorResult(metadata={"skipped": "no_slots"})

        # Stack into feature matrix
        X = np.array(slot_features)

        # Predict: classes are "kick", "snare", "clap", "none"
        predictions = self._model.predict(X)
        probabilities = self._model.predict_proba(X) if hasattr(self._model, 'predict_proba') else None

        # Build patterns from predictions
        avg_beat_dur = (beats[-1] - beats[0]) / (len(beats) - 1) if len(beats) >= 2 else 0.5
        sixteenth_dur = avg_beat_dur / 4.0

        patterns: list[DrumPattern] = []
        current_start = 0
        kick_slots: list[int] = []
        snare_slots: list[int] = []
        clap_slots: list[int] = []
        hihat_count = 0
        slot_count = 0

        for i, pred in enumerate(predictions):
            bar_idx = i // SLOTS_PER_BAR
            slot_in_bar = i % SLOTS_PER_BAR

            kick_slots.append(1 if pred == "kick" else 0)
            snare_slots.append(1 if pred == "snare" else 0)
            clap_slots.append(1 if pred == "clap" else 0)
            if pred == "hihat":
                hihat_count += 1
            slot_count += 1

            # Close pattern every 4 bars or at end
            bars_done = bar_idx - current_start + 1
            is_last = i == len(predictions) - 1
            if (slot_in_bar == SLOTS_PER_BAR - 1 and bars_done >= 4) or is_last:
                density = hihat_count / max(slot_count, 1)
                hihat_type = _classify_hihat_type(density)

                patterns.append(DrumPattern(
                    bar_start=current_start,
                    bar_end=bar_idx + 1,
                    kick=kick_slots,
                    snare=snare_slots,
                    clap=clap_slots,
                    hihat_type=hihat_type,
                    hihat_density=round(density, 3),
                    hihat_open_ratio=0.0,  # RF doesn't distinguish open/closed yet
                    confidence=0.7,  # base confidence for RF
                ))

                current_start = bar_idx + 1
                kick_slots = []
                snare_slots = []
                clap_slots = []
                hihat_count = 0
                slot_count = 0

        total_kicks = sum(sum(p.kick) for p in patterns)
        total_snares = sum(sum(p.snare) for p in patterns)

        return DetectorResult(
            patterns=patterns,
            metadata={
                "strategy": "random_forest",
                "model_path": str(model_path),
                "total_patterns": len(patterns),
                "total_kicks": total_kicks,
                "total_snares": total_snares,
                "total_slots_classified": len(predictions),
            },
        )


def _extract_slot_features(
    features: AudioFeatures,
    beats: list[float],
    downbeats: list[float],
) -> list[list[float]]:
    """Extract per-slot feature vectors for RF classification.

    Each slot gets a 7-dimensional feature vector:
    [kick_energy, snare_energy, clap_energy, hihat_energy,
     onset_strength, spectral_centroid, beat_position]
    """
    signal = features.y_percussive if features.y_percussive is not None else features.signal
    sr = features.sr
    hop = features.hop_length

    # Compute STFT for sub-band energies
    n_fft = 2048
    S = np.abs(np.fft.rfft(
        np.lib.stride_tricks.sliding_window_view(signal, n_fft)[::hop],
        axis=1,
    ))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

    kick_mask = (freqs >= KICK_BAND[0]) & (freqs < KICK_BAND[1])
    snare_mask = (freqs >= SNARE_BAND[0]) & (freqs < SNARE_BAND[1])
    clap_mask = (freqs >= CLAP_BAND[0]) & (freqs < CLAP_BAND[1])
    hihat_mask = (freqs >= HIHAT_BAND[0]) & (freqs < HIHAT_BAND[1])

    kick_e = S[:, kick_mask].mean(axis=1) if kick_mask.any() else np.zeros(S.shape[0])
    snare_e = S[:, snare_mask].mean(axis=1) if snare_mask.any() else np.zeros(S.shape[0])
    clap_e = S[:, clap_mask].mean(axis=1) if clap_mask.any() else np.zeros(S.shape[0])
    hihat_e = S[:, hihat_mask].mean(axis=1) if hihat_mask.any() else np.zeros(S.shape[0])

    # Normalize
    for arr in [kick_e, snare_e, clap_e, hihat_e]:
        mx = arr.max()
        if mx > 0:
            arr /= mx

    avg_beat_dur = (beats[-1] - beats[0]) / (len(beats) - 1) if len(beats) >= 2 else 0.5
    sixteenth_dur = avg_beat_dur / 4.0

    slot_vectors: list[list[float]] = []

    for bar_idx, bar_time in enumerate(downbeats):
        for slot in range(SLOTS_PER_BAR):
            slot_time = bar_time + slot * sixteenth_dur
            frame = int(slot_time * sr / hop)
            frame = max(0, min(frame, len(kick_e) - 1))

            onset_frame = min(frame, len(features.onset_strength) - 1)
            centroid_frame = min(frame, len(features.spectral_centroid) - 1)

            slot_vectors.append([
                float(kick_e[frame]),
                float(snare_e[frame]),
                float(clap_e[frame]),
                float(hihat_e[frame]),
                float(features.onset_strength[onset_frame]),
                float(features.spectral_centroid[centroid_frame]),
                float(slot / SLOTS_PER_BAR),  # normalized beat position
            ])

    return slot_vectors


def _classify_hihat_type(density: float) -> str:
    """Classify hi-hat pattern type from hit density."""
    if density < 0.05:
        return "none"
    elif density < 0.2:
        return "offbeat"
    elif density < 0.4:
        return "8ths"
    elif density < 0.7:
        return "16ths"
    else:
        return "roll"


def train_from_labels(
    label_files: list[str | Path],
    output_path: str | Path = "models/drum_classifier.joblib",
    n_estimators: int = 150,
) -> dict:
    """Train a Random Forest model from labeled ground truth files.

    Args:
        label_files: Paths to ground truth JSON files with labeled slots.
            Expected format: list of {features: [7 floats], label: str}
        output_path: Where to save the trained model.
        n_estimators: Number of trees in the forest.

    Returns:
        Training stats dict with accuracy, class distribution, etc.
    """
    import json

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    import joblib

    X_all = []
    y_all = []

    for path in label_files:
        with open(path) as f:
            data = json.load(f)

        for entry in data:
            X_all.append(entry["features"])
            y_all.append(entry["label"])

    X = np.array(X_all)
    y = np.array(y_all)

    logger.info("Training RF with %d samples, %d features", len(X), X.shape[1])

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=10,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1,
    )

    # Cross-validation
    scores = cross_val_score(clf, X, y, cv=5, scoring="f1_weighted")
    logger.info("CV F1 scores: %s (mean=%.3f)", scores.round(3), scores.mean())

    # Train on full dataset
    clf.fit(X, y)

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, output_path)
    logger.info("Model saved to %s", output_path)

    # Class distribution
    unique, counts = np.unique(y, return_counts=True)
    class_dist = dict(zip(unique.tolist(), counts.tolist()))

    return {
        "n_samples": len(X),
        "n_features": X.shape[1],
        "n_estimators": n_estimators,
        "cv_f1_mean": float(scores.mean()),
        "cv_f1_std": float(scores.std()),
        "class_distribution": class_dist,
        "model_path": str(output_path),
    }
