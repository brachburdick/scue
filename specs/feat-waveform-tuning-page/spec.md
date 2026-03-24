# Spec: Waveform Rendering Tuning Page

## Summary

A dev-facing page for real-time tuning of waveform rendering parameters. Displays the same track's waveform rendered with adjustable frequency weighting, amplitude compression, normalization strategy, and color mapping — with live preview as sliders change. Supports saving named presets, selecting an active preset for app-wide use, and A/B comparison against Pioneer ANLZ waveform data when available.

Route: `/dev/waveforms`
Sidebar: "Waveforms" entry under the "Dev" section header (alongside existing "Detectors" entry).

---

## Motivation

SCUE's current waveform rendering uses global normalization and linear amplitude scaling. This produces bass-dominated, "bricked out" displays on EDM tracks — low frequencies over-represent because they carry more physical energy. Pioneer hardware compensates for this with per-band normalization and compressed amplitude ranges, producing waveforms with much higher color and amplitude fidelity.

Rather than guess at the right compensation parameters, this page lets the operator visually tune rendering in real time, compare against Pioneer reference data, and save presets that are applied across the entire application.

---

## User-Facing Behavior

1. Operator navigates to `/dev/waveforms` and selects a track from the track picker.
2. The page loads the track's `RGBWaveform` data (and Pioneer ANLZ waveform if available).
3. A large waveform canvas renders the track using the currently active preset's parameters.
4. Below the waveform, a control panel exposes all tunable parameters as sliders, dropdowns, and toggles.
5. Changes to any parameter immediately re-render the waveform (no save required for preview).
6. A preset management bar lets the operator: save current settings as a named preset, load a saved preset, rename/delete presets, and designate one preset as "active" (applied app-wide).
7. When Pioneer ANLZ data is available for the selected track, a reference waveform renders below the tunable one for visual comparison.

---

## Page Layout

```
+----------------------------------------------------------+
| Track Picker (mini table — title, artist, BPM, key, dur) |
+----------------------------------------------------------+
| Preset Bar: [Active: "Pioneer Match v2"] [Save] [Save As] [Presets v] |
+----------------------------------------------------------+
| Main Waveform Canvas (zoomable, scrollable)              |
| [rendered with current parameter values]                  |
+----------------------------------------------------------+
| Pioneer Reference Waveform (if ANLZ data available)      |
| [rendered from PWV5/PWV7 data, read-only]                |
+----------------------------------------------------------+
| Parameter Controls                                        |
| +------------------+------------------+----------------+  |
| | Frequency        | Amplitude        | Color          |  |
| | Weighting        | Scaling          | Mapping        |  |
| +------------------+------------------+----------------+  |
+----------------------------------------------------------+
```

- **Top:** Track picker (reuse existing mini track table component).
- **Preset bar:** Shows active preset name, save/save-as buttons, preset dropdown.
- **Main waveform:** Full-width, zoomable/scrollable. Renders using current parameter values. Same interaction as AnalysisViewer waveform (scroll, zoom, click for position).
- **Reference waveform:** Shown only when Pioneer data exists. Half-height. Rendered from raw ANLZ PWV5 or PWV7 bytes. Scroll/zoom is synced with main waveform.
- **Controls:** Three-column grid of parameter groups.

On narrower screens, controls stack vertically.

---

## Tunable Parameters

All parameters below should be exposed in the control panel. Default values match current SCUE behavior (so the page launches showing the existing rendering).

### Group 1: Frequency Band Weighting

These control how much each frequency band contributes relative to the others.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `normalization` | dropdown | `global` / `per_band` / `weighted` | `global` | How bands are normalized relative to each other |
| `lowGain` | slider | 0.0 – 3.0 | 1.0 | Gain multiplier applied to low band before rendering |
| `midGain` | slider | 0.0 – 3.0 | 1.0 | Gain multiplier applied to mid band before rendering |
| `highGain` | slider | 0.0 – 3.0 | 1.0 | Gain multiplier applied to high band before rendering |
| `frequencyWeighting` | dropdown | `none` / `a_weight` / `k_weight` / `pink_tilt` | `none` | Perceptual weighting curve applied to band energies |
| `lowCrossover` | slider | 80 – 500 Hz | 200 Hz | Low/mid crossover frequency |
| `highCrossover` | slider | 1000 – 8000 Hz | 2500 Hz | Mid/high crossover frequency |

