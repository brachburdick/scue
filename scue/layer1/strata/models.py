"""Strata data models — all dataclasses for arrangement analysis.

These are the canonical data structures for the Strata engine. The
ArrangementFormula is stored as JSON files per tier (quick/standard/deep),
separate from the main TrackAnalysis JSON.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import RGBWaveform


# ---------------------------------------------------------------------------
# Stems / Layers
# ---------------------------------------------------------------------------

class StemType(str, Enum):
    """Coarse stem categories from source separation."""
    DRUMS = "drums"
    BASS = "bass"
    VOCALS = "vocals"
    OTHER = "other"


class LayerRole(str, Enum):
    """Semantic role a layer plays in the arrangement."""
    RHYTHM = "rhythm"
    BASSLINE = "bassline"
    LEAD = "lead"
    PAD = "pad"
    ARPEGGIO = "arpeggio"
    FX = "fx"
    VOCAL = "vocal"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Activity (layer presence/absence)
# ---------------------------------------------------------------------------

@dataclass
class ActivitySpan:
    """A contiguous region where a layer is active (audible)."""
    start: float
    end: float
    bar_start: int
    bar_end: int
    energy: float = 0.5
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Atomic Events
# ---------------------------------------------------------------------------

@dataclass
class AtomicEvent:
    """A single musical occurrence within a layer.

    Extends MusicalEvent with stem attribution and richer metadata.
    Backward-compatible: can be converted to/from MusicalEvent.
    """
    type: str
    timestamp: float
    duration: float | None = None
    intensity: float = 0.5
    stem: str | None = None
    pitch: str | None = None
    beat_position: int | None = None
    bar_index: int | None = None
    confidence: float = 0.5
    source: str = "detector"
    payload: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

class PatternType(str, Enum):
    DRUM_GROOVE = "drum_groove"
    ARPEGGIO = "arpeggio"
    BASSLINE = "bassline"
    CHORD_PROGRESSION = "chord_prog"
    VOCAL_PHRASE = "vocal_phrase"
    PERCUSSION_FILL = "perc_fill"
    CUSTOM = "custom"


@dataclass
class PatternTemplate:
    """The archetypal version of a pattern."""
    events: list[AtomicEvent] = field(default_factory=list)
    duration_bars: int = 1
    duration_seconds: float = 0.0
    signature: str = ""


@dataclass
class PatternInstance:
    """One occurrence of a pattern in the track."""
    bar_start: int
    bar_end: int
    start: float = 0.0
    end: float = 0.0
    variation: str = "exact"
    variation_description: str = ""
    confidence: float = 0.5


@dataclass
class Pattern:
    """A named, repeating musical figure."""
    id: str
    name: str
    pattern_type: PatternType = PatternType.CUSTOM
    stem: str | None = None
    template: PatternTemplate = field(default_factory=PatternTemplate)
    instances: list[PatternInstance] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transitions (arrangement changes)
# ---------------------------------------------------------------------------

class TransitionType(str, Enum):
    LAYER_ENTER = "layer_enter"
    LAYER_EXIT = "layer_exit"
    PATTERN_CHANGE = "pattern_change"
    FILL = "fill"
    ENERGY_SHIFT = "energy_shift"
    BREAKDOWN = "breakdown"
    DROP_IMPACT = "drop_impact"


@dataclass
class ArrangementTransition:
    """A moment where the arrangement changes."""
    type: TransitionType
    timestamp: float
    bar_index: int = 0
    section_label: str = ""
    layers_affected: list[str] = field(default_factory=list)
    patterns_affected: list[str] = field(default_factory=list)
    energy_delta: float = 0.0
    description: str = ""
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Per-Stem Analysis
# ---------------------------------------------------------------------------

@dataclass
class StemAnalysis:
    """Analysis results for a single separated stem."""
    stem_type: str
    audio_path: str | None = None
    layer_role: str = "unknown"
    activity: list[ActivitySpan] = field(default_factory=list)
    events: list[AtomicEvent] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    energy_curve: list[float] = field(default_factory=list)
    waveform: "RGBWaveform | None" = None


# ---------------------------------------------------------------------------
# Per-Section Arrangement Summary
# ---------------------------------------------------------------------------

@dataclass
class SectionArrangement:
    """What's happening in a specific section, arrangement-wise."""
    section_label: str
    section_start: float
    section_end: float
    active_layers: list[str] = field(default_factory=list)
    active_patterns: list[str] = field(default_factory=list)
    transitions: list[ArrangementTransition] = field(default_factory=list)
    energy_level: float = 0.5
    energy_trend: str = "stable"
    layer_count: int = 0


# ---------------------------------------------------------------------------
# The Arrangement Formula — the top-level output
# ---------------------------------------------------------------------------

