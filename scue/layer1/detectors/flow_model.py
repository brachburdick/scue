"""EDM flow model labeler.

Relabels sections from generic ML labels (verse/chorus/break/etc.) to
EDM-specific labels (intro/verse/build/drop/breakdown/fakeout/outro)
using energy analysis and structural pattern priors.

The flow model applies soft constraints (scoring-based), not hard rules.
Unusual tracks get lower confidence rather than forced wrong labels.
"""

from __future__ import annotations

import logging

from ..models import Section

logger = logging.getLogger(__name__)

# EDM flow pattern fragments — common label sequences
# Used for scoring how well a label sequence matches known patterns
VALID_TRANSITIONS = {
    "intro": ["verse", "build", "drop"],
    "verse": ["build", "verse", "breakdown", "drop"],
    "build": ["drop", "fakeout"],
    "drop": ["breakdown", "drop", "outro", "verse"],
    "breakdown": ["build", "verse", "drop"],
    "fakeout": ["build", "breakdown"],
    "outro": [],  # terminal
}

# Generic label → EDM label mapping (from allin1 labels)
LABEL_MAP = {
    "intro": "intro",
    "outro": "outro",
    "start": "intro",
    "end": "outro",
}

# Maximum duration for a fakeout drop (in seconds)
FAKEOUT_MAX_DURATION_SEC = 15.0

# Minimum bar count for fakeout detection
FAKEOUT_MAX_BARS = 4


def classify_sections(
    sections: list[Section],
    section_features: list[dict[str, float]],
    track_stats: dict[str, float],
) -> list[Section]:
    """Relabel sections using EDM flow model and energy analysis.

    Args:
        sections: Sections with initial labels (from allin1 or snap pass).
        section_features: Per-section aggregate features from features.get_section_features().
        track_stats: Track-level stats from features.get_track_stats().

    Returns:
        New list of Sections with updated labels, confidence, and fakeout flags.
    """
    if not sections:
        return []

    # Phase 1: Energy-based classification for ambiguous labels
    classified = _energy_classify(sections, section_features, track_stats)

    # Phase 2: Build detection (rising energy before drops)
    classified = _detect_builds(classified, section_features, track_stats)

    # Phase 3: Fakeout detection
    classified = _detect_fakeouts(classified)

    # Phase 4: Score against flow patterns and adjust confidence
    classified = _score_flow(classified)

    # Phase 5: Ensure structural constraints (intro first, outro last)
    classified = _enforce_structure(classified)

    labels = [s.label for s in classified]
    logger.info("Flow model classification: %s", " → ".join(labels))

    return classified


def _energy_classify(
    sections: list[Section],
    section_features: list[dict[str, float]],
    track_stats: dict[str, float],
) -> list[Section]:
    """Classify sections by energy relative to track mean.

    Maps generic labels to EDM labels based on energy ratios:
    - High energy (RMS > 1.2× mean) + not bright → drop
    - Low energy (RMS < 0.7× mean) → breakdown
    - Rising energy slope → build candidate
    - Everything else → verse
    """
    result: list[Section] = []
    rms_mean = track_stats.get("rms_mean", 0.001)

    for i, section in enumerate(sections):
        feats = section_features[i] if i < len(section_features) else {}
        rms_ratio = feats.get("rms_mean", 0.0) / max(rms_mean, 0.001)
        centroid_ratio = feats.get("centroid_mean", 0.0) / max(track_stats.get("centroid_mean", 0.001), 0.001)

        original_label = section.original_label or section.label
        new_label = section.label

        # Direct mappings (intro/outro are unambiguous)
        if original_label in LABEL_MAP:
            new_label = LABEL_MAP[original_label]
        elif original_label in ("chorus",):
            # Chorus in EDM is usually a drop (high energy, not bright)
            if rms_ratio > 1.2 and centroid_ratio < 1.5:
                new_label = "drop"
            else:
                new_label = "drop"  # chorus → drop is the strong default in EDM
        elif original_label in ("break", "bridge"):
            new_label = "breakdown"
        elif original_label in ("inst", "solo"):
            new_label = _classify_by_energy(rms_ratio)
        elif original_label in ("verse",):
            new_label = "verse"
        elif original_label == "unknown":
            new_label = _classify_by_energy(rms_ratio)
        # else: keep existing label

        # Confidence based on energy clarity
        conf = _energy_confidence(rms_ratio, new_label)

        result.append(Section(
            label=new_label,
            start=section.start,
            end=section.end,
            confidence=conf,
            bar_count=section.bar_count,
            expected_bar_count=section.expected_bar_count,
            irregular_phrase=section.irregular_phrase,
            original_label=original_label,
            source=section.source,
        ))

    return result


def _classify_by_energy(rms_ratio: float) -> str:
    """Classify an ambiguous section purely by energy ratio."""
    if rms_ratio > 1.3:
        return "drop"
    elif rms_ratio < 0.7:
        return "breakdown"
    else:
        return "verse"


