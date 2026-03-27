"""Live Strata analyzer — builds ArrangementFormula from Pioneer hardware data.

Constructs arrangement analysis entirely from data streaming over Ethernet
from Pioneer hardware (phrase analysis, waveform, beat grid, cue points).
No audio files needed.

Pioneer phrase_analysis provides:
  - Section boundaries + labels (intro/verse/chorus/breakdown/build/drop/outro)
  - Mood IDs per phrase

Pioneer track_waveform provides:
  - 3-band RGB waveform (low/mid/high frequency energy)

Pioneer beat_grid provides:
  - Beat→time mapping for temporal alignment

Pioneer cue_points provides:
  - Hot cues + memory points for marker placement
"""

from __future__ import annotations

import logging
import time

from ...bridge.adapter import PlayerState
from ..models import RGBWaveform
from .grid_trust import score_beat_grid
from .models import (
    ActivitySpan,
    ArrangementFormula,
    ArrangementTransition,
    SectionArrangement,
    StemAnalysis,
    TransitionType,
)

logger = logging.getLogger(__name__)


# --- Pioneer phrase kind → section label mapping ---

PHRASE_KIND_MAP: dict[str, str] = {
    "intro": "intro",
    "verse": "verse",
    "chorus": "chorus",
    "bridge": "bridge",
    "breakdown": "breakdown",
    "build": "build",
    "buildup": "build",
    "drop": "drop",
    "outro": "outro",
    # Fallback for numeric/unknown kinds from some hardware
}

# Energy heuristic per section type (0.0-1.0)
SECTION_ENERGY: dict[str, float] = {
    "intro": 0.3,
    "verse": 0.5,
    "chorus": 0.75,
    "bridge": 0.5,
    "breakdown": 0.3,
    "build": 0.6,
    "drop": 0.9,
    "outro": 0.25,
}

# Energy trend heuristic per section type
SECTION_TREND: dict[str, str] = {
    "intro": "rising",
    "verse": "stable",
    "chorus": "peak",
    "bridge": "stable",
    "breakdown": "valley",
    "build": "rising",
    "drop": "peak",
    "outro": "falling",
}


def _beat_to_time_ms(beat: int, beat_grid: list[dict]) -> float:
    """Convert a beat number to a time in milliseconds using the beat grid.

    Finds the grid entry at or before the target beat, then interpolates:
      time_ms = entry.time_ms + (target_beat - entry.beat_number) * (60000 / entry.bpm)
    """
    if not beat_grid:
        return 0.0

    # Find the grid entry at or before the target beat
    entry = beat_grid[0]
    for bg in beat_grid:
        if bg["beat_number"] <= beat:
            entry = bg
        else:
            break

    bpm = entry.get("bpm", 120.0)
    if bpm <= 0:
        bpm = 120.0

    return entry["time_ms"] + (beat - entry["beat_number"]) * (60000.0 / bpm)


def _beat_to_time_s(beat: int, beat_grid: list[dict]) -> float:
    """Convert a beat number to seconds."""
    return _beat_to_time_ms(beat, beat_grid) / 1000.0


