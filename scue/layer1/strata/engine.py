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

Hybrid tier stages:
  A. Load Pioneer phrases from live_pioneer.json → Section objects
  B. Load track analysis for M7 drum patterns + audio features
  C. Compute per-bar energy from audio (same as quick)
  D. Discover patterns from M7 drum patterns (same as quick)
  E. Detect transitions at Pioneer section boundaries (same as quick)
  F. Assemble ArrangementFormula with Pioneer sections + audio detail
"""

from __future__ import annotations

import gc
import logging
import time
from collections.abc import Callable
from pathlib import Path

from ..models import Section, TrackAnalysis
from ..storage import TrackCache, TrackStore
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
        cache_path: Path | None = None,
    ) -> None:
        self._track_store = TrackStore(tracks_dir)
        self._strata_store = strata_store
        self._priors = priors
        self._cache_path = cache_path

    def analyze_quick(
        self,
        fingerprint: str,
        analysis_version: int | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> ArrangementFormula:
        """Run the quick tier analysis.

        Produces an arrangement formula from existing M7 analysis data
        without stem separation. Self-contained: runs base analysis if needed.

        Args:
            fingerprint: Track fingerprint.
            analysis_version: Specific TrackAnalysis version to use. If None,
                uses load_latest() (highest available version).
            progress_callback: Optional callback for step progress.
        """
        start_time = time.time()
        logger.info("Strata quick tier: starting for %s", fingerprint[:16])

        # Load track analysis (specific version or latest), running base if needed
        signal = None  # Reuse audio signal from base analysis if available
        if analysis_version is not None:
            analysis = self._track_store.load(fingerprint, version=analysis_version)
            if analysis is None:
                raise ValueError(f"No track analysis v{analysis_version} for {fingerprint[:16]}")
        else:
            analysis, ran_base, signal = self._ensure_base_analysis(fingerprint, progress_callback)
            if ran_base:
                logger.info("Base analysis completed for %s, continuing with quick tier", fingerprint[:16])

        # Stage A: Read existing M7 output
        logger.info("  Stage A: Reading M7 detector output")
        # Events and drum_patterns already on the analysis object

        # Stage B: Energy/activity analysis
        logger.info("  Stage B: Computing per-bar energy")
        energy = self._compute_energy(analysis, signal=signal)

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

        # Stage A: Load track analysis (specific version or latest), running base if needed
        _progress(1, "Loading track analysis")
        signal = None  # Reuse audio signal from base analysis if available
        if analysis_version is not None:
            analysis = self._track_store.load(fingerprint, version=analysis_version)
            if analysis is None:
                raise ValueError(f"No track analysis v{analysis_version} for {fingerprint[:16]}")
        else:
            analysis, ran_base, signal = self._ensure_base_analysis(fingerprint, progress_callback)
            if ran_base:
                logger.info("Base analysis completed for %s, continuing with standard tier", fingerprint[:16])

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
        energy = self._compute_energy(analysis, signal=signal)
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
            results["quick"] = self.analyze_quick(
                fingerprint, analysis_version=analysis_version,
                progress_callback=progress_callback,
            )

        if "standard" in tiers:
            results["standard"] = self.analyze_standard(
                fingerprint, analysis_version=analysis_version,
                progress_callback=progress_callback,
            )

        if "hybrid" in tiers:
            results["hybrid"] = self.analyze_hybrid(fingerprint, analysis_version=analysis_version)

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
        tracks_dir = self._track_store.tracks_dir
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

    def analyze_hybrid(
        self, fingerprint: str, analysis_version: int | None = None,
    ) -> ArrangementFormula:
        """Run the hybrid tier: Pioneer sections + audio energy/patterns.

        Uses Pioneer phrase analysis for section boundaries (high confidence,
        DJ-verified structure) combined with audio-derived energy analysis,
        drum pattern discovery, and transition detection from the quick tier.

        Requires both:
          - A TrackAnalysis with audio path + M7 output
          - A live_pioneer.json sidecar with phrase analysis + beat grid
        """
        import json

        from .live_analyzer import PHRASE_KIND_MAP, _beat_to_bar

        start_time = time.time()
        logger.info("Strata hybrid tier: starting for %s", fingerprint[:16])

        # --- Load Pioneer sidecar data ---
        tracks_dir = self._track_store.tracks_dir
        sidecar_path = tracks_dir / fingerprint / "live_pioneer.json"
        if not sidecar_path.exists():
            raise ValueError(
                f"No saved Pioneer data for {fingerprint[:16]}. "
                "Hybrid tier requires Pioneer phrase analysis."
            )
        saved = json.loads(sidecar_path.read_text())
        phrases = saved.get("phrases", [])
        beat_grid = saved.get("beat_grid", [])
        if not phrases or not beat_grid:
            raise ValueError(
                f"Pioneer data for {fingerprint[:16]} missing phrases or beat grid."
            )

        # --- Beat-to-time conversion ---
        # ANLZ beatgrids have beat_number cycling 1,3,1,3 (positional, not
        # absolute). Live bridge beatgrids have monotonically increasing
        # beat_number. Detect format and choose conversion strategy.
        # ANLZ beatgrids cycle beat_number (e.g., 1,3,1,3 — beat within bar).
        # Live bridge beatgrids have strictly increasing beat_number.
        # Detect ANLZ by checking if beat_numbers are NOT monotonically increasing.
        bg_beats = [bg["beat_number"] for bg in beat_grid[:6]]
        is_anlz_format = len(bg_beats) >= 4 and not all(
            bg_beats[i] < bg_beats[i + 1] for i in range(min(3, len(bg_beats) - 1))
        )

        if is_anlz_format:
            # ANLZ format: use BPM arithmetic from first entry
            bpm = beat_grid[0].get("bpm", 120.0)
            first_time_ms = beat_grid[0].get("time_ms", 0.0)
            beat_duration_s = 60.0 / bpm if bpm > 0 else 0.5

            def _beat_to_s(beat: int) -> float:
                return first_time_ms / 1000.0 + (beat - 1) * beat_duration_s
        else:
            # Live bridge format: interpolate from absolute beat grid
            from .live_analyzer import _beat_to_time_s
            def _beat_to_s(beat: int) -> float:
                return _beat_to_time_s(beat, beat_grid)

        # --- Stage A: Convert Pioneer phrases → Section objects ---
        logger.info("  Stage A: Building sections from Pioneer phrases")
        pioneer_sections: list[Section] = []
        for phrase in phrases:
            start_beat = phrase["start_beat"]
            end_beat = phrase["end_beat"]
            kind_raw = str(phrase.get("kind", "")).lower().strip()
            label = PHRASE_KIND_MAP.get(kind_raw, kind_raw or "unknown")

            start_s = _beat_to_s(start_beat)
            end_s = _beat_to_s(end_beat) if end_beat > 0 else saved.get("duration", 0.0)
            # Clamp to track duration
            track_dur = saved.get("duration", 0.0)
            if track_dur > 0:
                start_s = max(0.0, min(start_s, track_dur))
                end_s = max(start_s, min(end_s, track_dur))
            bar_start = _beat_to_bar(start_beat)
            bar_end = _beat_to_bar(end_beat) if end_beat > 0 else bar_start

            pioneer_sections.append(Section(
                label=label,
                start=start_s,
                end=end_s,
                confidence=0.85,
                bar_count=bar_end - bar_start,
                expected_bar_count=bar_end - bar_start,
                source="pioneer_phrases",
            ))

        # --- Stage B: Load TrackAnalysis for audio features + M7 ---
        logger.info("  Stage B: Loading track analysis for audio features")
        signal = None  # Reuse audio signal from base analysis if available
        if analysis_version is not None:
            analysis = self._track_store.load(fingerprint, version=analysis_version)
            if analysis is None:
                raise ValueError(f"No track analysis v{analysis_version} for {fingerprint[:16]}")
        else:
            analysis, ran_base, signal = self._ensure_base_analysis(fingerprint)
            if ran_base:
                logger.info("Base analysis completed for %s, continuing with hybrid tier", fingerprint[:16])

        # --- Stage C: Energy analysis from audio ---
        logger.info("  Stage C: Computing per-bar energy from audio")
        energy = self._compute_energy(analysis, signal=signal)

        # --- Stage D: Pattern discovery from M7 drum patterns ---
        logger.info("  Stage D: Discovering patterns from M7 output")
        patterns = discover_patterns(
            analysis.drum_patterns,
            analysis.downbeats,
            analysis.beats,
        )

        # --- Stage E: Transition detection at Pioneer section boundaries ---
        logger.info("  Stage E: Detecting transitions at Pioneer boundaries")
        transitions = detect_transitions(
            pioneer_sections,
            energy,
            analysis.downbeats,
        )

        # --- Stage F: Assembly (Pioneer sections + audio detail) ---
        logger.info("  Stage F: Assembling hybrid formula")

        # Temporarily swap analysis.sections with Pioneer sections for assembly
        original_sections = analysis.sections
        analysis.sections = pioneer_sections
        formula = self._assemble(
            fingerprint=fingerprint,
            analysis=analysis,
            energy=energy,
            patterns=patterns,
            transitions=transitions,
            tier="hybrid",
            start_time=start_time,
        )
        analysis.sections = original_sections  # Restore

        formula.analysis_source = "pioneer_sections+audio_detail"
        self._strata_store.save(formula, "hybrid", source="pioneer_live")
        elapsed = time.time() - start_time
        logger.info(
            "Strata hybrid tier complete: %d sections, %d patterns, %d transitions, %.1fs",
            len(pioneer_sections), len(patterns), len(transitions), elapsed,
        )
        return formula

    def _ensure_base_analysis(
        self,
        fingerprint: str,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> tuple[TrackAnalysis, bool, "np.ndarray | None"]:
        """Load TrackAnalysis, running base analysis first if version===0.

        Returns (analysis, ran_base, signal):
          - ran_base=True means base was just computed.
          - signal is the decoded audio waveform when base analysis ran
            (avoids redundant librosa.load in downstream energy computation).
            None when existing analysis was found.
        """
        import numpy as np  # noqa: F811 — type hint in signature

        analysis = self._track_store.load_latest(fingerprint)
        if analysis is not None and analysis.version > 0:
            return analysis, False, None

        # Need base analysis — resolve audio path
        audio_path = self._resolve_audio_path(fingerprint, analysis)
        logger.info("Running base analysis for %s (no existing analysis)", fingerprint[:16])

        from ..analysis import run_analysis

        def _base_progress(step: int, name: str, total: int) -> None:
            if progress_callback is not None:
                progress_callback(step, name)

        result, features = run_analysis(
            audio_path=audio_path,
            tracks_dir=self._track_store.tracks_dir,
            cache_path=self._cache_path,
            skip_waveform=True,  # Strata doesn't use waveform data
            progress_callback=_base_progress,
            return_features=True,
        )
        # Extract signal before gc — energy analysis needs it
        signal = features.signal if features is not None else None
        gc.collect()  # OOM prevention after heavy analysis
        return result, True, signal

    def _resolve_audio_path(self, fingerprint: str, analysis: TrackAnalysis | None) -> Path:
        """Get audio_path from TrackAnalysis or SQLite cache."""
        if analysis and analysis.audio_path:
            p = Path(analysis.audio_path)
            if p.exists():
                return p
        # Fall back to SQLite cache lookup
        if self._cache_path:
            cache = TrackCache(self._cache_path)
            meta = cache.get_track(fingerprint)
            if meta and meta.get("audio_path"):
                p = Path(meta["audio_path"])
                if p.exists():
                    return p
        raise ValueError(f"No audio file found for {fingerprint[:16]}")

    def _compute_energy(
        self,
        analysis: TrackAnalysis,
        signal: "np.ndarray | None" = None,
    ) -> EnergyAnalysis:
        """Compute energy analysis, loading audio features if needed.

        Args:
            analysis: TrackAnalysis with downbeats and audio_path.
            signal: Pre-loaded audio waveform (mono, sr=22050). When provided,
                skips the redundant librosa.load() from disk.

        Tries the feature cache first for onset_strength, falling back to
        loading audio from disk.
        """
        import numpy as np  # noqa: F811

        if not analysis.downbeats:
            logger.warning("No downbeats available — skipping energy analysis")
            return EnergyAnalysis()

        sr = 22050  # Standard sample rate used throughout the pipeline

        # Try feature cache for onset_strength
        from ..feature_cache import load_features
        cached = load_features(analysis.fingerprint, self._track_store.tracks_dir)
        if cached is not None and cached.onset_strength is not None:
            logger.info("Using cached onset_strength for energy analysis")
            # Need raw signal for band energy — reuse if provided
            if signal is None:
                audio_path = Path(analysis.audio_path)
                if not audio_path.exists():
                    logger.warning("Audio file not found: %s — skipping energy analysis", audio_path)
                    return EnergyAnalysis()
                try:
                    import librosa
                    signal, sr = librosa.load(str(audio_path), sr=sr, mono=True)
                except Exception as e:
                    logger.warning("Failed to load audio for energy: %s", e)
                    return EnergyAnalysis()
            else:
                logger.info("Reusing pre-loaded signal for energy analysis")
            try:
                return compute_energy_analysis(
                    signal=signal,
                    sr=sr,
                    downbeats=analysis.downbeats,
                    onset_strength=cached.onset_strength,
                    duration=analysis.duration,
                )
            except Exception as e:
                logger.warning("Energy analysis failed: %s", e)
                return EnergyAnalysis()

        # No cache — need signal + onset_strength
        if signal is None:
            audio_path = Path(analysis.audio_path)
            if not audio_path.exists():
                logger.warning("Audio file not found: %s — skipping energy analysis", audio_path)
                return EnergyAnalysis()
            try:
                import librosa
                signal, sr = librosa.load(str(audio_path), sr=sr, mono=True)
            except Exception as e:
                logger.warning("Failed to load audio for energy: %s", e)
                return EnergyAnalysis()
        else:
            logger.info("Reusing pre-loaded signal for energy analysis")

        try:
            import librosa
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
