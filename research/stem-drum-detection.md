# Stem-Aware Drum Event Detection — Research & Recommendations

**Date:** 2026-03-24
**Context:** SCUE Strata engine produces isolated drum stems via demucs (`htdemucs`). The current M7 percussion detector (`percussion_heuristic.py`) was designed for full-mix signals. This document evaluates approaches for detecting kick, snare, and hi-hat events directly from the isolated drum stem.

---

## 1. Why the Isolated Stem Changes Everything

The current M7 heuristic detector solves a **hard** problem: finding percussion events buried in a full mix with bass, vocals, synths, and reverb. It uses HPSS pre-separation, aggressive onset gating, and conservative thresholds (kick: 0.6, snare: 0.5, hihat: 0.4) to avoid false positives from non-percussive content.

On an isolated demucs drum stem, the problem is **dramatically easier**:

| Challenge | Full Mix | Isolated Stem |
|-----------|----------|---------------|
| Bass guitar/synth masking kick fundamental | Severe | Gone |
| Vocals/melody masking snare body | Severe | Gone |
| Reverb/pads masking hi-hat shimmer | Moderate | Gone |
| Spectral overlap between instruments | Constant | Minimal |
| HPSS required | Yes | No (stem IS the percussive component) |
| False positive rate | High | Very low |

Visual inspection of the drum stem waveform in ArrangementMap confirms this: kick hits appear as clear low-frequency amplitude peaks, snare hits as mid-frequency peaks, and when both are absent, hi-hat patterns emerge as smaller high-frequency peaks.

---

## 2. Feature Analysis: What Works on Isolated Stems

### 2.1 Spectral Centroid — The Single Best Feature

On an isolated drum stem, spectral centroid at each onset is highly discriminative:

| Drum | Centroid Range (Isolated) | Centroid Range (Full Mix) |
|------|--------------------------|--------------------------|
| Kick | 80–400 Hz | 200–800 Hz (pulled up by bass content) |
| Snare | 800–4000 Hz | 1500–5000 Hz (broader, noisier) |
| Hi-hat | 5000–12000+ Hz | Often undetectable |

The gaps between these ranges are **wide** on isolated stems, making simple threshold rules reliable.

### 2.2 Sub-Band Energy Ratios — Best for Simultaneous Hits

Spectral centroid averages across the spectrum, so a simultaneous kick+snare hit gives a blended centroid (~500–1000 Hz) that falls in nobody's range. Sub-band energy ratios solve this by asking three independent questions:

```python
# Recommended bands for isolated EDM drum stems
STEM_BANDS = {
    'kick':  (20, 200),     # fundamental + boom
    'snare': (200, 5000),   # body + snap + wires
    'hihat': (5000, 16000), # metallic shimmer
}
```

These are **narrower and more aggressive** than the current M7 bands:
- M7 `KICK_BAND = (20, 150)` — too narrow, misses kick body at 150–200 Hz
- M7 `SNARE_BAND = (150, 1000)` — too narrow, misses snare snap above 1 kHz
- M7 `HIHAT_BAND = (4000, 16000)` — reasonable, could tighten lower bound to 5 kHz

### 2.3 Zero-Crossing Rate — Hi-Hat Discriminator

Hi-hats produce dramatically higher zero-crossing rates than kicks or snares. On an isolated stem, ZCR at each onset provides a strong secondary feature for hi-hat detection.

### 2.4 Spectral Rolloff — Kick Confirmation

The frequency below which 85% of spectral energy sits. Kicks have rolloff < 300 Hz; snares 1–4 kHz; hi-hats > 5 kHz. Useful as a confidence booster.

---

## 3. Detection Algorithm: Recommended Approach

### 3.1 Multi-Band Onset Detection (Recommended)

Rather than running a single onset detector and then classifying each onset, **run onset detection independently on band-filtered versions of the stem**. This naturally handles simultaneous hits and avoids the classification-after-detection problem entirely.