**Note on crossover sliders:** These affect the *backend* analysis, not just rendering. Changing crossovers requires re-analysis. The UI should indicate this with a "Re-analyze required" badge when crossovers differ from the stored waveform's analysis parameters. For the initial implementation, crossover sliders preview an *approximation* (re-weighting existing band data) but accurate results require re-analysis.

### Group 2: Amplitude Scaling

These control how amplitude maps to bar height.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `amplitudeScale` | dropdown | `linear` / `sqrt` / `log` / `gamma` | `linear` | Amplitude-to-height mapping function |
| `gamma` | slider | 0.1 – 1.0 | 1.0 | Exponent for gamma scaling (only shown when `amplitudeScale` = `gamma`) |
| `logStrength` | slider | 1 – 100 | 10 | Compression strength for log scaling (only shown when `amplitudeScale` = `log`) |
| `noiseFloor` | slider | 0.0 – 0.1 | 0.001 | Minimum amplitude threshold; values below this are not rendered |
| `peakNormalize` | toggle | on/off | on | Normalize so the loudest point fills the canvas height |

### Group 3: Color Mapping

These control how frequency ratios map to visible colors.

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `colorMode` | dropdown | `rgb_blend` / `three_band_overlap` / `mono_blue` | `rgb_blend` | Color rendering strategy |
| `lowColor` | color picker | any RGB | `#ff0000` (red) | Base color for low frequency band |
| `midColor` | color picker | any RGB | `#00ff00` (green) | Base color for mid frequency band |
| `highColor` | color picker | any RGB | `#0000ff` (blue) | Base color for high frequency band |
| `saturation` | slider | 0.0 – 2.0 | 1.0 | Color saturation multiplier |
| `brightness` | slider | 0.0 – 2.0 | 1.0 | Overall brightness multiplier |
| `minBrightness` | slider | 0.0 – 0.3 | 0.0 | Minimum brightness floor per band (prevents a band from being invisible) |

---

## Preset System

### Data Model

```typescript
interface WaveformPreset {
  id: string;              // UUID
  name: string;            // User-assigned name
  isActive: boolean;       // One preset is active at a time
  createdAt: string;       // ISO timestamp
  updatedAt: string;       // ISO timestamp
  params: WaveformRenderParams;
}

interface WaveformRenderParams {
  // Frequency
  normalization: "global" | "per_band" | "weighted";
  lowGain: number;
  midGain: number;
  highGain: number;
  frequencyWeighting: "none" | "a_weight" | "k_weight" | "pink_tilt";
  lowCrossover: number;
  highCrossover: number;

  // Amplitude
  amplitudeScale: "linear" | "sqrt" | "log" | "gamma";
  gamma: number;
  logStrength: number;
  noiseFloor: number;
  peakNormalize: boolean;

  // Color
  colorMode: "rgb_blend" | "three_band_overlap" | "mono_blue";
  lowColor: string;     // hex
  midColor: string;     // hex
  highColor: string;    // hex
  saturation: number;
  brightness: number;
  minBrightness: number;
}
```

### Storage

Presets are stored as a YAML file at `config/waveform-presets.yaml`. The backend serves them via REST endpoints. This follows SCUE's convention of YAML for all configuration.

```yaml
active_preset: "pioneer-match-v1"
presets:
  - id: "default"
    name: "SCUE Default"
    params:
      normalization: global
      lowGain: 1.0
      midGain: 1.0
      highGain: 1.0
      # ... all params at defaults
  - id: "pioneer-match-v1"
    name: "Pioneer Match v1"
    params:
      normalization: per_band
      lowGain: 0.6
      midGain: 1.0
      highGain: 1.4
      amplitudeScale: sqrt
      # ... tuned values
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/waveform-presets` | List all presets, with active flag |
| `GET` | `/api/waveform-presets/active` | Get the currently active preset |
| `PUT` | `/api/waveform-presets/{id}` | Update a preset's params or name |
| `POST` | `/api/waveform-presets` | Create a new preset |
| `DELETE` | `/api/waveform-presets/{id}` | Delete a preset (cannot delete active) |
| `POST` | `/api/waveform-presets/{id}/activate` | Set a preset as active |

