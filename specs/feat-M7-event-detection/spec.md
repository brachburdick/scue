---
status: DRAFT
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
pdr_ref: docs/MILESTONES.md → M7 Event Detection
evidence_ref: research/findings-event-detection-m7.md
---

# Spec: M7 Event Detection (Layer 1A, Tier 2)

## Frozen Intent

### Problem Statement
SCUE's analysis pipeline identifies track sections (Tier 1) but cannot identify individual
musical events within those sections. Without event detection, Layer 2's cue stream is
limited to section-level triggers — no kick-synchronized strobes, no riser-driven build
effects, no snare-timed flashes. M7 fills the `events: list[MusicalEvent]` field that has
been empty since day one.

### Target Users
Brach — DJ using SCUE to generate automated lighting cues. Needs accurate event detection
to drive beat-reactive lighting effects. Also acts as the **tuner** — expects to iterate on
detection algorithms, compare approaches, and adjust thresholds using his own music library.

### Desired Outcome
1. The analysis pipeline populates `TrackAnalysis.events` with detected musical events.
2. Detection algorithms are **pluggable and evaluable** — multiple strategies can be swapped,
   A/B tested, and scored against ground truth.
3. Brach can modify detector configurations, re-run analysis, and compare results.

### Non-Goals
- Arpeggio detection (deferred to M8)
- Real-time event detection from live audio (Layer 0.5 / future milestone)
- Training a production-grade ML model (M7 ships heuristics + RF as competing strategies)
- User-facing event visualization in the Analysis Viewer or Live Deck Monitor (separate feature)
- Modifying the MusicalEvent dataclass shape (already defined)

### Hard Constraints
- Must not break existing analysis pipeline (sections, waveform, features all still work)
- Must not add >3s to total analysis time on M-series Mac
- Percussion stored as compact pattern arrays, not individual MusicalEvent objects
- Hi-hat: pattern-level info only (type, density), not individual hits
- All detectors must be independently toggleable via configuration
- scikit-learn is the only new dependency allowed

### Quality Priorities
1. **Correctness** — false negatives are better than false positives for lighting
2. **Tunability** — easy to adjust thresholds, swap algorithms, measure impact
3. **Performance** — stays within compute budget

## Mutable Specification

### Summary
Add a pluggable event detection framework to Layer 1A's offline analysis pipeline.
Two parallel detection pipelines — percussive (beat-synchronous classification) and
tonal (signal-based detection) — produce MusicalEvent objects that populate
TrackAnalysis.events. A detector eval harness enables A/B comparison of detection
strategies against labeled ground truth.

### User-Facing Behavior
- Running `run_analysis()` on a track now populates the `events` field with detected
  kick, snare, clap, hi-hat pattern, riser, faller, and stab events.
- A new CLI command `python -m scue.layer1.eval_detectors <track_path>` runs all
  configured detector strategies and prints precision/recall/F1 per event type.
- Detector configuration is a YAML file (`config/detectors.yaml`) that specifies which
  strategies are active and their parameters.

### Technical Requirements

#### TR-1: Detector Framework
- `DetectorProtocol`: common interface all detectors implement
- `DetectorConfig`: dataclass loaded from `config/detectors.yaml`, parameterizes each
  detector's algorithm choice, thresholds, and feature requirements
- `DetectorResult`: standardized output (list of events + metadata/confidence scores)
- Detectors receive `AudioFeatures` + `beatgrid` + `sections` and return `DetectorResult`
- **Acceptance:** Two detector strategies for the same event type can be registered and
  run independently, producing comparable results

#### TR-2: Extended Feature Extraction
- Add to `AudioFeatures`: `spectral_flatness`, `spectral_bandwidth`, `y_harmonic`,
  `y_percussive` (HPSS components)
- HPSS runs once, results cached on AudioFeatures for all downstream detectors
- **Acceptance:** `extract_all()` populates new fields; total extraction time <4s for
  a 6-min track on M-series Mac