```python
import librosa
import numpy as np
from scipy.signal import find_peaks

def detect_drum_events_multiband(
    signal: np.ndarray,
    sr: int,
    hop_length: int = 512,
) -> dict[str, list[dict]]:
    """Detect kick, snare, and hi-hat from an isolated drum stem.

    Uses multi-band onset detection: each drum type is detected
    independently in its frequency range, avoiding the classification
    problem entirely.
    """
    n_fft = 2048

    # Compute full STFT once
    S = np.abs(librosa.stft(signal, n_fft=n_fft, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    bands = {
        'kick':  (20, 200),
        'snare': (200, 5000),
        'hihat': (5000, 16000),
    }

    results = {}

    for drum_type, (lo, hi) in bands.items():
        # Extract sub-band spectrogram
        mask = (freqs >= lo) & (freqs < hi)
        S_band = S[mask, :]

        # Onset strength from sub-band spectral flux
        band_flux = np.sum(np.maximum(0, np.diff(S_band, axis=1)), axis=0)
        band_flux = np.concatenate([[0], band_flux])  # pad to original length

        # Normalize
        if band_flux.max() > 0:
            band_flux /= band_flux.max()

        # Adaptive threshold: median + k * std
        threshold = np.median(band_flux) + 1.5 * np.std(band_flux)
        threshold = max(threshold, 0.15)  # floor to avoid noise

        # Peak picking with minimum inter-onset interval
        min_distance = int(sr / hop_length * 0.04)  # 40ms minimum
        peaks, props = find_peaks(
            band_flux,
            height=threshold,
            distance=min_distance,
        )

        onset_times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)
        onset_strengths = props['peak_heights']

        results[drum_type] = [
            {'time': float(t), 'intensity': float(s)}
            for t, s in zip(onset_times, onset_strengths)
        ]

    return results
```

### 3.2 Why Not Single-Onset-Then-Classify?

The current M7 approach (detect all onsets, then classify each) has two problems on isolated stems:

1. **Simultaneous hits are hard to classify.** Kick+snare is common on beats 2 and 4 in EDM. A single onset at that point has blended spectral features that fall between kick and snare thresholds.

2. **Hi-hat is often missed.** The onset detector is dominated by the louder kick/snare transients. Hi-hat peaks are subtle and get filtered out by the onset threshold.

Multi-band detection sidesteps both issues: the kick detector only sees 20–200 Hz energy, so snare content at that same timestamp is invisible to it. The hi-hat detector operates in its own band where kick/snare are absent.

### 3.3 Fallback: Enhanced Single-Pass Approach

If multi-band is too expensive or complex, an improved single-pass approach:

```python
def classify_onset_multi_label(
    signal: np.ndarray,
    sr: int,
    onset_sample: int,
    window: int = 2048,
) -> list[str]:
    """Classify a single onset as one or more drum types.

    Multi-label: returns all drum types present at this onset.
    """
    segment = signal[onset_sample:onset_sample + window]
    if len(segment) < window:
        segment = np.pad(segment, (0, window - len(segment)))

    S = np.abs(np.fft.rfft(segment))
    freqs = np.fft.rfftfreq(window, d=1.0 / sr)

    # Sub-band energies
    low = np.sum(S[(freqs >= 20) & (freqs < 200)] ** 2)
    mid = np.sum(S[(freqs >= 200) & (freqs < 5000)] ** 2)
    high = np.sum(S[(freqs >= 5000) & (freqs < 16000)] ** 2)
    total = low + mid + high + 1e-10

    low_ratio = low / total
    mid_ratio = mid / total
    high_ratio = high / total

    labels = []
    if low_ratio > 0.30:
        labels.append('kick')
    if mid_ratio > 0.25 and low_ratio < 0.70:
        labels.append('snare')
    if high_ratio > 0.30:
        labels.append('hihat')

    return labels if labels else ['unknown']
```

Key difference from M7: **multi-label** (a single onset can be both kick AND snare), not mutually exclusive.

---

## 4. Thresholds for Isolated Stems

