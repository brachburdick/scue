# Skill: Waveform Rendering & Frequency Visualization

> **When to use:** Any task involving RGB waveform computation, frequency-to-color mapping, amplitude scaling, perceptual weighting, or waveform display tuning. Covers both backend (analysis-time) and frontend (render-time) concerns.

---

## Why This Skill Exists

Achieving Pioneer-quality waveform display requires understanding psychoacoustics, not just signal processing. Naive FFT-to-color mapping produces bass-dominated, "bricked out" waveforms. This skill documents the domain knowledge needed to produce visually informative frequency-colored waveforms.

## The Core Problem

Bass frequencies carry far more physical energy than mids/highs in virtually all music (1/f spectral profile). Without compensation, a raw 3-band energy display is always red/bass-colored because:

1. **Energy distribution:** A kick drum at 80 Hz produces ~20-40 dB more energy than a hi-hat at 10 kHz, even though both sound equally prominent to the ear.
2. **Fletcher-Munson curves:** Human hearing is least sensitive at low frequencies. A 50 Hz tone needs ~30 dB more SPL than a 3 kHz tone to sound equally loud at moderate listening levels.
3. **Linear FFT bins:** An FFT with uniform frequency spacing gives the bass band fewer bins but each bin carries more energy density.

Pioneer solves this with **per-band independent normalization** and **compressed amplitude ranges** in their ANLZ waveform data. SCUE must apply similar compensation.

## Key Concepts

### Perceptual Frequency Weighting

| Weighting | When to Use | Characteristic |
|---|---|---|
| **A-weighting** | Low-SPL approximation | -30 dB at 50 Hz, boost at 2-4 kHz |
| **K-weighting** | Modern loudness (LUFS/ITU-R BS.1770) | +4 dB shelf above 1.5 kHz, high-pass below 100 Hz |
| **Pink noise tilt** | Spectrum analyzer correction | +3 dB/octave compensates 1/f rolloff |

For DJ waveforms, **K-weighting** or **pink noise tilt** are the most relevant. A-weighting over-attenuates bass for this use case.

### Amplitude Compression

| Method | Formula | Effect |
|---|---|---|
| **Linear** | `h = amplitude` | Loud sections brick out, quiet detail invisible |
| **Square root** | `h = amplitude^0.5` | Moderate compression, common compromise |
| **Power/gamma** | `h = amplitude^gamma` (0.3-0.7) | Tunable compression |
| **Logarithmic** | `h = log(1 + gamma*v) / log(1 + gamma)` | Maximum detail, quiet sections visible |

### Normalization Strategies

| Strategy | Behavior | Trade-off |
|---|---|---|
| **Global max** (current SCUE) | All bands share one max | Preserves absolute balance; bass dominates visually |
| **Per-band independent** (Pioneer) | Each band scaled to own peak | All bands visible; loses absolute cross-band comparison |
| **Per-band with weighting** | Apply frequency weighting, then per-band normalize | Best perceptual accuracy; most complex |
| **Percentile-based** | Normalize to 95th percentile instead of max | Avoids single-peak spikes dominating |

### Color Mapping Modes

| Mode | Low | Mid | High | Notes |
|---|---|---|---|---|
| **Pioneer RGB** | Red | Green | Blue | Standard; color = freq ratio, height = amplitude |
| **Pioneer 3-Band** | Dark blue | Amber | White | Painter's algorithm overlap rendering |
| **Serato** | Red | Green | Blue | Same as Pioneer RGB |
| **BLUE/Mono** | Dark blue | — | White | Brightness = spectral centroid |

## SCUE Waveform Pipeline

### Backend (`scue/layer1/waveform.py`)

```
Audio signal → STFT (n_fft=2048) → 3-band RMS → resample to 150 FPS → global normalize → RGBWaveform
```

Current band boundaries: LOW 20-200 Hz, MID 200-2500 Hz, HIGH 2500-Nyquist.