#### TR-3: Percussive Detection — Heuristic Strategy
- Beat-synchronous slot classification at 16th-note resolution
- Detects: kick, snare, clap, hi-hat pattern (open/closed, density, type)
- Uses sub-band energy, onset strength, spectral centroid, beat position encoding
- Section-aware priors weight confidence by section type
- **Acceptance:** Detects kicks in a 4-on-the-floor EDM track with >80% precision

#### TR-4: Percussive Detection — Random Forest Strategy
- Same slot classification, but uses trained RF model instead of threshold rules
- Model trained on labeled data (heuristic seed, ENST-drums, or manual labels)
- Serialized as `models/drum_classifier.joblib`
- Falls back to heuristic strategy if model file not present
- **Acceptance:** RF strategy can be A/B tested against heuristic via eval harness

#### TR-5: Tonal Event Detection
- **Riser:** spectral centroid slope + R² > 0.7 over ≥2 bars before section boundaries.
  Section priors boost confidence in build sections.
- **Faller:** inverted riser (falling centroid + RMS decay) in post-drop windows.
  Cymbal discrimination via spectral flatness profile.
- **Stab:** HPSS harmonic ratio > 0.3 at onset points + centroid > 500 Hz + duration
  50-200ms. Individual events, grouped by rhythmic regularity in payload.
- **Acceptance:** Risers detected in build→drop transitions with >75% precision

#### TR-6: Compact Pattern Storage
- Percussion events stored as `DrumPattern` objects: bar_range + per-instrument
  16th-note arrays (1/0) per bar pattern
- Runtime expansion to `list[MusicalEvent]` via `expand_patterns()` utility
- Hi-hat stored as pattern metadata: type (8ths/16ths/roll), density, open_ratio
- Tonal events (riser, faller, stab) stored as individual MusicalEvent objects
- **Acceptance:** A track's percussion patterns serialize to <15 KB JSON

#### TR-7: Eval Harness
- Ground truth format: JSON file with labeled events per track (same schema as
  MusicalEvent but with `ground_truth: true` flag)
- Scoring: per-event-type precision, recall, F1 with configurable time tolerance
  (default ±50ms for percussion, ±500ms for tonal events)
- Comparison mode: run N strategies, output side-by-side scores
- **Acceptance:** `eval_detectors` CLI produces a scored comparison table for ≥2
  strategies on a labeled test track

#### TR-8: Detection Tuning Page (Frontend)
- Internal-facing page at `/dev/detectors` — not linked from main nav, accessed directly
- Load a track's analysis, display detected events overlaid on the waveform timeline
- **Waveform + event overlay:** Reuse `WaveformCanvas` component. Render event markers
  on top: kicks as vertical lines, snares/claps as colored markers, risers/fallers as
  shaded regions, stabs as short bars. Color-coded by event type.
- **Section context:** Show section labels as background bands behind the waveform so
  you can see which events land in which sections
- **Per-event-type toggles:** Checkboxes to show/hide each event type independently
- **Confidence filter:** Slider to set minimum confidence threshold — events below the
  threshold fade or hide, so you can see what the detector is confident about vs guessing
- **Stats panel:** Per-event-type counts, density (events/bar), and average confidence
- **Strategy selector:** Dropdown to switch between detection strategies (e.g., heuristic
  vs RF for percussion) — re-fetches or toggles between cached results
- **Acceptance:** Page loads a track's detected events, renders them on the waveform,
  and toggling event types / confidence threshold updates the view immediately

#### TR-9: Pipeline Integration
- New step 8.5 in `analysis.py` between confidence scoring (step 8) and waveform (step 9)
- Loads `DetectorConfig` from `config/detectors.yaml`
- Runs active detectors, merges results, applies section priors, deduplicates
- Populates `TrackAnalysis.events` (tonal events) and a new `TrackAnalysis.drum_patterns`
  field (compact percussion)
- **Acceptance:** `run_analysis()` produces non-empty events for an EDM track

### Interface Definitions