### 4.1 Recommended Detection Thresholds

| Parameter | M7 Full-Mix Value | Stem-Aware Value | Rationale |
|-----------|-------------------|------------------|-----------|
| Kick band energy threshold | 0.6 | 0.25–0.35 | No bass competition |
| Snare band energy threshold | 0.5 | 0.20–0.30 | No vocal/melody competition |
| Hi-hat band energy threshold | 0.4 | 0.15–0.25 | No pad/reverb competition |
| Onset strength gate | 0.5 * mean | 0.3 * mean (or remove) | Cleaner signal, less gating needed |
| Min inter-onset interval | Implicit (16th grid) | 40ms (~30ms for hihat) | Sub-beat resolution |

### 4.2 Adaptive Per-Track Thresholds

Different EDM tracks have very different drum balances. A tech house track's kick is much louder relative to its hi-hat than a breakbeat track. Recommended: compute per-band median energy across the first 8 bars and use it to set track-specific thresholds.

```python
def compute_adaptive_thresholds(
    signal: np.ndarray, sr: int, downbeats: list[float],
) -> dict[str, float]:
    """Compute per-track detection thresholds from the first 8 bars."""
    end_time = downbeats[min(8, len(downbeats) - 1)]
    end_sample = int(end_time * sr)
    segment = signal[:end_sample]

    S = np.abs(librosa.stft(segment, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

    thresholds = {}
    for name, (lo, hi) in STEM_BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        band_energy = S[mask, :].mean(axis=0)
        # Threshold = median + 1 std (adaptive to this track)
        thresholds[name] = float(np.median(band_energy) + np.std(band_energy))

    return thresholds
```

---

## 5. Beat-Synchronous vs. Free Onset Detection

### Current M7 Approach: Beat-Synchronous (16th-Note Grid)

The current detector quantizes everything to a 16th-note grid. For each of the 16 slots in a bar, it checks the energy at that grid position. This has advantages:
- Produces clean `DrumPattern` objects compatible with the existing pipeline
- Naturally aligns with EDM's grid-locked production style
- Pattern comparison across bars is trivial

### Recommended: Hybrid Approach

**Detect freely, then snap to grid.**

1. Run multi-band onset detection at full temporal resolution
2. Snap each detected onset to the nearest 16th-note slot
3. Populate `DrumPattern` objects from the snapped onsets
4. Retain the raw onset time and snap error as metadata for confidence scoring

```python
def snap_to_grid(
    onset_time: float,
    downbeats: list[float],
    beats: list[float],
) -> tuple[int, int, float]:
    """Snap an onset to the nearest 16th-note slot.

    Returns:
        (bar_index, slot_index, snap_error_ms)
    """
    if len(beats) < 2:
        return 0, 0, 0.0

    sixteenth = ((beats[-1] - beats[0]) / (len(beats) - 1)) / 4.0

    # Find the bar this onset falls in
    bar_idx = int(np.searchsorted(downbeats, onset_time)) - 1
    bar_idx = max(0, min(bar_idx, len(downbeats) - 1))

    bar_time = downbeats[bar_idx]
    offset = onset_time - bar_time
    slot = round(offset / sixteenth)
    slot = max(0, min(slot, 15))

    snapped_time = bar_time + slot * sixteenth
    snap_error_ms = abs(onset_time - snapped_time) * 1000

    return bar_idx, slot, snap_error_ms
```

Benefits of free-then-snap over pure grid-based:
- Catches ghost notes and flams that fall between grid positions
- The snap error provides a confidence signal (large error = possibly wrong)
- Sub-grid timing information preserved for micro-timing analysis (future feature)

---

## 6. Existing Libraries & Models

### Evaluated Options

