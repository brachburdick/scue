# Pioneer Waveform Color Mode — Research & Implementation Notes

## Date: 2026-03-24
## Status: v4 — "pretty damn close" per operator review

---

## Problem Statement

SCUE's waveform rendering looked nothing like Pioneer/BLT waveforms. The original
`rgb_blend` mode mapped Low→Red, Mid→Green, High→Blue, producing warm yellow/orange/green
tones. Pioneer waveforms are cool-toned: blues, purples, pinks, cyans with red accents.

## Reference Material

22 photos of AHEE - Inner Energy (JADU244) captured from XDJ-AZ at various zoom levels
and track positions. Stored in `research/waveform-references/AHEE - Inner Energy (JADU244)/`.
JPG conversions in the `jpg/` subdirectory.

Additional comparison photos from the operator (IMG_4468, IMG_4469, IMG_4470) showing
SCUE vs Pioneer side-by-side at various iteration stages.

## Key Observations from Reference Photos

### Color Palette (what Pioneer actually shows)
- **Bass-dominant bars** → Vivid RED (kicks, sub-bass)
- **Mid-dominant bars** → Blue/cyan tones (synths, vocals) — NOT green
- **High-dominant bars** → Bright cyan/white (hi-hats, crashes, air)
- **Bass+Mid overlap** → Purple/magenta
- **Mid+High overlap** → Cyan/teal (this is green+blue — green IS present)
- **Bass+High (no mid)** → Purple/magenta
- **Full spectrum peaks** → Lavender/white
- **Bass+Mid (warm)** → Orange tones (red+green)

### Critical Insight: Green Channel IS Present
Initial iterations removed green entirely (mapping Mid→Blue instead of Mid→Green).
This produced a too-saturated pink/purple/blue palette with no variance.

The breakthrough came from noticing **cyans, oranges, and occasional yellows** in the
Pioneer reference photos. These colors REQUIRE the green channel:
- Cyan = Green + Blue (mid + high)
- Orange = Red + Green (bass + mid)
- Lavender/white = R + G + B (all bands)

Pioneer likely uses something close to standard RGB mapping, but the green doesn't
appear as "green" because pure mid-only content is rare in music.

### Per-Bar Color Variance
Pioneer shows high color variance between adjacent bars. This comes from using raw
band amplitudes directly (not ratio-normalized). Each sample's unique frequency balance
produces a unique color.

### Saturation Variance
Some bars are deep/saturated (pure red, pure blue), while others are washed-out/pastel
(lavender, light pink). This variance is natural when using amplitude-driven color — bars
where one band dominates are saturated; bars where all bands are present wash toward white.

## Implementation History

### v1: Mid→Blue remap (too warm, not enough blue)
- Mapped: Low→Red, Mid→Blue, High→White
- Problem: Lost green channel entirely, everything too pink/magenta

### v2: Power-curve sharpening + bass boost (too saturated, too uniform)
- Added sharpness=1.6 power curve on ratios to exaggerate dominant band
- Pre-boosted bass 1.4x to compensate for mids naturally dominating
- Problem: Sharpness too aggressive — blue won every frame, red only on transients

### v3: Reduced sharpness + pastel wash (too washed out, too pink)
- Dropped sharpness to 1.15, added baseBrightness + whitening
- Problem: Everything converged to pink/lavender. No color variance.
- Operator feedback: "too saturated, not variated enough" then "too washed out"

### v4: Direct amplitude RGB (current — "pretty damn close")
- **Fundamental approach change**: dropped ratio normalization entirely
- Uses raw band amplitudes (after sqrt compression) as RGB channel drivers
- Color mapping:
  ```
  R = sqrt(low) * 1.15
  G = sqrt(mid) * 0.55 + sqrt(high) * 0.25
  B = sqrt(high) * 0.90 + sqrt(mid) * 0.45
  ```
- Then normalize so max channel = 1.0 (preserves hue, bar height = amplitude)
- Key: green is present but attenuated (0.55x mid vs 1.0x for red/blue)
- This naturally produces the full Pioneer gamut including cyans, oranges,
  deep saturated bars AND pastel/washed-out bars