def _energy_confidence(rms_ratio: float, label: str) -> float:
    """Score confidence based on how well energy matches the label."""
    if label == "drop" and rms_ratio > 1.3:
        return 0.85
    elif label == "drop" and rms_ratio > 1.0:
        return 0.65
    elif label == "breakdown" and rms_ratio < 0.7:
        return 0.8
    elif label == "breakdown" and rms_ratio < 1.0:
        return 0.6
    elif label in ("intro", "outro"):
        return 0.9  # structural positions are high confidence
    elif label == "verse":
        return 0.6
    return 0.5


def _detect_builds(
    sections: list[Section],
    section_features: list[dict[str, float]],
    track_stats: dict[str, float],
) -> list[Section]:
    """Detect build sections: rising energy that precedes a drop."""
    result = list(sections)

    for i in range(len(result) - 1):
        feats = section_features[i] if i < len(section_features) else {}
        next_section = result[i + 1]

        rms_slope = feats.get("rms_slope", 0.0)
        centroid_slope = feats.get("centroid_slope", 0.0)

        # A build: rising energy, followed by a drop
        if (next_section.label == "drop"
                and rms_slope > 0
                and result[i].label in ("verse", "breakdown", "unknown")):
            result[i] = Section(
                label="build",
                start=result[i].start,
                end=result[i].end,
                confidence=0.75,
                bar_count=result[i].bar_count,
                expected_bar_count=result[i].expected_bar_count,
                irregular_phrase=result[i].irregular_phrase,
                original_label=result[i].original_label,
                source=result[i].source,
            )

    return result


def _detect_fakeouts(sections: list[Section]) -> list[Section]:
    """Detect fakeout drops: short drops followed by a build or breakdown.

    A fakeout is a drop-like section that is ≤4 bars (or ≤15s) and is
    followed by a build or breakdown rather than continuing into another
    drop or breakdown.
    """
    result = list(sections)

    for i in range(len(result) - 1):
        section = result[i]
        next_section = result[i + 1]

        is_short = (
            section.bar_count <= FAKEOUT_MAX_BARS
            or section.duration <= FAKEOUT_MAX_DURATION_SEC
        )

        if (section.label == "drop"
                and is_short
                and next_section.label in ("build", "breakdown")):
            result[i] = Section(
                label="fakeout",
                start=section.start,
                end=section.end,
                confidence=0.7,
                bar_count=section.bar_count,
                expected_bar_count=section.expected_bar_count,
                irregular_phrase=section.irregular_phrase,
                fakeout=True,
                original_label=section.original_label,
                source=section.source,
            )

    return result


def _score_flow(sections: list[Section]) -> list[Section]:
    """Score the label sequence against known EDM flow patterns.

    Adjusts confidence based on whether each transition is valid.
    """
    result = list(sections)

    for i in range(len(result) - 1):
        current = result[i]
        next_label = result[i + 1].label
        valid_next = VALID_TRANSITIONS.get(current.label, [])

        if next_label in valid_next:
            # Valid transition — boost confidence slightly
            new_conf = min(1.0, current.confidence + 0.05)
        else:
            # Invalid transition — reduce confidence
            new_conf = max(0.2, current.confidence - 0.15)

        if new_conf != current.confidence:
            result[i] = Section(
                label=current.label,
                start=current.start,
                end=current.end,
                confidence=round(new_conf, 3),
                bar_count=current.bar_count,
                expected_bar_count=current.expected_bar_count,
                irregular_phrase=current.irregular_phrase,
                fakeout=current.fakeout,
                original_label=current.original_label,
                source=current.source,
            )

    return result


def _enforce_structure(sections: list[Section]) -> list[Section]:
    """Ensure intro is first and outro is last.

    Soft enforcement — relabel with lower confidence rather than
    forcing if the energy doesn't match.
    """
    if not sections:
        return sections

    result = list(sections)

    # First section should be intro
    if result[0].label not in ("intro",):
        result[0] = Section(
            label="intro",
            start=result[0].start,
            end=result[0].end,
            confidence=min(result[0].confidence, 0.6),
            bar_count=result[0].bar_count,
            expected_bar_count=result[0].expected_bar_count,
            irregular_phrase=result[0].irregular_phrase,
            fakeout=result[0].fakeout,
            original_label=result[0].original_label,
            source=result[0].source,
        )

    # Last section should be outro
    if result[-1].label not in ("outro",):
        result[-1] = Section(
            label="outro",
            start=result[-1].start,
            end=result[-1].end,
            confidence=min(result[-1].confidence, 0.6),
            bar_count=result[-1].bar_count,
            expected_bar_count=result[-1].expected_bar_count,
            irregular_phrase=result[-1].irregular_phrase,
            fakeout=result[-1].fakeout,
            original_label=result[-1].original_label,
            source=result[-1].source,
        )

    return result