| Tool | Approach | Pros | Cons | Recommendation |
|------|----------|------|------|----------------|
| **ADTLib** | TF + madmom CRNN | Dedicated kick/snare/hihat output | TF dependency, last updated 2020, version conflicts | Skip — heavy dependency for marginal gain |
| **ADTOF-pytorch** | PyTorch CRNN | 359hr training data, near state-of-art | PyTorch inference overhead, ~200ms per track | Consider as eval baseline |
| **madmom** | RNN onset/beat | Strong onset detection | No drum-specific transcription, numpy<2.0 requirement | Skip — librosa covers our needs |
| **essentia** | 133 descriptors | Comprehensive features | Heavy dependency, C++ bindings | Skip — overkill |
| **Custom librosa** | Sub-band energy + peaks | No extra dependencies, fast, tunable | Needs manual threshold tuning | **Recommended** |

### Verdict

For SCUE's use case (EDM, already-separated stems, need for speed and minimal dependencies), a custom librosa-based approach is optimal. The isolated stem makes the problem easy enough that ML models add dependency cost without meaningful accuracy gain. Reserve ADTOF-pytorch as an evaluation baseline if we ever need to measure accuracy against a reference.

---

## 7. Integration Plan

### 7.1 Where It Fits in the Pipeline

The stem-aware detector slots into `per_stem.py` → `_detect_drum_events()`, replacing the current approach that wraps the M7 heuristic with lowered thresholds.

```
Current flow:
  per_stem.py → _detect_drum_events()
    → PercussionHeuristicDetector.detect()  # M7 full-mix detector
    → (with lowered thresholds for stem)

Proposed flow:
  per_stem.py → _detect_drum_events()
    → StemDrumDetector.detect()  # NEW: purpose-built for isolated stem
    → Multi-band onset detection
    → Snap to 16th grid → DrumPattern objects
    → Also return raw AtomicEvents with sub-beat timing
```

### 7.2 New Module: `scue/layer1/detectors/percussion_stem.py`