### Why v4 Works
1. **No ratio normalization** → each bar's color is driven by its unique amplitude
   profile, not a smoothed/normalized ratio. Adjacent bars with different frequency
   content get different colors.
2. **sqrt compression on amplitudes** → compresses dynamic range before color mapping,
   similar to how Pioneer's ANLZ data is pre-compressed. Makes quiet content visible.
3. **Green channel present but attenuated** → mid energy contributes to cyan (with blue)
   and orange (with red), but doesn't dominate as pure green.
4. **Blue gets both high AND mid contribution** → mids feed into blue (0.45x), which is
   why Pioneer waveforms feel "cool-toned" even though green is present.

## Coefficients Reference

Current v4 mapping (WaveformCanvas.tsx, `colorMode === "pioneer"` branch):

```typescript
// Per-band sqrt compression
const lAmp = Math.sqrt(low);
const mAmp = Math.sqrt(mid);
const hAmp = Math.sqrt(high);

// RGB channel mapping
let r = lAmp * 1.15;                    // Bass → Red (boosted)
let g = mAmp * 0.55 + hAmp * 0.25;     // Mid+High → Green (attenuated)
let b = hAmp * 0.90 + mAmp * 0.45;     // High+Mid → Blue (dominant cool)

// Normalize to max=1.0 (color = frequency balance, height = amplitude)
const maxCh = Math.max(r, g, b, 0.001);
r /= maxCh; g /= maxCh; b /= maxCh;
```

## Data Source Considerations

### Pioneer waveform data (from bridge via beat-link)
- Pre-analyzed by rekordbox, stored in ANLZ files
- THREE_BAND style: per-segment low/mid/high heights (0-31 scale)
- Crossover frequencies determined by rekordbox (not documented, likely ~300Hz and ~3kHz)
- Data served via `/api/bridge/pioneer-waveform/{player}` endpoint
- ~150 samples/sec, normalized 0.0-1.0

### SCUE-computed waveform data (from audio analysis)
- Computed by `scue/layer1/waveform.py` using STFT
- Crossovers: 20-200Hz (low), 200-2500Hz (mid), 2500Hz+ (high)
- Output at 150 FPS (WAVEFORM_FPS), normalized 0.0-1.0
- Global RMS normalization across all bands

### Key Difference
The crossover frequencies differ between Pioneer and SCUE analysis. This means
the same track may have different low/mid/high distributions depending on the data
source. The Pioneer color mode coefficients were tuned against Pioneer's pre-analyzed
data. When applied to SCUE-computed waveforms, the color balance may shift because:
- SCUE's low band extends to 200Hz (vs Pioneer's likely ~300Hz)
- SCUE's mid band is 200-2500Hz (vs Pioneer's likely ~300-3000Hz)
- Different normalization approaches

**If colors look wrong on SCUE-computed waveforms**, the fix is either:
1. Adjust crossover frequencies in `waveform.py` to match Pioneer's
2. Add a "translator" that re-weights the coefficients based on data source
3. Keep separate coefficient sets for Pioneer vs SCUE data

## Future Tuning

If revisiting this work:
1. Start from v4's direct-amplitude approach — don't go back to ratio normalization
2. The green channel attenuation (0.55x) is the most sensitive parameter — too high
   and everything looks green/cyan, too low and you lose the orange/cyan variance
3. The bass boost (1.15x on red) compensates for bass being perceptually quieter
4. The mid→blue crosstalk (0.45x) is what makes the overall feel "cool-toned"
5. sqrt compression can be swapped for other curves (gamma, log) for different dynamics

## Files Modified
- `frontend/src/components/shared/WaveformCanvas.tsx` — new `pioneer` branch in `processBar()`
- `frontend/src/types/waveformPreset.ts` — added `"pioneer"` to colorMode union type
- `config/waveform-presets.yaml` — active preset set to `colorMode: pioneer`
- `frontend/src/components/live/DeckWaveform.tsx` — added zoom + smooth rAF animation
- `frontend/src/components/live/DeckPanel.tsx` — passes `bpm` to DeckWaveform