**Where compensation should be applied:**
- After RMS computation, before normalization: apply per-band gain (frequency weighting)
- After normalization: apply amplitude compression (gamma/log curve)
- Alternative: switch from global to per-band normalization

### Frontend (`frontend/src/components/shared/WaveformCanvas.tsx`)

```
RGBWaveform data → blendColor(low, mid, high) → amplitude = max(l,m,h), color = ratio → draw bars
```

**Where compensation should be applied:**
- In `blendColor()`: apply per-channel gain multipliers before computing amplitude/color
- Bar height calculation: apply gamma/compression curve to amplitude before scaling to pixels
- Optional: add minimum brightness floor per channel

### Pioneer ANLZ Data (for reference comparison)

- **PWV5** (RGB detail): 2 bytes per entry. 3 bits R + 3 bits G + 3 bits B + 5 bits height. 150 entries/sec.
- **PWV7** (3-band detail): 3 bytes per entry. Mid, High, Low (byte order). 150 entries/sec.
- Pioneer performs per-band normalization during rekordbox analysis, not at render time.

## Gotchas

- **Global normalization preserves imbalance:** The current SCUE approach (all bands share one max) means if bass is the loudest band (common in EDM), it dominates the entire track's color. This is technically "correct" but visually uninformative.
- **Per-band normalization loses cross-band truth:** If you normalize each band independently, a quiet hi-hat pattern looks as tall as a booming kick. The trade-off is visual information density vs physical accuracy.
- **Gamma affects color perception:** Applying gamma to amplitude after color computation changes the perceived saturation. Apply gamma to the final bar height, not to individual channels, to preserve color ratios.
- **Frontend-only vs backend changes:** Frontend-only tweaks (gain multipliers, gamma) are instant but don't change stored data. Backend changes (weighting, normalization) require re-analysis of all tracks.
- **Pioneer comparison requires Pioneer data:** To compare SCUE rendering against Pioneer, load the same track's PWV5/PWV7 data from USB ANLZ files. The API endpoint `GET /api/tracks/{fp}/pioneer-waveform` provides this.

## Reference Research

Full findings: `research/findings-waveform-frequency-color-rendering.md`

## Files

| File | Role |
|---|---|
| `scue/layer1/waveform.py` | Backend: 3-band RMS computation + normalization |
| `scue/layer1/models.py` | `RGBWaveform` dataclass |
| `scue/api/waveform_presets.py` | Backend: preset CRUD API (6 endpoints, YAML storage) |
| `config/waveform-presets.yaml` | Preset storage (4 seed presets) |
| `frontend/src/components/shared/WaveformCanvas.tsx` | Frontend: canvas rendering + color blending + `renderParams` pipeline |
| `frontend/src/components/shared/drawBeatgridLines.ts` | Beatgrid overlay |
| `frontend/src/components/live/DeckWaveform.tsx` | Live playback waveform wrapper (reads active preset) |
| `frontend/src/components/analysis/AnalysisViewer.tsx` | Analysis page waveform integration (reads active preset) |
| `frontend/src/pages/WaveformTuningPage.tsx` | Dev page: real-time parameter tuning at `/dev/waveforms` |
| `frontend/src/components/waveformTuning/ParameterControls.tsx` | 3-group parameter sliders/dropdowns/pickers |
| `frontend/src/components/waveformTuning/PresetBar.tsx` | Preset management (save/save-as/load/activate/delete) |
| `frontend/src/components/waveformTuning/PioneerReferenceWaveform.tsx` | Pioneer ANLZ PWV5 reference renderer |
| `frontend/src/stores/waveformPresetStore.ts` | Zustand store: presets, activePreset, draftParams |
| `frontend/src/api/waveformPresets.ts` | TanStack Query hooks for preset API |
| `frontend/src/types/waveformPreset.ts` | `WaveformRenderParams`, `WaveformPreset` types |
| `docs/DECISIONS.md` | ADR-018 (Pioneer-accurate RGB rendering), ADR-019 (preset system) |