### App-Wide Application

When a preset is marked active, all waveform rendering in the app (AnalysisViewer, DeckWaveform, DetectorTuningPage) reads the active preset's `WaveformRenderParams` and applies them during rendering. This is a frontend concern — the params are fetched once on app load and cached in a Zustand store (`waveformPresetStore`). Changes to the active preset trigger re-renders across all mounted waveform components.

---

## Component Hierarchy

```
WaveformTuningPage
  TrackPicker (reuse existing)
  PresetBar
    ActivePresetLabel
    SaveButton
    SaveAsButton (opens name dialog)
    PresetDropdown (list all, select to load)
    DeleteButton
  WaveformCanvas (main — receives current params)
  PioneerReferenceWaveform (conditional — rendered from ANLZ data)
  ParameterControls
    FrequencyWeightingPanel
      NormalizationDropdown
      GainSliders (low/mid/high)
      FrequencyWeightingDropdown
      CrossoverSliders (low/high)
    AmplitudeScalingPanel
      ScaleDropdown
      GammaSlider (conditional)
      LogStrengthSlider (conditional)
      NoiseFloorSlider
      PeakNormalizeToggle
    ColorMappingPanel
      ColorModeDropdown
      ColorPickers (low/mid/high)
      SaturationSlider
      BrightnessSlider
      MinBrightnessSlider
```

---

## Pioneer Reference Waveform

When the selected track has Pioneer ANLZ data (from USB scan), the reference waveform section appears. It fetches `GET /api/tracks/{fp}/pioneer-waveform` and renders the PWV5 (color detail) or PWV7 (3-band detail) data directly — no SCUE processing. This provides a ground-truth comparison target.

The reference waveform:
- Is read-only (no parameter controls).
- Scroll/zoom is synced with the main waveform (same viewStart/viewEnd).
- Is half the height of the main waveform.
- Shows a label: "Pioneer Reference (PWV5)" or "Pioneer Reference (PWV7)".
- Is hidden when no Pioneer data exists for the track (with a note: "No Pioneer ANLZ data — analyze from USB to enable comparison").

---

## Rendering Pipeline (Modified WaveformCanvas)

The tuning page needs a modified rendering path in `WaveformCanvas` (or a wrapper) that accepts `WaveformRenderParams` and applies them:

```
For each sample/pixel:
  1. Read raw low/mid/high values from RGBWaveform
  2. Apply per-band gain multipliers (lowGain, midGain, highGain)
  3. Apply frequency weighting curve (if not "none")
  4. Apply normalization strategy (global, per_band, or weighted)
  5. Compute amplitude:
     - rgb_blend: amplitude = max(low, mid, high)
     - three_band_overlap: each band has independent height
  6. Apply amplitude scaling (linear/sqrt/log/gamma)
  7. Apply noise floor threshold
  8. Compute color based on colorMode:
     - rgb_blend: R=low/amp, G=mid/amp, B=high/amp (current approach)
     - three_band_overlap: draw 3 layers with band-specific colors
     - mono_blue: brightness from spectral centroid
  9. Apply saturation, brightness, minBrightness adjustments
  10. Draw bar
```

Steps 2-4 and 6-9 are the new additions relative to the current rendering path.

**Important:** The render params are applied at render time in the frontend. The stored `RGBWaveform` data is not modified. This means all parameter changes are instant and don't require re-analysis — except crossover frequency changes, which affect the backend STFT band splitting.

---

## State Management

New Zustand store: `waveformPresetStore`

