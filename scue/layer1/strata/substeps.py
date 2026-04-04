"""Substep strategy protocols for the Strata analysis pipeline.

Each substep in the pipeline (transition detection, energy trend
classification, fill detection) can be swapped out for an alternative
implementation. Strategies implement these protocols and are selected
via config/strata_variants.yaml.

Mirrors the DetectorProtocol pattern from scue/layer1/detectors/events.py.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models import Section
from .energy import EnergyAnalysis
from .models import ArrangementTransition


@runtime_checkable
class TransitionStrategy(Protocol):
    """Strategy for detecting arrangement transitions at section boundaries."""

    name: str

    def detect(
        self,
        sections: list[Section],
        energy: EnergyAnalysis,
        downbeats: list[float],
    ) -> list[ArrangementTransition]:
        """Detect transitions and return them sorted by timestamp."""
        ...


@runtime_checkable
class EnergyTrendStrategy(Protocol):
    """Strategy for classifying energy trend within a section."""

    name: str

    def classify(self, bar_energies: list[float], window: int = 4) -> str:
        """Return a trend label: 'rising' | 'falling' | 'stable' | 'peak' | 'valley'."""
        ...


@runtime_checkable
class FillStrategy(Protocol):
    """Strategy for detecting fill transitions (onset density spikes near boundaries)."""

    name: str

    def detect(
        self,
        energy: EnergyAnalysis,
        downbeats: list[float],
        sections: list[Section],
    ) -> list[ArrangementTransition]:
        """Detect fill-like transitions and return them sorted by timestamp."""
        ...
