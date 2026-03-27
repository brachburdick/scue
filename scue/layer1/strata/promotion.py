"""Tier promotion rules for the Strata engine.

Defines quality gates that a Strata method must pass before it can be
used in a given runtime tier. These are internal developer quality gates,
NOT user-facing — users can analyze at whatever tier they choose.

Each tier has scorecard thresholds and optional perturbation requirements.
The ``check_promotion`` function returns a verdict with pass/fail details.

Note: Per operator decision, promotion verdicts are never surfaced to
end users. They exist to guide development decisions only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .evaluation import StrataScorecard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier requirements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TierRequirements:
    """Scorecard thresholds for a specific tier.

    Fields set to None are not checked. All numeric fields represent
    minimum acceptable values (except where noted).
    """

    tier: str

    # Structure
    min_boundary_hit_rate: float | None = None
    min_label_agreement: float | None = None

    # Layers
    min_layer_f1: float | None = None

    # Transitions
    min_transition_precision: float | None = None
    min_transition_recall: float | None = None

    # Stability (these are MAXIMUMS — lower is better)
    max_boundary_jitter_seconds: float | None = None
    max_boundary_jitter_beats: float | None = None
    max_label_flip_rate: float | None = None
    max_transition_fp_per_minute: float | None = None

    # Latency (MAXIMUM — lower is better)
    max_latency_seconds: float | None = None

    # Whether perturbation suite must pass
    requires_perturbation_suite: bool = False

    # Description
    description: str = ""


# Default requirements per tier
QUICK_REQUIREMENTS = TierRequirements(
    tier="quick",
    min_boundary_hit_rate=0.6,
    max_latency_seconds=10.0,
    description="Fast, interpretable, dependency-light, stable enough for broad use",
)

STANDARD_REQUIREMENTS = TierRequirements(
    tier="standard",
    min_boundary_hit_rate=0.75,
    min_layer_f1=0.6,
    min_transition_precision=0.5,
    min_transition_recall=0.5,
    max_latency_seconds=180.0,  # 3 minutes
    description="Must materially beat quick on scorecard and justify heavier compute",
)

LIVE_REQUIREMENTS = TierRequirements(
    tier="live",
    min_boundary_hit_rate=0.6,
    max_boundary_jitter_beats=2.0,
    max_label_flip_rate=0.1,
    max_transition_fp_per_minute=1.0,
    max_latency_seconds=0.1,  # 100ms per update
    requires_perturbation_suite=True,
    description="Must stay aligned under DJ operations and pass perturbation tests",
)

LIVE_OFFLINE_REQUIREMENTS = TierRequirements(
    tier="live_offline",
    min_boundary_hit_rate=0.6,
    max_boundary_jitter_beats=2.0,
    max_label_flip_rate=0.1,
    description="Must reproduce live behavior from saved data closely enough for offline QA",
)

DEEP_REQUIREMENTS = TierRequirements(
    tier="deep",
    min_boundary_hit_rate=0.8,
    min_layer_f1=0.7,
    min_transition_precision=0.6,
    min_transition_recall=0.6,
    max_boundary_jitter_seconds=2.0,
    description="Must prove repeatable value; must beat standard on scorecard twice",
)

# Registry of all tier requirements
TIER_REQUIREMENTS: dict[str, TierRequirements] = {
    "quick": QUICK_REQUIREMENTS,
    "standard": STANDARD_REQUIREMENTS,
    "live": LIVE_REQUIREMENTS,
    "live_offline": LIVE_OFFLINE_REQUIREMENTS,
    "deep": DEEP_REQUIREMENTS,
}


# ---------------------------------------------------------------------------
# Promotion verdict
# ---------------------------------------------------------------------------


@dataclass
class PromotionVerdict:
    """Result of checking a scorecard against tier requirements."""

    eligible: bool
    tier: str
    passing_checks: list[str] = field(default_factory=list)
    failing_checks: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "eligible": self.eligible,
            "tier": self.tier,
            "passing_checks": self.passing_checks,
            "failing_checks": self.failing_checks,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Promotion check
# ---------------------------------------------------------------------------


def check_promotion(
    scorecard: StrataScorecard,
    target_tier: str,
    perturbation_results: dict[str, StrataScorecard] | None = None,
    requirements: TierRequirements | None = None,
) -> PromotionVerdict:
    """Check whether a scorecard meets the requirements for a target tier.

    Args:
        scorecard: The evaluation scorecard to check.
        target_tier: The tier to check against ("quick", "standard", etc.).
        perturbation_results: Optional dict of perturbation name → scorecard.
            Required if the tier has requires_perturbation_suite=True.
        requirements: Override the default requirements for the tier.

    Returns:
        PromotionVerdict with pass/fail details.
    """
    if requirements is None:
        requirements = TIER_REQUIREMENTS.get(target_tier)
        if requirements is None:
            return PromotionVerdict(
                eligible=False,
                tier=target_tier,
                failing_checks=[f"Unknown tier: {target_tier}"],
            )

    passing: list[str] = []
    failing: list[str] = []

    # --- Structure checks ---
    _check_min(
        "boundary_hit_rate",
        scorecard.structure.boundary_hit_rate,
        requirements.min_boundary_hit_rate,
        passing, failing,
    )
    _check_min(
        "label_agreement",
        scorecard.structure.label_agreement,
        requirements.min_label_agreement,
        passing, failing,
    )

    # --- Layer checks ---
    _check_min(
        "layer_f1",
        scorecard.layers.layer_f1,
        requirements.min_layer_f1,
        passing, failing,
    )

    # --- Transition checks ---
    _check_min(
        "transition_precision",
        scorecard.transitions.transition_precision,
        requirements.min_transition_precision,
        passing, failing,
    )
    _check_min(
        "transition_recall",
        scorecard.transitions.transition_recall,
        requirements.min_transition_recall,
        passing, failing,
    )

    # --- Stability checks (max thresholds — lower is better) ---
    _check_max(
        "boundary_jitter_seconds",
        scorecard.stability.boundary_jitter_seconds,
        requirements.max_boundary_jitter_seconds,
        passing, failing,
    )
    _check_max(
        "boundary_jitter_beats",
        scorecard.stability.boundary_jitter_beats,
        requirements.max_boundary_jitter_beats,
        passing, failing,
    )
    _check_max(
        "label_flip_rate",
        scorecard.stability.label_flip_rate,
        requirements.max_label_flip_rate,
        passing, failing,
    )
    _check_max(
        "transition_fp_per_minute",
        scorecard.stability.transition_false_positives_per_minute,
        requirements.max_transition_fp_per_minute,
        passing, failing,
    )

    # --- Latency check ---
    _check_max(
        "latency_seconds",
        scorecard.latency.total_analysis_seconds,
        requirements.max_latency_seconds,
        passing, failing,
    )

    # --- Perturbation suite check ---
    if requirements.requires_perturbation_suite:
        if perturbation_results is None:
            failing.append(
                "perturbation_suite: required but not provided"
            )
        else:
            # All perturbation runs must have non-zero boundary hit rate
            suite_ok = True
            for name, perturb_sc in perturbation_results.items():
                if name == "baseline":
                    continue
                if perturb_sc.structure.boundary_hit_rate <= 0:
                    failing.append(
                        f"perturbation_{name}: boundary_hit_rate=0 "
                        f"(method collapsed under perturbation)"
                    )
                    suite_ok = False

            if suite_ok:
                passing.append("perturbation_suite: all perturbations survived")

    eligible = len(failing) == 0
    notes = requirements.description

    return PromotionVerdict(
        eligible=eligible,
        tier=target_tier,
        passing_checks=passing,
        failing_checks=failing,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_min(
    name: str,
    actual: float,
    minimum: float | None,
    passing: list[str],
    failing: list[str],
) -> None:
    """Check that actual >= minimum."""
    if minimum is None:
        return
    if actual >= minimum:
        passing.append(f"{name}: {actual:.4f} >= {minimum:.4f}")
    else:
        failing.append(f"{name}: {actual:.4f} < {minimum:.4f}")


def _check_max(
    name: str,
    actual: float,
    maximum: float | None,
    passing: list[str],
    failing: list[str],
) -> None:
    """Check that actual <= maximum."""
    if maximum is None:
        return
    if actual <= maximum:
        passing.append(f"{name}: {actual:.4f} <= {maximum:.4f}")
    else:
        failing.append(f"{name}: {actual:.4f} > {maximum:.4f}")
