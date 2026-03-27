"""EDM priors registry for the Strata engine.

Extracts implicit domain knowledge (thresholds, heuristics, mappings) from
the Strata codebase into explicit, versioned, and auditable data structures.

Each prior is tagged with a kind:
  - "hard"       — directly constrains output (e.g., section energy lookup)
  - "soft"       — informs but does not override inference
  - "diagnostic" — used for evaluation/debugging only, not runtime

This module is additive — existing engine modules keep their inline constants.
The registry provides a single source of truth for documentation, evaluation,
and future config externalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PriorKind(str, Enum):
    """How a prior constrains the engine."""

    HARD = "hard"
    SOFT = "soft"
    DIAGNOSTIC = "diagnostic"


# ---------------------------------------------------------------------------
# Section-level priors (from live_analyzer.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionEnergyPrior:
    """Heuristic energy level per section type (0.0-1.0).

    Source: live_analyzer.py SECTION_ENERGY dict.
    Used by: LiveStrataAnalyzer to assign energy_level when no audio is available.
    """

    kind: PriorKind = PriorKind.HARD

    intro: float = 0.3
    verse: float = 0.5
    chorus: float = 0.75
    bridge: float = 0.5
    breakdown: float = 0.3
    build: float = 0.6
    drop: float = 0.9
    outro: float = 0.25

    def as_dict(self) -> dict[str, float]:
        """Return as a label->energy mapping (matches SECTION_ENERGY format)."""
        return {
            "intro": self.intro,
            "verse": self.verse,
            "chorus": self.chorus,
            "bridge": self.bridge,
            "breakdown": self.breakdown,
            "build": self.build,
            "drop": self.drop,
            "outro": self.outro,
        }


@dataclass(frozen=True)
class SectionTrendPrior:
    """Heuristic energy trend per section type.

    Source: live_analyzer.py SECTION_TREND dict.
    Used by: LiveStrataAnalyzer to assign energy_trend when no audio is available.
    """

    kind: PriorKind = PriorKind.HARD

    intro: str = "rising"
    verse: str = "stable"
    chorus: str = "peak"
    bridge: str = "stable"
    breakdown: str = "valley"
    build: str = "rising"
    drop: str = "peak"
    outro: str = "falling"

    def as_dict(self) -> dict[str, str]:
        """Return as a label->trend mapping (matches SECTION_TREND format)."""
        return {
            "intro": self.intro,
            "verse": self.verse,
            "chorus": self.chorus,
            "bridge": self.bridge,
            "breakdown": self.breakdown,
            "build": self.build,
            "drop": self.drop,
            "outro": self.outro,
        }


@dataclass(frozen=True)
class PhraseMapping:
    """Pioneer phrase kind -> SCUE section label mapping.

    Source: live_analyzer.py PHRASE_KIND_MAP dict.
    Used by: LiveStrataAnalyzer to translate Pioneer hardware phrase labels.
    """

    kind: PriorKind = PriorKind.HARD

    mapping: dict[str, str] = field(default_factory=lambda: {
        "intro": "intro",
        "verse": "verse",
        "chorus": "chorus",
        "bridge": "bridge",
        "breakdown": "breakdown",
        "build": "build",
        "buildup": "build",
        "drop": "drop",
        "outro": "outro",
    })


# ---------------------------------------------------------------------------
# Transition detection priors (from transitions.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionPrior:
    """Thresholds for transition detection at section boundaries.

    Source: transitions.py detect_transitions() and _classify_transition().
    """

    kind: PriorKind = PriorKind.SOFT

    # Minimum energy delta to flag a transition at all
    energy_threshold: float = 0.15

    # Window size (bars before/after boundary) for energy comparison
    comparison_window_bars: int = 2

    # Per-band delta threshold to identify a layer change
    band_change_threshold: float = 0.1

    # Section-label + energy delta -> transition type
    drop_energy_delta: float = 0.2
    breakdown_energy_delta: float = -0.2

    # Layer enter/exit requires this many layers + energy delta
    layer_enter_exit_delta: float = 0.15
    layer_enter_exit_min_layers: int = 2

    # Fill detection
    fill_spike_ratio: float = 1.8
    fill_proximity_seconds: float = 5.0


# ---------------------------------------------------------------------------
# Pattern discovery priors (from patterns.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternPrior:
    """Thresholds for drum pattern clustering and naming.

    Source: patterns.py discover_patterns().
    """

    kind: PriorKind = PriorKind.SOFT

    # Cosine similarity threshold for "same pattern"
    similarity_threshold: float = 0.85

    # Minimum instances to call it a repeating pattern
    min_repeats: int = 2

    # Variation classification thresholds
    exact_threshold: float = 0.99
    minor_threshold: float = 0.85


# ---------------------------------------------------------------------------
# Energy analysis priors (from energy.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnergyPrior:
    """Thresholds for energy analysis and pseudo-layer activity.

    Source: energy.py compute_energy_analysis() and _compute_pseudo_activity().
    """

    kind: PriorKind = PriorKind.SOFT

    # Frequency band boundaries (Hz) -- aligned with Pioneer mixer EQ
    low_band: tuple[int, int] = (20, 200)
    mid_band: tuple[int, int] = (200, 2500)
    high_band: tuple[int, int] = (2500, 11025)

    # Pseudo-activity detection
    threshold_ratio: float = 0.15
    min_span_bars: int = 2

    # Onset density threshold (fraction of mean onset strength)
    onset_threshold_ratio: float = 0.5

    # Energy trend classification
    slope_threshold: float = 0.05
    peak_multiplier: float = 1.3
    valley_multiplier: float = 0.7

    # Band-to-stem mapping for pseudo-layers
    band_stem_mapping: dict[str, str] = field(default_factory=lambda: {
        "low": "bass",
        "mid": "other",
        "high": "other",
    })


# ---------------------------------------------------------------------------
# Per-stem analysis priors (from per_stem.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StemActivityPrior:
    """Thresholds for per-stem activity detection in the standard tier.

    Source: per_stem.py module-level constants and analyze_stem().
    """

    kind: PriorKind = PriorKind.SOFT

    # Fraction of stem's max energy to count as "active"
    activity_threshold: float = 0.08

    # Minimum consecutive bars for an activity span
    min_activity_bars: int = 2

    # Confidence assigned to real stem activity (vs pseudo-activity at 0.6)
    stem_activity_confidence: float = 0.85
    pseudo_activity_confidence: float = 0.6

    # Per-stem event detection thresholds (standard tier, cleaner stems)
    kick_low_band_threshold: float = 0.4
    snare_mid_band_threshold: float = 0.35
    hihat_high_band_threshold: float = 0.3

    # Vocal presence threshold (fraction of max RMS)
    vocal_presence_threshold: float = 0.10

    # Synth onset delta for "other" stem
    synth_onset_delta: float = 0.15

    # Cross-stem transition merge window (seconds)
    merge_window_seconds: float = 2.0


# ---------------------------------------------------------------------------
# EDM structural priors (from domain knowledge)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EDMStructurePrior:
    """Domain knowledge about EDM track structure.

    These are not directly used by the current engine but are declared
    here for evaluation, documentation, and future use by constrained
    decoding methods.
    """

    kind: PriorKind = PriorKind.DIAGNOSTIC

    # Typical phrase lengths in bars
    typical_phrase_bars: list[int] = field(
        default_factory=lambda: [4, 8, 16, 32]
    )

    # Typical BPM range for EDM
    typical_bpm_range: tuple[float, float] = (100.0, 180.0)

    # Typical section ordering (descriptive, not prescriptive)
    typical_section_order: list[str] = field(
        default_factory=lambda: [
            "intro", "build", "drop", "breakdown", "build", "drop", "outro"
        ]
    )

    # Section labels expected in EDM
    edm_section_vocabulary: list[str] = field(
        default_factory=lambda: [
            "intro", "verse", "chorus", "bridge", "breakdown",
            "build", "drop", "outro",
        ]
    )

    # Typical time signature
    typical_meter: tuple[int, int] = (4, 4)


# ---------------------------------------------------------------------------
# Aggregate registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EDMPriors:
    """Complete registry of all EDM priors used by the Strata engine.

    This is the single source of truth for domain assumptions. Use
    ``load_default_priors()`` to get the current defaults matching the
    hardcoded values in the engine modules.
    """

    version: str = "1.0.0"

    section_energy: SectionEnergyPrior = field(default_factory=SectionEnergyPrior)
    section_trend: SectionTrendPrior = field(default_factory=SectionTrendPrior)
    phrase_mapping: PhraseMapping = field(default_factory=PhraseMapping)
    transitions: TransitionPrior = field(default_factory=TransitionPrior)
    patterns: PatternPrior = field(default_factory=PatternPrior)
    energy: EnergyPrior = field(default_factory=EnergyPrior)
    stem_activity: StemActivityPrior = field(default_factory=StemActivityPrior)
    edm_structure: EDMStructurePrior = field(default_factory=EDMStructurePrior)


def load_default_priors() -> EDMPriors:
    """Return the default EDM priors matching current engine constants."""
    return EDMPriors()


def priors_to_dict(priors: EDMPriors) -> dict:
    """Serialize EDMPriors to a JSON-compatible dict."""
    from dataclasses import asdict

    def _convert(obj: object) -> object:
        if isinstance(obj, PriorKind):
            return obj.value
        if isinstance(obj, tuple):
            return list(obj)
        return obj

    result = asdict(priors)
    return _walk_dict(result, _convert)


def priors_from_dict(data: dict) -> EDMPriors:
    """Deserialize a dict back into EDMPriors."""
    return EDMPriors(
        version=data.get("version", "1.0.0"),
        section_energy=_restore_dataclass(
            SectionEnergyPrior, data.get("section_energy", {})
        ),
        section_trend=_restore_dataclass(
            SectionTrendPrior, data.get("section_trend", {})
        ),
        phrase_mapping=_restore_dataclass(
            PhraseMapping, data.get("phrase_mapping", {})
        ),
        transitions=_restore_dataclass(
            TransitionPrior, data.get("transitions", {})
        ),
        patterns=_restore_dataclass(
            PatternPrior, data.get("patterns", {})
        ),
        energy=_restore_energy_prior(data.get("energy", {})),
        stem_activity=_restore_dataclass(
            StemActivityPrior, data.get("stem_activity", {})
        ),
        edm_structure=_restore_edm_structure(data.get("edm_structure", {})),
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _walk_dict(d: dict, convert: callable) -> dict:
    """Recursively apply convert to all values in a nested dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _walk_dict(v, convert)
        elif isinstance(v, list):
            result[k] = [
                _walk_dict(item, convert) if isinstance(item, dict)
                else convert(item)
                for item in v
            ]
        else:
            result[k] = convert(v)
    return result


