"""Strata — Song Arrangement Engine.

Decomposes tracks into layers, patterns, and transitions to capture
the compositional formula of how a song is arranged.
"""

from .models import (
    ActivitySpan,
    ArrangementFormula,
    ArrangementTransition,
    AtomicEvent,
    LayerRole,
    Pattern,
    PatternInstance,
    PatternTemplate,
    PatternType,
    SectionArrangement,
    StemAnalysis,
    StemType,
    TransitionType,
)
from .storage import StrataStore

__all__ = [
    "ActivitySpan",
    "ArrangementFormula",
    "ArrangementTransition",
    "AtomicEvent",
    "LayerRole",
    "Pattern",
    "PatternInstance",
    "PatternTemplate",
    "PatternType",
    "SectionArrangement",
    "StemAnalysis",
    "StemType",
    "StrataStore",
    "TransitionType",
]