Create a new detector module (not modify `percussion_heuristic.py`) because:
- Different input assumptions (isolated stem vs full mix)
- Different algorithm (multi-band onset vs grid-scan)
- Different thresholds (can't share config sensibly)
- M7 heuristic remains the fallback when stems aren't available

### 7.3 Interface

```python
class StemDrumDetector:
    """Drum event detector optimized for isolated drum stems.

    Uses multi-band onset detection rather than the M7 heuristic's
    beat-synchronous grid scanning. Produces both DrumPattern objects
    (for backward compatibility) and raw AtomicEvents (for richer
    downstream use).
    """

    name: str = "stem_multiband"
    event_types: list[str] = ["kick", "snare", "hihat", "clap"]

    def detect(
        self,
        signal: np.ndarray,
        sr: int,
        beats: list[float],
        downbeats: list[float],
        sections: list,
    ) -> tuple[list[DrumPattern], list[AtomicEvent]]:
        """Detect drum events from an isolated drum stem.

        Returns:
            (patterns, events) — DrumPattern list for pattern analysis,
            AtomicEvent list for arrangement timeline.
        """
        ...
```

Note: this does **not** implement `DetectorProtocol` because it takes a raw signal, not `AudioFeatures`. It's a stem-specific detector, not a general-purpose M7 detector.

### 7.4 Config Extension

Add to `config/detectors.yaml`:

```yaml
stem_percussion:
  # Multi-band onset detection parameters
  bands:
    kick:  [20, 200]
    snare: [200, 5000]
    hihat: [5000, 16000]
  # Relative thresholds (multiplier on median + std)
  sensitivity:
    kick: 1.5    # higher = fewer detections
    snare: 1.5
    hihat: 2.0   # hi-hat needs more filtering
  # Minimum inter-onset interval (ms)
  min_ioi:
    kick: 60
    snare: 60
    hihat: 30
  # Snap tolerance: max ms from grid to accept an onset
  max_snap_error_ms: 25
  # Adaptive threshold window (bars)
  adaptive_window_bars: 8
```

### 7.5 Changes Required

| File | Change |
|------|--------|
| `scue/layer1/detectors/percussion_stem.py` | **NEW** — StemDrumDetector class |
| `scue/layer1/strata/per_stem.py` | Modify `_detect_drum_events()` to use StemDrumDetector instead of PercussionHeuristicDetector |
| `config/detectors.yaml` | Add `stem_percussion` section |
| `tests/test_layer1/test_percussion_stem.py` | **NEW** — unit tests for the stem detector |

No changes to: `percussion_heuristic.py` (preserved as full-mix fallback), `events.py` (DrumPattern/AtomicEvent unchanged), `models.py` (StemAnalysis unchanged).

---

## 8. Expected Improvements

### 8.1 Qualitative

- **Kick detection**: Currently misses kicks when bass synth is heavy (e.g., dubstep). Isolated stem eliminates this entirely.
- **Snare detection**: Currently confuses vocal attacks with snares. Isolated stem eliminates this.
- **Hi-hat detection**: Currently unreliable on full mix (too much spectral overlap). Isolated stem makes hi-hat patterns clearly detectable.
- **Simultaneous hits**: Current mutually-exclusive classification drops the snare when kick+snare co-occur. Multi-label detection catches both.

### 8.2 Quantitative (Expected)

| Metric | M7 Heuristic (Full Mix) | M7 Heuristic (Stem, Current) | Stem Multi-Band (Proposed) |
|--------|------------------------|------------------------------|---------------------------|
| Kick precision | ~70% | ~80% | ~95% |
| Kick recall | ~60% | ~75% | ~95% |
| Snare precision | ~55% | ~65% | ~90% |
| Snare recall | ~50% | ~60% | ~90% |
| Hi-hat detection | Unreliable | Poor (wrong thresholds) | ~85% |
| Simultaneous hit handling | Mutually exclusive | Mutually exclusive | Multi-label |

These are estimates; actual numbers need ground truth annotations (see evaluation plan below).

### 8.3 Performance

The multi-band approach is **faster** than the current stem path because:
- No HPSS needed (stem is already percussive)
- One STFT (shared across bands) vs. M7's sliding-window STFT per slot
- `scipy.signal.find_peaks` is faster than M7's nested bar/slot loop

Expected: < 100ms for a 6-minute drum stem at 22050 Hz.

---

## 9. Evaluation Plan

### 9.1 Ground Truth

Create a small ground truth dataset by manually annotating 2–3 drum stems:
- Use the existing stem at `strata/0c6960e8d9de8cf9272652b54a8cd278316c2964ecc9018918dcf5af4e9bfeed/stems/drums.wav`
- Annotate kick, snare, hi-hat events as `(time, type)` pairs
- Store as JSON in `ground_truth/drum_events/`
- Use the ArrangementMap waveform view to guide annotation (events are visually obvious)

### 9.2 Comparison

Run three detectors on the same stems:
1. **M7 heuristic on full mix** (baseline)
2. **M7 heuristic on isolated stem** (current stem path)
3. **Stem multi-band detector** (proposed)

Measure precision, recall, F1 per drum type with a 50ms tolerance window.

### 9.3 A/B Visualization

Add a toggle in the ArrangementMap view to switch between M7 and stem-detected events, overlaid on the drum stem waveform. This provides immediate visual validation.

---

## 10. Summary of Recommendations

1. **Create `percussion_stem.py`** with a multi-band onset detector
2. **Use sub-band spectral flux** for onset detection, not single-band onset strength
3. **Detect freely, snap to grid** — hybrid approach for DrumPattern compatibility
4. **Multi-label classification** — each onset can be kick AND snare simultaneously
5. **Adaptive per-track thresholds** from first 8 bars of stem energy
6. **No ML dependency** — librosa + scipy.signal.find_peaks is sufficient for isolated EDM stems
7. **Keep M7 heuristic intact** as fallback for non-Strata analysis paths
8. **Build ground truth** from the existing drum stem for evaluation
9. **Recommended frequency bands**: kick 20–200 Hz, snare 200–5000 Hz, hihat 5000–16000 Hz
10. **Expected result**: ~90–95% accuracy on kick/snare, ~85% on hi-hat, with multi-label support for simultaneous hits