@dataclass
class ArrangementFormula:
    """Complete arrangement analysis for a single track.

    This is the top-level output of the Strata engine. Each tier produces
    its own ArrangementFormula stored independently.
    """
    fingerprint: str
    version: int = 1

    stems: list[StemAnalysis] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    sections: list[SectionArrangement] = field(default_factory=list)
    transitions: list[ArrangementTransition] = field(default_factory=list)

    total_layers: int = 0
    total_patterns: int = 0
    arrangement_complexity: float = 0.0
    energy_narrative: str = ""

    pipeline_tier: str = "quick"
    analysis_source: str = "analysis"   # "analysis" | "pioneer_enriched" | "pioneer_reanalyzed"
    stem_separation_model: str = ""
    compute_time_seconds: float = 0.0
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Serialization Helpers
# ---------------------------------------------------------------------------

def _activity_to_dict(span: ActivitySpan) -> dict:
    return {
        "start": span.start,
        "end": span.end,
        "bar_start": span.bar_start,
        "bar_end": span.bar_end,
        "energy": span.energy,
        "confidence": span.confidence,
    }


def _activity_from_dict(d: dict) -> ActivitySpan:
    return ActivitySpan(
        start=d["start"],
        end=d["end"],
        bar_start=d.get("bar_start", 0),
        bar_end=d.get("bar_end", 0),
        energy=d.get("energy", 0.5),
        confidence=d.get("confidence", 0.5),
    )


def _event_to_dict(e: AtomicEvent) -> dict:
    return {
        "type": e.type,
        "timestamp": e.timestamp,
        "duration": e.duration,
        "intensity": e.intensity,
        "stem": e.stem,
        "pitch": e.pitch,
        "beat_position": e.beat_position,
        "bar_index": e.bar_index,
        "confidence": e.confidence,
        "source": e.source,
        "payload": e.payload,
    }


def _event_from_dict(d: dict) -> AtomicEvent:
    return AtomicEvent(
        type=d["type"],
        timestamp=d["timestamp"],
        duration=d.get("duration"),
        intensity=d.get("intensity", 0.5),
        stem=d.get("stem"),
        pitch=d.get("pitch"),
        beat_position=d.get("beat_position"),
        bar_index=d.get("bar_index"),
        confidence=d.get("confidence", 0.5),
        source=d.get("source", "detector"),
        payload=d.get("payload", {}),
    )


def _template_to_dict(t: PatternTemplate) -> dict:
    return {
        "events": [_event_to_dict(e) for e in t.events],
        "duration_bars": t.duration_bars,
        "duration_seconds": t.duration_seconds,
        "signature": t.signature,
    }


def _template_from_dict(d: dict) -> PatternTemplate:
    return PatternTemplate(
        events=[_event_from_dict(e) for e in d.get("events", [])],
        duration_bars=d.get("duration_bars", 1),
        duration_seconds=d.get("duration_seconds", 0.0),
        signature=d.get("signature", ""),
    )


def _instance_to_dict(inst: PatternInstance) -> dict:
    return {
        "bar_start": inst.bar_start,
        "bar_end": inst.bar_end,
        "start": inst.start,
        "end": inst.end,
        "variation": inst.variation,
        "variation_description": inst.variation_description,
        "confidence": inst.confidence,
    }


def _instance_from_dict(d: dict) -> PatternInstance:
    return PatternInstance(
        bar_start=d["bar_start"],
        bar_end=d["bar_end"],
        start=d.get("start", 0.0),
        end=d.get("end", 0.0),
        variation=d.get("variation", "exact"),
        variation_description=d.get("variation_description", ""),
        confidence=d.get("confidence", 0.5),
    )


def _pattern_to_dict(p: Pattern) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "pattern_type": p.pattern_type.value if isinstance(p.pattern_type, PatternType) else p.pattern_type,
        "stem": p.stem,
        "template": _template_to_dict(p.template),
        "instances": [_instance_to_dict(i) for i in p.instances],
        "tags": p.tags,
    }


def _pattern_from_dict(d: dict) -> Pattern:
    pt = d.get("pattern_type", "custom")
    try:
        pattern_type = PatternType(pt)
    except ValueError:
        pattern_type = PatternType.CUSTOM
    return Pattern(
        id=d["id"],
        name=d.get("name", ""),
        pattern_type=pattern_type,
        stem=d.get("stem"),
        template=_template_from_dict(d.get("template", {})),
        instances=[_instance_from_dict(i) for i in d.get("instances", [])],
        tags=d.get("tags", []),
    )


def _transition_to_dict(t: ArrangementTransition) -> dict:
    return {
        "type": t.type.value if isinstance(t.type, TransitionType) else t.type,
        "timestamp": t.timestamp,
        "bar_index": t.bar_index,
        "section_label": t.section_label,
        "layers_affected": t.layers_affected,
        "patterns_affected": t.patterns_affected,
        "energy_delta": t.energy_delta,
        "description": t.description,
        "confidence": t.confidence,
    }