```python
# --- Detector Protocol ---
from typing import Protocol

class DetectorProtocol(Protocol):
    """Interface all event detectors implement."""
    name: str
    event_types: list[str]  # which event types this detector produces

    def detect(
        self,
        features: AudioFeatures,
        beats: list[float],
        downbeats: list[float],
        sections: list[Section],
        config: DetectorConfig,
    ) -> DetectorResult: ...


@dataclass
class DetectorResult:
    """Standardized detector output."""
    events: list[MusicalEvent]
    patterns: list[DrumPattern]  # empty for tonal detectors
    metadata: dict  # detector-specific debug info (thresholds used, timing, etc.)


@dataclass
class DrumPattern:
    """Compact percussion pattern for a range of bars."""
    bar_start: int
    bar_end: int  # exclusive
    kick: list[int]   # 16 slots per bar (1=hit, 0=silent)
    snare: list[int]
    clap: list[int]
    hihat_type: str         # "8ths" | "16ths" | "offbeat" | "roll" | "none"
    hihat_density: float    # 0.0-1.0
    hihat_open_ratio: float # fraction of open vs closed hits


@dataclass
class DetectorConfig:
    """Loaded from config/detectors.yaml."""
    active_strategies: dict[str, str]  # event_type → strategy_name
    params: dict[str, dict]            # strategy_name → {param: value}
    section_priors: dict[str, dict[str, float]]  # event_type → {section_label: weight}
```

```yaml
# config/detectors.yaml
active_strategies:
  percussion: "heuristic"  # or "random_forest"
  riser: "centroid_slope"
  faller: "centroid_slope"
  stab: "hpss_harmonic"

params:
  heuristic:
    kick_low_band_threshold: 0.6
    snare_mid_band_threshold: 0.5
    hihat_high_band_threshold: 0.4
  random_forest:
    model_path: "models/drum_classifier.joblib"
    n_estimators: 150
  centroid_slope:
    min_slope: 50.0
    min_r_squared: 0.7
    min_bars: 2
  hpss_harmonic:
    harmonic_ratio_threshold: 0.3
    min_centroid_hz: 500
    max_duration_ms: 200

section_priors:
  riser:  {build: 1.5, drop: 0.3, breakdown: 0.5, intro: 1.2, verse: 0.5, outro: 0.3}
  faller: {build: 0.2, drop: 1.2, breakdown: 1.5, intro: 0.5, verse: 0.5, outro: 1.0}
  stab:   {build: 0.8, drop: 1.5, breakdown: 0.5, intro: 0.3, verse: 0.5, outro: 0.3}
```

### Layer Boundaries
- **Layer 1A (this feature)** is responsible for: offline event detection, pattern storage,
  eval harness, detector configuration
- **Backend API** is responsible for: `GET /api/tracks/{fingerprint}/events` endpoint that
  returns detected events + drum patterns for a given track. Optional `?strategy=` query
  param to request results from a specific detector strategy.
- **Frontend** is responsible for: `/dev/detectors` tuning page (internal, dev-only)
- **Layer 1B (TrackCursor)** is responsible for: expanding compact patterns into
  `upcoming_events` at playback time (future work, not M7 scope)
- **Layer 2 (Cue Stream)** consumes `TrackCursor.upcoming_events` — no changes needed in M7
- Interface: `TrackAnalysis.events` + `TrackAnalysis.drum_patterns` (new field)

### Edge Cases
- **Track with no beatgrid:** Skip percussion detection entirely (beat-synchronous
  classification requires beats). Tonal detectors still run.
- **Very short track (<30s):** May have no full sections. Tonal detectors use whole-track
  windows. Percussion still classifies at beat positions.
- **Dense mix (layered kicks + bass):** Spectral flatness discriminates kick impulses from
  tonal bass. Expect lower accuracy in heavily layered drops — section priors help.
- **No HPSS available (optional skip):** Stab detection disabled. Percussion and tonal
  detectors still function.
- **RF model file missing:** Graceful fallback to heuristic strategy with log warning.
- **Track already analyzed:** Re-analysis with `force=True` replaces events. Events are
  never merged across analysis runs.

### Open Questions
- None — all design decisions resolved. Implementation details to be refined during build.

### Change Log
<!-- When spec changes during implementation, record the change and its upstream cause. -->