```typescript
interface WaveformPresetStore {
  presets: WaveformPreset[];
  activePreset: WaveformPreset | null;

  // For tuning page only
  draftParams: WaveformRenderParams | null;  // Unsaved changes
  isDirty: boolean;

  // Actions
  fetchPresets: () => Promise<void>;
  setDraftParams: (params: Partial<WaveformRenderParams>) => void;
  savePreset: (id: string) => Promise<void>;
  saveAsNewPreset: (name: string) => Promise<void>;
  activatePreset: (id: string) => Promise<void>;
  deletePreset: (id: string) => Promise<void>;
  resetDraft: () => void;
}
```

The `draftParams` field holds unsaved changes on the tuning page. The main waveform renders using `draftParams` (if set) falling back to `activePreset.params`. Other pages always use `activePreset.params`.

---

## Interactions

| Action | Behavior |
|---|---|
| Adjust any slider/dropdown | Immediately updates `draftParams`; waveform re-renders. Preset bar shows "unsaved" indicator. |
| Click "Save" | Writes `draftParams` to the current preset via `PUT /api/waveform-presets/{id}`. Clears dirty flag. |
| Click "Save As" | Opens a name input dialog. Creates new preset via `POST`. The new preset becomes active. |
| Select preset from dropdown | Loads that preset's params into `draftParams`. Does NOT activate it (activation is explicit). |
| Click "Activate" on a preset | Sets it as the app-wide active preset. All waveform components re-render. |
| Click "Delete" on a preset | Confirms, then deletes. Cannot delete the active preset. |
| Change track in picker | Reloads waveform data; re-renders with current `draftParams`. Also fetches Pioneer data. |
| Scroll/zoom main waveform | Reference waveform follows (synced viewport). |
| Double-click main waveform | Resets zoom to full track view (existing behavior). |

---

## Seed Presets

The initial `config/waveform-presets.yaml` ships with these presets:

1. **SCUE Default** — All parameters at their defaults (current behavior). Serves as baseline.
2. **Pioneer RGB Match** — Per-band normalization, sqrt amplitude, low gain reduced to ~0.6, high gain boosted to ~1.4. Approximates Pioneer RGB mode appearance.
3. **Pioneer 3-Band** — Three-band overlap color mode, per-band normalization, Pioneer 3-band colors (blue/amber/white).
4. **High Detail** — Log amplitude scaling (strength 20), per-band normalization, 0.05 min brightness. Maximizes visibility of quiet sections.

The "SCUE Default" preset is initially active.

---

## Non-Goals (v1)

- **Backend re-analysis from the tuning page.** Crossover frequency changes show an approximation only. A "Re-analyze" button could be added later.
- **Per-track presets.** Presets are global. Per-genre or per-track overrides are a future concern.
- **Undo/redo.** The draft system and preset loading provide sufficient rollback.
- **Export/import presets.** The YAML file is human-readable and can be manually shared.
- **Live waveform tuning.** The DeckWaveform component reads the active preset but the tuning page operates on static analysis data only.

---

## Acceptance Criteria

- [ ] Page loads at `/dev/waveforms` with track picker and parameter controls.
- [ ] Adjusting any parameter re-renders the waveform within one animation frame.
- [ ] Per-band normalization visibly reduces bass dominance on bass-heavy tracks.
- [ ] Sqrt/log amplitude scaling visibly improves detail in quiet sections.
- [ ] Pioneer reference waveform renders from ANLZ PWV5 data and syncs scroll/zoom.
- [ ] Presets can be saved, loaded, renamed, deleted, and activated.
- [ ] Active preset is persisted across page refreshes (stored in YAML, fetched on load).
- [ ] Other waveform components (AnalysisViewer, DeckWaveform) respect the active preset.
- [ ] `config/waveform-presets.yaml` ships with 4 seed presets.
- [ ] TypeScript strict mode passes. Production build succeeds.

---

## Skill Reference

Domain knowledge for implementation: `skills/waveform-rendering.md`
Research findings: `research/findings-waveform-frequency-color-rendering.md`

## Related ADRs

- ADR-018: Pioneer-accurate RGB waveform rendering (current approach)
- A new ADR should be filed when the active preset system is implemented, documenting the decision to apply rendering params at frontend render time rather than backend analysis time.