def _restore_dataclass(cls: type, data: dict) -> object:
    """Restore a frozen dataclass from a dict, converting kind strings."""
    if not data:
        return cls()
    cleaned = {}
    for k, v in data.items():
        if k == "kind":
            cleaned[k] = PriorKind(v) if isinstance(v, str) else v
        else:
            cleaned[k] = v
    return cls(**cleaned)


def _restore_energy_prior(data: dict) -> EnergyPrior:
    """Restore EnergyPrior, converting band tuples from lists."""
    if not data:
        return EnergyPrior()
    cleaned = {}
    for k, v in data.items():
        if k == "kind":
            cleaned[k] = PriorKind(v) if isinstance(v, str) else v
        elif k in ("low_band", "mid_band", "high_band"):
            cleaned[k] = tuple(v) if isinstance(v, list) else v
        else:
            cleaned[k] = v
    return EnergyPrior(**cleaned)


def _restore_edm_structure(data: dict) -> EDMStructurePrior:
    """Restore EDMStructurePrior, converting tuples from lists."""
    if not data:
        return EDMStructurePrior()
    cleaned = {}
    for k, v in data.items():
        if k == "kind":
            cleaned[k] = PriorKind(v) if isinstance(v, str) else v
        elif k in ("typical_bpm_range", "typical_meter"):
            cleaned[k] = tuple(v) if isinstance(v, list) else v
        else:
            cleaned[k] = v
    return EDMStructurePrior(**cleaned)
