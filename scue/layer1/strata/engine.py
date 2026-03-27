"""Strata analysis engine — orchestrates the arrangement analysis pipeline.

Quick tier stages:
  A. Read existing M7 detector output (events + drum patterns)
  B. Compute per-bar energy in 3 frequency bands + onset density
  C. Discover patterns from drum pattern repetition + auto-naming
  D. Detect transitions at section boundaries
  E. Assemble ArrangementFormula

Standard tier stages:
  A. Load track analysis (same as quick)
  B. Stem separation via demucs (cached)
  C. Per-stem analysis (energy, events, patterns, activity)
  D. Cross-stem transition detection
  E. Assemble ArrangementFormula with real stem data
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from ..models import TrackAnalysis
from ..storage import TrackStore
from .energy import EnergyAnalysis, compute_energy_analysis
from .models import (
    ArrangementFormula,
    Pattern,
    SectionArrangement,
    StemAnalysis,
    StemType,
)
from .patterns import discover_patterns
from .priors import EDMPriors
from .storage import StrataStore
from .transitions import compute_section_energy, detect_transitions

logger = logging.getLogger(__name__)


class StrataEngine:
    """Orchestrates Strata arrangement analysis."""

    def __init__(
        self,
        tracks_dir: Path,
        strata_store: StrataStore,
        priors: EDMPriors | None = None,
    ) -> None:
        self._track_store = TrackStore(tracks_dir)
        self._strata_store = strata_store
        self._priors = priors

    def analyze_quick(
        self, fingerprint: str, analysis_version: int | None = None,
    ) -> ArrangementFormula:
        """Run the quick tier analysis.

        Produces an arrangement formula from existing M7 analysis data
        without stem separation. Total time: ~2-3s.

        Args:
            fingerprint: Track fingerprint.
            analysis_version: Specific TrackAnalysis version to use. If None,
                uses load_latest() (highest available version).
        """
        start_time = time.time()
        logger.info("Strata quick tier: starting for %s", fingerprint[:16])

        # Load track analysis (specific version or latest)
        if analysis_version is not None:
            analysis = self._track_store.load(fingerprint, version=analysis_version)
        else:
            analysis = self._track_store.load_latest(fingerprint)
        if analysis is None:
            raise ValueError(f"No track analysis found for {fingerprint[:16]}. Run analysis first.")

        # Stage A: Read existing M7 output
        logger.info("  Stage A: Reading M7 detector output")
        # Events and drum_patterns already on the analysis object

        # Stage B: Energy/activity analysis
        logger.info("  Stage B: Computing per-bar energy")
        energy = self._compute_energy(analysis)

        # Stage C: Pattern discovery
        logger.info("  Stage C: Discovering patterns")
        patterns = discover_patterns(
            analysis.drum_patterns,
            analysis.downbeats,
            analysis.beats,
        )

        # Stage D: Transition detection
        logger.info("  Stage D: Detecting transitions")
        transitions = detect_transitions(
            analysis.sections,
            energy,
            analysis.downbeats,
        )

        # Stage E: Assembly
        logger.info("  Stage E: Assembling formula")
        formula = self._assemble(
            fingerprint=fingerprint,
            analysis=analysis,
            energy=energy,
            patterns=patterns,
            transitions=transitions,
            tier="quick",
            start_time=start_time,
        )

        # Save (source derived from the TrackAnalysis that was used)
        source = analysis.source if analysis.source in ("analysis", "pioneer_enriched", "pioneer_reanalyzed") else "analysis"
        formula.analysis_source = source
        self._strata_store.save(formula, "quick", source=source)
        elapsed = time.time() - start_time
        logger.info("Strata quick tier complete: %d patterns, %d transitions, %.1fs",
                     len(patterns), len(transitions), elapsed)
        return formula

    def analyze_standard(
        self,
        fingerprint: str,
        analysis_version: int | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> ArrangementFormula:
        """Run the standard tier analysis.

        Adds stem separation via demucs and runs per-stem analysis for
        richer arrangement data. Total time: ~1-2 minutes depending on
        track length and hardware.
        """
        from .per_stem import analyze_stem, detect_cross_stem_transitions
        from .separation import StemSeparator, is_demucs_available

        if not is_demucs_available():
            raise RuntimeError(
                "Standard tier requires demucs and torch. "
                "Install with: pip install demucs torch"
            )

        start_time = time.time()
        logger.info("Strata standard tier: starting for %s", fingerprint[:16])

        def _progress(step: int, name: str) -> None:
            if progress_callback is not None:
                progress_callback(step, name)

        # Stage A: Load track analysis (specific version or latest)
        _progress(1, "Loading track analysis")
        if analysis_version is not None:
            analysis = self._track_store.load(fingerprint, version=analysis_version)
        else:
            analysis = self._track_store.load_latest(fingerprint)
        if analysis is None:
            raise ValueError(f"No track analysis found for {fingerprint[:16]}. Run analysis first.")

        audio_path = Path(analysis.audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Stage B: Stem separation (cached)
        _progress(2, "Stem separation (demucs)")
        logger.info("  Stage B: Stem separation")
        separator = StemSeparator(strata_dir=self._strata_store.base_dir)
        stem_paths = separator.separate(audio_path, fingerprint)
        logger.info("  Stems: %s", [s.value for s in stem_paths.keys()])

        # Stage C: Per-stem analysis
        _progress(3, "Per-stem analysis")
        logger.info("  Stage C: Per-stem analysis")
        stems: list[StemAnalysis] = []
        all_patterns: list[Pattern] = []
        for stem_type, stem_path in stem_paths.items():
            stem_result = analyze_stem(
                stem_path=stem_path,
                stem_type=stem_type,
                downbeats=analysis.downbeats,
                beats=analysis.beats,
                duration=analysis.duration,
                sections=analysis.sections,
                drum_patterns=analysis.drum_patterns if stem_type == StemType.DRUMS else None,
            )
            stems.append(stem_result)
            all_patterns.extend(stem_result.patterns)

        # Stage D: Cross-stem transition detection
        _progress(4, "Cross-stem transitions")
        logger.info("  Stage D: Cross-stem transitions")
        cross_transitions = detect_cross_stem_transitions(
            stems, analysis.downbeats, analysis.sections,
        )

        # Also run the existing energy-based transition detection on the full mix
        energy = self._compute_energy(analysis)
        energy_transitions = detect_transitions(
            analysis.sections, energy, analysis.downbeats,
        )

        # Merge transitions, preferring cross-stem where timestamps overlap
        transitions = _merge_transitions(cross_transitions, energy_transitions)

        # Stage E: Assembly
        _progress(5, "Assembling formula")
        logger.info("  Stage E: Assembling formula")
        formula = self._assemble_standard(
            fingerprint=fingerprint,
            analysis=analysis,
            stems=stems,
            patterns=all_patterns,
            transitions=transitions,
            energy=energy,
            start_time=start_time,
        )

        # Save (source derived from the TrackAnalysis that was used)
        source = analysis.source if analysis.source in ("analysis", "pioneer_enriched", "pioneer_reanalyzed") else "analysis"
        formula.analysis_source = source
        self._strata_store.save(formula, "standard", source=source)
        elapsed = time.time() - start_time
        logger.info(
            "Strata standard tier complete: %d stems, %d patterns, %d transitions, %.1fs",
            len(stems), len(all_patterns), len(transitions), elapsed,
        )
        return formula

    def analyze(
        self,
        fingerprint: str,
        tiers: list[str],
        analysis_version: int | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, ArrangementFormula]:
        """Run analysis for the requested tiers.

        Args:
            fingerprint: Track fingerprint.
            tiers: List of tier names to run.
            analysis_version: Specific TrackAnalysis version. If None, uses latest.
            progress_callback: Optional callback for step progress (step_number, step_name).

        Returns a dict mapping tier name to ArrangementFormula.
        """
        results: dict[str, ArrangementFormula] = {}

        if "quick" in tiers:
            results["quick"] = self.analyze_quick(fingerprint, analysis_version=analysis_version)

        if "standard" in tiers:
            results["standard"] = self.analyze_standard(
                fingerprint, analysis_version=analysis_version,
                progress_callback=progress_callback,
            )

        if "live_offline" in tiers:
            results["live_offline"] = self.analyze_live_offline(fingerprint)

        if "deep" in tiers:
            logger.info("Deep tier not yet implemented (Phase 6). Skipping.")

        return results

    def analyze_live_offline(self, fingerprint: str) -> ArrangementFormula:
        """Run the live_offline tier — rebuild from saved Pioneer data.

        Reads the live_pioneer.json sidecar file (written by the live data
        persistence feature) and feeds it through LiveStrataAnalyzer.

        No audio files or hardware connection needed.
        """
        import json

        from .live_analyzer import LiveStrataAnalyzer

        start_time = time.time()
        logger.info("Strata live_offline tier: starting for %s", fingerprint[:16])

        # Look for saved Pioneer data sidecar
        tracks_dir = self._track_store._base_dir
        sidecar_path = tracks_dir / fingerprint / "live_pioneer.json"
        if not sidecar_path.exists():
            raise ValueError(
                f"No saved Pioneer data for {fingerprint[:16]}. "
                "Play the track on Pioneer hardware first to capture live data."
            )

        saved = json.loads(sidecar_path.read_text())
        formula = LiveStrataAnalyzer.build_from_saved_data(fingerprint, saved)
        if formula is None:
            raise ValueError(
                f"Saved Pioneer data for {fingerprint[:16]} is incomplete "
                "(missing phrases or beat grid)."
            )

        formula.compute_time_seconds = round(time.time() - start_time, 4)

        # Save as live_offline tier with pioneer_live source
        self._strata_store.save(formula, "live_offline", source="pioneer_live")
        elapsed = time.time() - start_time
        logger.info(
            "Strata live_offline tier complete: %d sections, %d transitions, %.3fs",
            len(formula.sections), len(formula.transitions), elapsed,
        )
        return formula

    def _compute_energy(self, analysis: TrackAnalysis) -> EnergyAnalysis:
        """Compute energy analysis, loading audio features if needed."""
        if not analysis.downbeats:
            logger.warning("No downbeats available — skipping energy analysis")
            return EnergyAnalysis()

        # We need the raw signal for band energy computation.
        # Load it from the audio file.
        audio_path = Path(analysis.audio_path)
        if not audio_path.exists():
            logger.warning("Audio file not found: %s — skipping energy analysis", audio_path)
            return EnergyAnalysis()

        try:
            import librosa
            signal, sr = librosa.load(str(audio_path), sr=22050, mono=True)

            # Also compute onset strength for density analysis
            onset_strength = librosa.onset.onset_strength(y=signal, sr=sr)

            return compute_energy_analysis(
                signal=signal,
                sr=sr,
                downbeats=analysis.downbeats,
                onset_strength=onset_strength,
                duration=analysis.duration,
            )
        except Exception as e:
            logger.warning("Energy analysis failed: %s", e)
            return EnergyAnalysis()

    def _assemble(
        self,
        fingerprint: str,
        analysis: TrackAnalysis,
        energy: EnergyAnalysis,
        patterns: list[Pattern],
        transitions: list,
        tier: str,
        start_time: float,
    ) -> ArrangementFormula:
        """Assemble all results into an ArrangementFormula."""

        # Build per-section arrangement summaries
        section_arrangements: list[SectionArrangement] = []
        for section in analysis.sections:
            energy_level, energy_trend = compute_section_energy(
                section, energy, analysis.downbeats,
            )

            # Find which patterns are active in this section
            active_patterns: list[str] = []
            for p in patterns:
                for inst in p.instances:
                    # Pattern instance overlaps this section?
                    if inst.start < section.end and inst.end > section.start:
                        if p.id not in active_patterns:
                            active_patterns.append(p.id)

            # Find transitions within this section
            section_transitions = [
                t for t in transitions
                if section.start <= t.timestamp < section.end
            ]

            # Determine active layers from energy pseudo-activity
            active_layers: list[str] = []
            for stem_type, spans in energy.pseudo_activity.items():
                for span in spans:
                    if span.start < section.end and span.end > section.start:
                        if stem_type not in active_layers:
                            active_layers.append(stem_type)
            # Drums are always "active" if we have drum patterns in this section
            if active_patterns and StemType.DRUMS.value not in active_layers:
                active_layers.insert(0, StemType.DRUMS.value)

            section_arrangements.append(SectionArrangement(
                section_label=section.label,
                section_start=section.start,
                section_end=section.end,
                active_layers=active_layers,
                active_patterns=active_patterns,
                transitions=section_transitions,
                energy_level=energy_level,
                energy_trend=energy_trend,
                layer_count=len(active_layers),
            ))

        # Build stems (quick tier: pseudo-stems from energy bands)
        stems: list[StemAnalysis] = []
        for stem_type, spans in energy.pseudo_activity.items():
            stems.append(StemAnalysis(
                stem_type=stem_type,
                activity=spans,
            ))

        # Generate energy narrative
        narrative = _generate_narrative(section_arrangements, patterns, transitions)

        # Compute complexity metric
        pattern_variety = len(set(p.pattern_type for p in patterns)) if patterns else 0
        transition_density = len(transitions) / max(1, len(analysis.sections))
        complexity = min(1.0, (pattern_variety * 0.3 + transition_density * 0.2))

        elapsed = time.time() - start_time

        return ArrangementFormula(
            fingerprint=fingerprint,
            stems=stems,
            patterns=patterns,
            sections=section_arrangements,
            transitions=transitions,
            total_layers=len(stems),
            total_patterns=len(patterns),
            arrangement_complexity=round(complexity, 3),
            energy_narrative=narrative,
            pipeline_tier=tier,
            compute_time_seconds=round(elapsed, 2),
        )


    def _assemble_standard(
        self,
        fingerprint: str,
        analysis: TrackAnalysis,
        stems: list[StemAnalysis],
        patterns: list[Pattern],
        transitions: list,
        energy: EnergyAnalysis,
        start_time: float,
    ) -> ArrangementFormula:
        """Assemble standard tier results into an ArrangementFormula.

        Uses real stem activity data instead of pseudo-activity.
        """
        # Build per-section arrangement summaries using real stem data
        section_arrangements: list[SectionArrangement] = []
        for section in analysis.sections:
            energy_level, energy_trend = compute_section_energy(
                section, energy, analysis.downbeats,
            )

            # Active layers from real stem activity spans
            active_layers: list[str] = []
            for stem in stems:
                for span in stem.activity:
                    if span.start < section.end and span.end > section.start:
                        if stem.stem_type not in active_layers:
                            active_layers.append(stem.stem_type)
                        break

            # Active patterns from per-stem pattern instances
            active_patterns: list[str] = []
            for p in patterns:
                for inst in p.instances:
                    if inst.start < section.end and inst.end > section.start:
                        if p.id not in active_patterns:
                            active_patterns.append(p.id)

            section_transitions = [
                t for t in transitions
                if section.start <= t.timestamp < section.end
            ]

            section_arrangements.append(SectionArrangement(
                section_label=section.label,
                section_start=section.start,
                section_end=section.end,
                active_layers=active_layers,
                active_patterns=active_patterns,
                transitions=section_transitions,
                energy_level=energy_level,
                energy_trend=energy_trend,
                layer_count=len(active_layers),
            ))

        # Generate narrative
        narrative = _generate_narrative(section_arrangements, patterns, transitions)

        # Compute complexity (richer with real stems)
        pattern_variety = len(set(p.pattern_type for p in patterns)) if patterns else 0
        stem_variety = len(set(s.stem_type for s in stems if s.activity))
        transition_density = len(transitions) / max(1, len(analysis.sections))
        complexity = min(1.0, (
            pattern_variety * 0.2
            + stem_variety * 0.2
            + transition_density * 0.15
        ))

        elapsed = time.time() - start_time

        return ArrangementFormula(
            fingerprint=fingerprint,
            stems=stems,
            patterns=patterns,
            sections=section_arrangements,
            transitions=transitions,
            total_layers=len(stems),
            total_patterns=len(patterns),
            arrangement_complexity=round(complexity, 3),
            energy_narrative=narrative,
            pipeline_tier="standard",
            stem_separation_model="htdemucs",
            compute_time_seconds=round(elapsed, 2),
        )


def _merge_transitions(
    cross_stem: list,
    energy_based: list,
    merge_window: float = 2.0,
) -> list:
    """Merge cross-stem and energy-based transitions.

    Cross-stem transitions take priority. Energy-based transitions are
    kept only if they don't overlap (within merge_window seconds) with
    a cross-stem transition.
    """
    merged = list(cross_stem)
    cross_times = {t.timestamp for t in cross_stem}

    for t in energy_based:
        # Keep if no cross-stem transition is within merge_window
        if not any(abs(t.timestamp - ct) < merge_window for ct in cross_times):
            merged.append(t)

    merged.sort(key=lambda t: t.timestamp)
    return merged


def _generate_narrative(
    sections: list[SectionArrangement],
    patterns: list[Pattern],
    transitions: list,
) -> str:
    """Auto-generate a human-readable energy narrative."""
    if not sections:
        return ""

    parts: list[str] = []
    for sec in sections:
        label = sec.section_label.capitalize()

        if sec.transitions:
            descs = [t.description for t in sec.transitions if t.description]
            if descs:
                parts.append(f"{label}: {', '.join(descs)}.")
            else:
                parts.append(f"{label}: {sec.energy_trend} energy.")
        elif sec.active_patterns:
            pattern_names = []
            for pid in sec.active_patterns[:2]:
                for p in patterns:
                    if p.id == pid:
                        pattern_names.append(p.name)
                        break
            if pattern_names:
                parts.append(f"{label}: {' + '.join(pattern_names)}.")
            else:
                parts.append(f"{label}: {sec.energy_trend} energy.")
        else:
            parts.append(f"{label}: {sec.energy_trend} energy.")

    return " ".join(parts)