def _transition_from_dict(d: dict) -> ArrangementTransition:
    tt = d.get("type", "energy_shift")
    try:
        transition_type = TransitionType(tt)
    except ValueError:
        transition_type = TransitionType.ENERGY_SHIFT
    return ArrangementTransition(
        type=transition_type,
        timestamp=d["timestamp"],
        bar_index=d.get("bar_index", 0),
        section_label=d.get("section_label", ""),
        layers_affected=d.get("layers_affected", []),
        patterns_affected=d.get("patterns_affected", []),
        energy_delta=d.get("energy_delta", 0.0),
        description=d.get("description", ""),
        confidence=d.get("confidence", 0.5),
    )


def _stem_to_dict(s: StemAnalysis) -> dict:
    d: dict = {
        "stem_type": s.stem_type,
        "audio_path": s.audio_path,
        "layer_role": s.layer_role,
        "activity": [_activity_to_dict(a) for a in s.activity],
        "events": [_event_to_dict(e) for e in s.events],
        "patterns": [_pattern_to_dict(p) for p in s.patterns],
        "energy_curve": s.energy_curve,
    }
    if s.waveform is not None:
        d["waveform"] = {
            "sample_rate": s.waveform.sample_rate,
            "duration": s.waveform.duration,
            "low": s.waveform.low,
            "mid": s.waveform.mid,
            "high": s.waveform.high,
        }
    return d


def _stem_from_dict(d: dict) -> StemAnalysis:
    from ..models import RGBWaveform

    wf_data = d.get("waveform")
    waveform = None
    if wf_data and isinstance(wf_data, dict):
        waveform = RGBWaveform(
            sample_rate=wf_data.get("sample_rate", 150),
            duration=wf_data.get("duration", 0.0),
            low=wf_data.get("low", []),
            mid=wf_data.get("mid", []),
            high=wf_data.get("high", []),
        )
    return StemAnalysis(
        stem_type=d["stem_type"],
        audio_path=d.get("audio_path"),
        layer_role=d.get("layer_role", "unknown"),
        activity=[_activity_from_dict(a) for a in d.get("activity", [])],
        events=[_event_from_dict(e) for e in d.get("events", [])],
        patterns=[_pattern_from_dict(p) for p in d.get("patterns", [])],
        energy_curve=d.get("energy_curve", []),
        waveform=waveform,
    )


def _section_arr_to_dict(s: SectionArrangement) -> dict:
    return {
        "section_label": s.section_label,
        "section_start": s.section_start,
        "section_end": s.section_end,
        "active_layers": s.active_layers,
        "active_patterns": s.active_patterns,
        "transitions": [_transition_to_dict(t) for t in s.transitions],
        "energy_level": s.energy_level,
        "energy_trend": s.energy_trend,
        "layer_count": s.layer_count,
    }


def _section_arr_from_dict(d: dict) -> SectionArrangement:
    return SectionArrangement(
        section_label=d["section_label"],
        section_start=d["section_start"],
        section_end=d["section_end"],
        active_layers=d.get("active_layers", []),
        active_patterns=d.get("active_patterns", []),
        transitions=[_transition_from_dict(t) for t in d.get("transitions", [])],
        energy_level=d.get("energy_level", 0.5),
        energy_trend=d.get("energy_trend", "stable"),
        layer_count=d.get("layer_count", 0),
    )


def formula_to_dict(f: ArrangementFormula) -> dict:
    """Serialize an ArrangementFormula to a JSON-safe dict."""
    return {
        "fingerprint": f.fingerprint,
        "version": f.version,
        "stems": [_stem_to_dict(s) for s in f.stems],
        "patterns": [_pattern_to_dict(p) for p in f.patterns],
        "sections": [_section_arr_to_dict(s) for s in f.sections],
        "transitions": [_transition_to_dict(t) for t in f.transitions],
        "total_layers": f.total_layers,
        "total_patterns": f.total_patterns,
        "arrangement_complexity": f.arrangement_complexity,
        "energy_narrative": f.energy_narrative,
        "pipeline_tier": f.pipeline_tier,
        "analysis_source": f.analysis_source,
        "stem_separation_model": f.stem_separation_model,
        "compute_time_seconds": f.compute_time_seconds,
        "created_at": f.created_at,
    }


def formula_from_dict(d: dict) -> ArrangementFormula:
    """Deserialize an ArrangementFormula from a dict."""
    return ArrangementFormula(
        fingerprint=d["fingerprint"],
        version=d.get("version", 1),
        stems=[_stem_from_dict(s) for s in d.get("stems", [])],
        patterns=[_pattern_from_dict(p) for p in d.get("patterns", [])],
        sections=[_section_arr_from_dict(s) for s in d.get("sections", [])],
        transitions=[_transition_from_dict(t) for t in d.get("transitions", [])],
        total_layers=d.get("total_layers", 0),
        total_patterns=d.get("total_patterns", 0),
        arrangement_complexity=d.get("arrangement_complexity", 0.0),
        energy_narrative=d.get("energy_narrative", ""),
        pipeline_tier=d.get("pipeline_tier", "quick"),
        analysis_source=d.get("analysis_source", "analysis"),
        stem_separation_model=d.get("stem_separation_model", ""),
        compute_time_seconds=d.get("compute_time_seconds", 0.0),
        created_at=d.get("created_at", 0.0),
    )
