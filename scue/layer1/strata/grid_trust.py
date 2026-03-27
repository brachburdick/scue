"""Beat-grid trust scoring for the Strata engine.

Evaluates the reliability of a Pioneer beat grid before it is used as a
constraint for arrangement analysis. Returns a trust tier (A/B/C) that
governs how the grid may be used:

  - Tier A: Cross-validated and musically plausible. Hard constraints allowed.
  - Tier B: Present but not fully validated. Soft priors only.
  - Tier C: Estimated fallback or conflicting sources. Alignment aid only.

This module is called by LiveStrataAnalyzer to annotate formulas with
grid trust information. It does NOT gate behavior yet — the trust report
is informational, attached to the ArrangementFormula for evaluation and
future use by constrained methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GridTrustTier(str, Enum):
    """How much the beat grid can be relied upon."""

    A = "A"  # Cross-validated, hard constraints OK
    B = "B"  # Present but unvalidated, soft priors only
    C = "C"  # Estimated/conflicting, alignment aid only


@dataclass
class GridTrustReport:
    """Result of beat-grid trust scoring."""

    tier: GridTrustTier
    source_id: str = ""  # Which source provided the grid
    sources_available: list[str] = field(default_factory=list)
    source_agreement: bool = True

    # Individual check results
    downbeat_plausible: bool = True
    drift_detected: bool = False
    half_double_tempo_suspicion: bool = False
    phrase_bar_plausible: bool = True

    confidence: float = 1.0  # 0.0-1.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "tier": self.tier.value,
            "source_id": self.source_id,
            "sources_available": self.sources_available,
            "source_agreement": self.source_agreement,
            "downbeat_plausible": self.downbeat_plausible,
            "drift_detected": self.drift_detected,
            "half_double_tempo_suspicion": self.half_double_tempo_suspicion,
            "phrase_bar_plausible": self.phrase_bar_plausible,
            "confidence": self.confidence,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> GridTrustReport:
        """Deserialize from a dict."""
        return GridTrustReport(
            tier=GridTrustTier(d.get("tier", "C")),
            source_id=d.get("source_id", ""),
            sources_available=d.get("sources_available", []),
            source_agreement=d.get("source_agreement", True),
            downbeat_plausible=d.get("downbeat_plausible", True),
            drift_detected=d.get("drift_detected", False),
            half_double_tempo_suspicion=d.get("half_double_tempo_suspicion", False),
            phrase_bar_plausible=d.get("phrase_bar_plausible", True),
            confidence=d.get("confidence", 1.0),
            notes=d.get("notes", []),
        )


# ---------------------------------------------------------------------------
# Typical EDM BPM range for half/double detection
# ---------------------------------------------------------------------------
_EDM_BPM_LOW = 100.0
_EDM_BPM_HIGH = 180.0

# Maximum cumulative drift (ms) before flagging
_MAX_DRIFT_MS = 500.0  # ~1 beat at 120 BPM

# Maximum acceptable beat spacing deviation from expected (fraction)
_SPACING_TOLERANCE = 0.15  # 15% deviation


def score_beat_grid(
    beat_grid: list[dict],
    phrases: list[dict] | None = None,
    bpm: float = 0.0,
    duration: float = 0.0,
    source_id: str = "pioneer_network",
) -> GridTrustReport:
    """Score beat-grid reliability and return a trust report.

    Args:
        beat_grid: List of grid entries, each with keys:
            beat_number (int), time_ms (float), bpm (float).
        phrases: Optional phrase analysis entries, each with keys:
            start_beat (int), end_beat (int), kind (str).
        bpm: Declared track BPM (0 = unknown, will extract from grid).
        duration: Track duration in seconds (0 = unknown).
        source_id: Identifier for the grid source.

    Returns:
        GridTrustReport with tier A/B/C and detailed check results.
    """
    notes: list[str] = []
    failures = 0

    # Handle empty or missing grid
    if not beat_grid:
        return GridTrustReport(
            tier=GridTrustTier.C,
            source_id=source_id,
            downbeat_plausible=False,
            confidence=0.0,
            notes=["No beat grid data available"],
        )

    # Extract effective BPM from grid if not provided
    effective_bpm = bpm
    if effective_bpm <= 0:
        effective_bpm = beat_grid[0].get("bpm", 120.0)
    if effective_bpm <= 0:
        effective_bpm = 120.0

    # --- Check 1: Downbeat plausibility ---
    downbeat_ok = _check_downbeat_plausibility(beat_grid, effective_bpm, notes)
    if not downbeat_ok:
        failures += 1

    # --- Check 2: Drift detection ---
    drift_detected = _check_drift(beat_grid, effective_bpm, notes)
    if drift_detected:
        failures += 1

    # --- Check 3: Half/double tempo suspicion ---
    half_double = _check_half_double_tempo(effective_bpm, notes)
    if half_double:
        failures += 1

    # --- Check 4: Phrase/bar plausibility ---
    phrase_ok = _check_phrase_bar_plausibility(phrases, notes)
    if not phrase_ok:
        failures += 1

    # --- Tier assignment ---
    if failures == 0:
        tier = GridTrustTier.A
        confidence = 1.0
    elif failures <= 2:
        tier = GridTrustTier.B
        confidence = max(0.3, 1.0 - failures * 0.25)
    else:
        tier = GridTrustTier.C
        confidence = max(0.1, 1.0 - failures * 0.25)

    return GridTrustReport(
        tier=tier,
        source_id=source_id,
        sources_available=[source_id],
        source_agreement=True,  # Only one source for now
        downbeat_plausible=downbeat_ok,
        drift_detected=drift_detected,
        half_double_tempo_suspicion=half_double,
        phrase_bar_plausible=phrase_ok,
        confidence=round(confidence, 2),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Individual validation checks
# ---------------------------------------------------------------------------


def _check_downbeat_plausibility(
    beat_grid: list[dict],
    bpm: float,
    notes: list[str],
) -> bool:
    """Check that beat spacing is consistent with declared BPM.

    Verifies that the average beat spacing matches the expected spacing
    (60000/BPM ms) within tolerance.
    """
    if len(beat_grid) < 2:
        notes.append("Only 1 grid entry — cannot verify beat spacing")
        return False

    expected_spacing_ms = 60000.0 / bpm

    # Check spacing consistency across the grid
    spacings = []
    for i in range(1, min(len(beat_grid), 50)):  # Sample up to 50 entries
        dt = beat_grid[i]["time_ms"] - beat_grid[i - 1]["time_ms"]
        db = beat_grid[i]["beat_number"] - beat_grid[i - 1]["beat_number"]
        if db > 0:
            spacings.append(dt / db)

    if not spacings:
        notes.append("Cannot compute beat spacing from grid")
        return False

    avg_spacing = sum(spacings) / len(spacings)
    deviation = abs(avg_spacing - expected_spacing_ms) / expected_spacing_ms

    if deviation > _SPACING_TOLERANCE:
        notes.append(
            f"Beat spacing deviation {deviation:.1%} exceeds {_SPACING_TOLERANCE:.0%} "
            f"tolerance (avg={avg_spacing:.1f}ms, expected={expected_spacing_ms:.1f}ms)"
        )
        return False

    return True


def _check_drift(
    beat_grid: list[dict],
    bpm: float,
    notes: list[str],
) -> bool:
    """Check for cumulative timing drift across the track.

    Compares actual beat times against expected times (linear from first beat).
    Returns True if drift is detected (bad).
    """
    if len(beat_grid) < 4:
        return False  # Not enough data to detect drift

    expected_spacing_ms = 60000.0 / bpm
    first_time = beat_grid[0]["time_ms"]
    first_beat = beat_grid[0]["beat_number"]

    max_drift = 0.0
    for entry in beat_grid:
        expected_time = first_time + (entry["beat_number"] - first_beat) * expected_spacing_ms
        actual_time = entry["time_ms"]
        drift = abs(actual_time - expected_time)
        max_drift = max(max_drift, drift)

    if max_drift > _MAX_DRIFT_MS:
        notes.append(
            f"Cumulative drift of {max_drift:.0f}ms detected "
            f"(threshold={_MAX_DRIFT_MS:.0f}ms)"
        )
        return True

    return False


def _check_half_double_tempo(
    bpm: float,
    notes: list[str],
) -> bool:
    """Check if BPM is suspiciously half or double the typical EDM range.

    Returns True if suspicious (bad).
    """
    if bpm <= 0:
        notes.append("BPM is zero or negative")
        return True

    # Check if BPM is in normal EDM range
    if _EDM_BPM_LOW <= bpm <= _EDM_BPM_HIGH:
        return False

    # Check if half-tempo (e.g., 64 BPM when track is really 128)
    if bpm * 2 >= _EDM_BPM_LOW and bpm * 2 <= _EDM_BPM_HIGH:
        notes.append(
            f"BPM {bpm:.1f} is half of typical EDM range "
            f"({_EDM_BPM_LOW}-{_EDM_BPM_HIGH}); "
            f"doubled={bpm * 2:.1f} would be in range"
        )
        return True

    # Check if double-tempo (e.g., 256 BPM when track is really 128)
    if bpm / 2 >= _EDM_BPM_LOW and bpm / 2 <= _EDM_BPM_HIGH:
        notes.append(
            f"BPM {bpm:.1f} is double of typical EDM range "
            f"({_EDM_BPM_LOW}-{_EDM_BPM_HIGH}); "
            f"halved={bpm / 2:.1f} would be in range"
        )
        return True

    # Outside range but not a clean half/double — still suspicious
    if bpm < _EDM_BPM_LOW or bpm > _EDM_BPM_HIGH:
        notes.append(
            f"BPM {bpm:.1f} is outside typical EDM range "
            f"({_EDM_BPM_LOW}-{_EDM_BPM_HIGH})"
        )
        return True

    return False


def _check_phrase_bar_plausibility(
    phrases: list[dict] | None,
    notes: list[str],
) -> bool:
    """Check that phrase lengths are multiples of 4 bars (16 beats).

    Returns True if plausible (good), False if phrases have unusual lengths.
    """
    if not phrases:
        notes.append("No phrase data available for bar plausibility check")
        return True  # No data = no failure (absence is not evidence)

    unusual_count = 0
    total_phrases = 0

    for phrase in phrases:
        start_beat = phrase.get("start_beat", 0)
        end_beat = phrase.get("end_beat", 0)
        length_beats = end_beat - start_beat

        if length_beats <= 0:
            continue
        total_phrases += 1

        # Check if length is a multiple of 16 beats (4 bars)
        # Allow multiples of 4 beats (1 bar) as acceptable
        if length_beats % 4 != 0:
            unusual_count += 1

    if total_phrases == 0:
        return True

    unusual_fraction = unusual_count / total_phrases
    if unusual_fraction > 0.3:  # More than 30% unusual phrase lengths
        notes.append(
            f"{unusual_count}/{total_phrases} phrases have non-bar-aligned "
            f"lengths ({unusual_fraction:.0%})"
        )
        return False

    return True
