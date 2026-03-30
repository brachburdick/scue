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

        has_waveform = bool(player.pioneer_waveform)

        for phrase in player.phrases:
            start_beat = phrase["start_beat"]
            end_beat = phrase["end_beat"]
            kind_raw = str(phrase.get("kind", "")).lower().strip()
            label = PHRASE_KIND_MAP.get(kind_raw, kind_raw or "unknown")

            start_s = _beat_to_time_s(start_beat, bg)
            end_s = _beat_to_time_s(end_beat, bg)
            bar_start = _beat_to_bar(start_beat)
            bar_end = _beat_to_bar(end_beat)

            # Use real waveform energy when available, fall back to heuristic
            if has_waveform:
                energy_level, energy_trend = _waveform_section_energy(
                    player.pioneer_waveform, start_s, end_s,
                )
            else:
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

        # Activity spans — real waveform-derived when available, else full-track
        if sections:
            track_start = sections[0].section_start
            track_end = sections[-1].section_end
        else:
            track_start = 0.0
            track_end = player.duration

        if has_waveform:
            activity_spans = _waveform_activity_spans(player.pioneer_waveform, bg)
        else:
            activity_spans = {}

        # Build stems from activity spans when available
        if activity_spans:
            for stem_type, spans in activity_spans.items():
                stems.append(StemAnalysis(
                    stem_type=stem_type,
                    audio_path=None,
                    layer_role="unknown",
                    activity=spans,
                    events=[],
                    patterns=[],
                ))

            # Populate active_layers on sections from real activity
            for sec in sections:
                active: list[str] = []
                for stem_type, spans in activity_spans.items():
                    for span in spans:
                        if span.start < sec.section_end and span.end > sec.section_start:
                            if stem_type not in active:
                                active.append(stem_type)
                            break
                sec.active_layers = active if active else ["mix"]
                sec.layer_count = len(sec.active_layers)

        # Mix stem carries energy curve and waveform visual data
        full_activity = [ActivitySpan(
            start=track_start, end=track_end,
            bar_start=0,
            bar_end=_beat_to_bar(bg[-1]["beat_number"]) if bg else 0,
            energy=0.5, confidence=0.7,
        )]
        mix_stem = StemAnalysis(
            stem_type="other",
            audio_path=None,
            layer_role="unknown",
            activity=full_activity if not activity_spans else [],
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
            total_layers=len(stems),
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


# --- Pioneer waveform energy extraction ---

def _waveform_section_energy(
    waveform: dict, section_start: float, section_end: float,
) -> tuple[float, str]:
    """Compute real energy level and trend from Pioneer waveform for a section.

    Args:
        waveform: dict with keys low, mid, high (lists of 0.0-1.0),
                  sample_rate (samples/sec), duration (seconds).
        section_start: Section start time in seconds.
        section_end: Section end time in seconds.

    Returns:
        (energy_level, energy_trend) where energy_level is 0.0-1.0 and
        trend is "rising" | "falling" | "stable" | "peak" | "valley".
    """
    sr = waveform.get("sample_rate", 150.0)
    low = waveform.get("low", [])
    mid = waveform.get("mid", [])
    high = waveform.get("high", [])

    if not low or sr <= 0:
        return 0.5, "stable"

    n = len(low)
    i_start = max(0, int(section_start * sr))
    i_end = min(n, int(section_end * sr))

    if i_end <= i_start:
        return 0.5, "stable"

    # Compute mean energy across the 3 bands for this section
    section_energy = 0.0
    for i in range(i_start, i_end):
        lo = low[i] if i < len(low) else 0.0
        mi = mid[i] if i < len(mid) else 0.0
        hi = high[i] if i < len(high) else 0.0
        section_energy += lo + mi + hi
    section_energy /= (i_end - i_start) * 3  # normalize to 0-1 range

    # Compute trend: compare first quarter vs last quarter
    quarter = max(1, (i_end - i_start) // 4)
    first_q = 0.0
    last_q = 0.0
    for i in range(i_start, i_start + quarter):
        lo = low[i] if i < len(low) else 0.0
        mi = mid[i] if i < len(mid) else 0.0
        hi = high[i] if i < len(high) else 0.0
        first_q += lo + mi + hi
    first_q /= quarter * 3

    for i in range(i_end - quarter, i_end):
        lo = low[i] if i < len(low) else 0.0
        mi = mid[i] if i < len(mid) else 0.0
        hi = high[i] if i < len(high) else 0.0
        last_q += lo + mi + hi
    last_q /= quarter * 3

    delta = last_q - first_q
    if delta > 0.08:
        trend = "rising"
    elif delta < -0.08:
        trend = "falling"
    elif section_energy > 0.65:
        trend = "peak"
    elif section_energy < 0.2:
        trend = "valley"
    else:
        trend = "stable"

    return round(section_energy, 3), trend


def _waveform_activity_spans(
    waveform: dict,
    beat_grid: list[dict],
    threshold_ratio: float = 0.15,
    min_span_bars: int = 2,
) -> dict[str, list[ActivitySpan]]:
    """Derive pseudo-activity spans from Pioneer waveform bands.

    Thresholds each band to find regions where that frequency range is
    "active" (above threshold_ratio of max). Similar to energy.py's
    pseudo-activity but using Pioneer waveform instead of STFT.

    Returns dict mapping stem-like names to ActivitySpan lists:
        "bass" from low band, "other" from mid+high bands.
    """
    sr = waveform.get("sample_rate", 150.0)
    low = waveform.get("low", [])
    mid = waveform.get("mid", [])
    high = waveform.get("high", [])
    duration = waveform.get("duration", 0.0)

    if not low or sr <= 0 or duration <= 0:
        return {}

    # Compute per-bar averages using beat grid
    # Build bar boundaries from beat grid
    if not beat_grid:
        return {}

    bpm = beat_grid[0].get("bpm", 128.0)
    bar_duration = 4 * 60.0 / bpm  # seconds per bar
    n_bars = max(1, int(duration / bar_duration))

    def _band_bar_energy(band: list[float]) -> list[float]:
        """Average band energy per bar."""
        result = []
        for bar_idx in range(n_bars):
            bar_start_s = bar_idx * bar_duration
            bar_end_s = (bar_idx + 1) * bar_duration
            i_start = max(0, int(bar_start_s * sr))
            i_end = min(len(band), int(bar_end_s * sr))
            if i_end <= i_start:
                result.append(0.0)
                continue
            avg = sum(band[i_start:i_end]) / (i_end - i_start)
            result.append(avg)
        return result

    low_bars = _band_bar_energy(low)
    # Combine mid+high for "other" stem
    combined_mh = [
        (mid[i] if i < len(mid) else 0.0) + (high[i] if i < len(high) else 0.0)
        for i in range(len(low))
    ]
    mh_bars = _band_bar_energy(combined_mh)

    def _find_spans(
        bar_energies: list[float], stem_type: str,
    ) -> list[ActivitySpan]:
        """Find contiguous bars above threshold and return ActivitySpan list."""
        if not bar_energies:
            return []
        max_e = max(bar_energies) if bar_energies else 1.0
        threshold = max_e * threshold_ratio
        spans: list[ActivitySpan] = []
        in_span = False
        span_start = 0

        for i, e in enumerate(bar_energies):
            if e > threshold and not in_span:
                in_span = True
                span_start = i
            elif e <= threshold and in_span:
                if i - span_start >= min_span_bars:
                    spans.append(ActivitySpan(
                        start=span_start * bar_duration,
                        end=i * bar_duration,
                        bar_start=span_start,
                        bar_end=i,
                        energy=sum(bar_energies[span_start:i]) / (i - span_start),
                        confidence=0.7,
                    ))
                in_span = False

        # Close final span
        if in_span and len(bar_energies) - span_start >= min_span_bars:
            spans.append(ActivitySpan(
                start=span_start * bar_duration,
                end=len(bar_energies) * bar_duration,
                bar_start=span_start,
                bar_end=len(bar_energies),
                energy=sum(bar_energies[span_start:]) / (len(bar_energies) - span_start),
                confidence=0.7,
            ))

        return spans

    result: dict[str, list[ActivitySpan]] = {}
    bass_spans = _find_spans(low_bars, "bass")
    if bass_spans:
        result["bass"] = bass_spans
    other_spans = _find_spans(mh_bars, "other")
    if other_spans:
        result["other"] = other_spans

    return result


def _generate_live_narrative(sections: list[SectionArrangement]) -> str:
    """Generate a narrative from live section data."""
    if not sections:
        return ""
    parts: list[str] = []
    for sec in sections:
        label = sec.section_label.capitalize()
        parts.append(f"{label}: {sec.energy_trend} energy.")
    return " ".join(parts)