def _beat_to_bar(beat: int) -> int:
    """Convert a beat number (1-based) to a bar index (0-based, 4 beats/bar)."""
    return max(0, (beat - 1) // 4)


class LiveStrataAnalyzer:
    """Builds an ArrangementFormula from live Pioneer hardware data."""

    @staticmethod
    def build_from_saved_data(
        fingerprint: str, saved: dict,
    ) -> ArrangementFormula | None:
        """Build an arrangement formula from saved Pioneer data on disk.

        This is the offline counterpart to build_from_pioneer(). It accepts
        a dict loaded from a live_pioneer.json sidecar file (written by the
        live data persistence feature) and produces the same ArrangementFormula
        that would have been built live.

        Expected keys in ``saved``:
            phrases: list[dict]          — phrase analysis entries
            beat_grid: list[dict]        — beat grid entries
            pioneer_waveform: dict|None  — RGB waveform {low, mid, high, sample_rate, duration}
            hot_cues: list[dict]         — hot cue entries
            memory_points: list[dict]    — memory point entries
            duration: float              — track duration in seconds
            bpm: float                   — track BPM
            rekordbox_id: int            — rekordbox track ID

        Returns None if ``saved`` lacks phrases or beat_grid.
        """
        phrases = saved.get("phrases", [])
        beat_grid = saved.get("beat_grid", [])
        if not phrases or not beat_grid:
            logger.debug(
                "Saved data for %s: insufficient Pioneer data "
                "(phrases=%d, beat_grid=%d)",
                fingerprint[:16], len(phrases), len(beat_grid),
            )
            return None

        # Build a lightweight duck-typed object matching PlayerState fields
        # so we can reuse build_from_pioneer() logic.
        class _SavedPlayer:
            pass

        player = _SavedPlayer()
        player.player_number = 0  # type: ignore[attr-defined]
        player.phrases = phrases  # type: ignore[attr-defined]
        player.beat_grid = beat_grid  # type: ignore[attr-defined]
        player.pioneer_waveform = saved.get("pioneer_waveform")  # type: ignore[attr-defined]
        player.hot_cues = saved.get("hot_cues", [])  # type: ignore[attr-defined]
        player.memory_points = saved.get("memory_points", [])  # type: ignore[attr-defined]
        player.duration = saved.get("duration", 0.0)  # type: ignore[attr-defined]
        player.rekordbox_id = saved.get("rekordbox_id", 0)  # type: ignore[attr-defined]

        formula = LiveStrataAnalyzer.build_from_pioneer(player)  # type: ignore[arg-type]
        if formula is None:
            return None

        # Override the fingerprint (live uses "live_{id}", offline uses real fp)
        formula.fingerprint = fingerprint
        formula.pipeline_tier = "live_offline"
        formula.analysis_source = "pioneer_live"
        return formula

    @staticmethod
    def build_from_pioneer(player: PlayerState) -> ArrangementFormula | None:
        """Build an arrangement formula from Pioneer data on a PlayerState.

        Returns None if insufficient data (no phrases or no beat grid).
        """
        if not player.phrases or not player.beat_grid:
            logger.debug(
                "Player %d: insufficient Pioneer data for live strata "
                "(phrases=%d, beat_grid=%d)",
                player.player_number,
                len(player.phrases),
                len(player.beat_grid),
            )
            return None

        start_time = time.time()
        bg = player.beat_grid

        # --- 1. Map Pioneer phrases → sections ---
        sections: list[SectionArrangement] = []
        transitions: list[ArrangementTransition] = []
        prev_energy = 0.0

        for phrase in player.phrases:
            start_beat = phrase["start_beat"]
            end_beat = phrase["end_beat"]
            kind_raw = str(phrase.get("kind", "")).lower().strip()
            label = PHRASE_KIND_MAP.get(kind_raw, kind_raw or "unknown")

            start_s = _beat_to_time_s(start_beat, bg)
            end_s = _beat_to_time_s(end_beat, bg)
            bar_start = _beat_to_bar(start_beat)
            bar_end = _beat_to_bar(end_beat)

            energy_level = SECTION_ENERGY.get(label, 0.5)
            energy_trend = SECTION_TREND.get(label, "stable")

            sections.append(SectionArrangement(
                section_label=label,
                section_start=start_s,
                section_end=end_s,
                active_layers=["mix"],
                active_patterns=[],
                transitions=[],
                energy_level=energy_level,
                energy_trend=energy_trend,
                layer_count=1,
            ))

            # --- 2. Detect transitions at phrase boundaries ---
            energy_delta = energy_level - prev_energy
            if abs(energy_delta) > 0.15:
                transition_type = _classify_transition(label, energy_delta)
                transitions.append(ArrangementTransition(
                    type=transition_type,
                    timestamp=start_s,
                    bar_index=bar_start,
                    section_label=label,
                    layers_affected=["mix"],
                    patterns_affected=[],
                    energy_delta=round(energy_delta, 3),
                    description=_transition_description(transition_type, label),
                    confidence=0.7,
                ))
            prev_energy = energy_level

        # Assign section-local transitions
        for t in transitions:
            for sec in sections:
                if sec.section_start <= t.timestamp < sec.section_end:
                    sec.transitions.append(t)
                    break

        # --- 3. Build single "mix" stem using Pioneer waveform ---
        stems: list[StemAnalysis] = []
        waveform: RGBWaveform | None = None

        if player.pioneer_waveform:
            pw = player.pioneer_waveform
            waveform = RGBWaveform(
                sample_rate=pw.get("sample_rate", 150.0),
                duration=pw.get("duration", 0.0),
                low=pw.get("low", []),
                mid=pw.get("mid", []),
                high=pw.get("high", []),
            )

        # Full-track activity span
        if sections:
            track_start = sections[0].section_start
            track_end = sections[-1].section_end
        else:
            track_start = 0.0
            track_end = player.duration

        mix_stem = StemAnalysis(
            stem_type="other",  # "other" maps to the "mix" lane in ArrangementMap
            audio_path=None,
            layer_role="unknown",
            activity=[ActivitySpan(
                start=track_start,
                end=track_end,
                bar_start=0,
                bar_end=_beat_to_bar(player.beat_grid[-1]["beat_number"]) if player.beat_grid else 0,
                energy=0.5,
                confidence=0.7,
            )],
            events=[],
            patterns=[],
            energy_curve=_build_energy_curve(sections, track_end),
            waveform=waveform,
        )
        stems.append(mix_stem)

        # --- 4. Build cue point markers (as transitions) ---
        for cp in player.hot_cues:
            time_ms = cp.get("time_ms", 0)
            if time_ms <= 0:
                continue
            time_s = time_ms / 1000.0
            name = cp.get("name", f"Cue {cp.get('slot', '?')}")
            transitions.append(ArrangementTransition(
                type=TransitionType.ENERGY_SHIFT,
                timestamp=time_s,
                bar_index=0,
                section_label=name,
                layers_affected=[],
                patterns_affected=[],
                energy_delta=0.0,
                description=f"Hot cue: {name}",
                confidence=1.0,
            ))

        for mp in player.memory_points:
            time_ms = mp.get("time_ms", 0)
            if time_ms <= 0:
                continue
            time_s = time_ms / 1000.0
            name = mp.get("name", "Memory")
            transitions.append(ArrangementTransition(
                type=TransitionType.ENERGY_SHIFT,
                timestamp=time_s,
                bar_index=0,
                section_label=name,
                layers_affected=[],
                patterns_affected=[],
                energy_delta=0.0,
                description=f"Memory point: {name}",
                confidence=1.0,
            ))

        transitions.sort(key=lambda t: t.timestamp)

        # --- 5. Generate narrative ---
        narrative = _generate_live_narrative(sections)

        elapsed = time.time() - start_time

        # Use rekordbox_id as a pseudo-fingerprint for live data
        # (real fingerprint requires audio file)
        fingerprint = f"live_{player.rekordbox_id}"

        # --- 6. Score beat-grid trust ---
        grid_bpm = bg[0].get("bpm", 120.0) if bg else 0.0
        trust_report = score_beat_grid(
            beat_grid=bg,
            phrases=player.phrases,
            bpm=grid_bpm,
            duration=player.duration,
            source_id="pioneer_network",
        )

        return ArrangementFormula(
            fingerprint=fingerprint,
            version=1,
            stems=stems,
            patterns=[],  # No pattern discovery without audio
            sections=sections,
            transitions=transitions,
            total_layers=1,
            total_patterns=0,
            arrangement_complexity=round(
                min(1.0, len(sections) * 0.1 + len(transitions) * 0.05), 3
            ),
            energy_narrative=narrative,
            pipeline_tier="live",
            analysis_source="pioneer_live",
            stem_separation_model="",
            compute_time_seconds=round(elapsed, 4),
            grid_trust=trust_report.to_dict(),
        )


def _classify_transition(label: str, energy_delta: float) -> TransitionType:
    """Classify a transition type from section label and energy change."""
    if label == "drop":
        return TransitionType.DROP_IMPACT
    if label == "breakdown":
        return TransitionType.BREAKDOWN
    if energy_delta > 0.2:
        return TransitionType.ENERGY_SHIFT
    if energy_delta < -0.2:
        return TransitionType.ENERGY_SHIFT
    return TransitionType.ENERGY_SHIFT


def _transition_description(tt: TransitionType, label: str) -> str:
    """Generate a human-readable transition description."""
    if tt == TransitionType.DROP_IMPACT:
        return f"Drop impact → {label}"
    if tt == TransitionType.BREAKDOWN:
        return f"Breakdown → {label}"
    return f"Energy shift → {label}"


def _build_energy_curve(
    sections: list[SectionArrangement], track_end: float,
) -> list[float]:
    """Build a coarse energy curve from section energy levels.

    Returns ~1 value per second for the whole track.
    """
    if not sections or track_end <= 0:
        return []

    n_points = max(1, int(track_end))
    curve: list[float] = [0.0] * n_points

    for sec in sections:
        start_idx = max(0, int(sec.section_start))
        end_idx = min(n_points, int(sec.section_end))
        for i in range(start_idx, end_idx):
            curve[i] = sec.energy_level

    return curve


def _generate_live_narrative(sections: list[SectionArrangement]) -> str:
    """Generate a narrative from live section data."""
    if not sections:
        return ""
    parts: list[str] = []
    for sec in sections:
        label = sec.section_label.capitalize()
        parts.append(f"{label}: {sec.energy_trend} energy.")
    return " ".join(parts)
