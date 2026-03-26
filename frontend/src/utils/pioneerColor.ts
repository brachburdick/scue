/**
 * Pioneer waveform color mapping — shared utility.
 *
 * Maps low/mid/high frequency band amplitudes to RGB color values
 * matching Pioneer/BLT waveform appearance.
 *
 * See research/waveform-references/PIONEER_COLOR_MODE.md for full
 * research notes and iteration history.
 *
 * DATA SOURCE NOTE:
 * These coefficients were tuned against Pioneer's pre-analyzed waveform data
 * (from beat-link bridge, THREE_BAND style). When used with SCUE-computed
 * waveform data, colors may shift slightly because the crossover frequencies
 * differ:
 *   - Pioneer: likely ~300Hz / ~3kHz crossovers
 *   - SCUE:    200Hz / 2500Hz crossovers (configurable in waveform.py)
 *
 * If the color balance looks wrong on SCUE-computed data, adjust the
 * coefficients here or add a data-source-aware wrapper.
 */

export interface PioneerRGB {
  r: number; // 0-255
  g: number; // 0-255
  b: number; // 0-255
}

/**
 * Convert low/mid/high band amplitudes (0.0-1.0) to Pioneer-style RGB.
 *
 * Uses direct amplitude mapping (not ratio-normalized) to preserve
 * per-bar color variance. sqrt compression on amplitudes gives
 * Pioneer-like dynamics.
 *
 * Color mapping:
 *   R = bass (1.15x boost — bass is perceptually underweight)
 *   G = mid (0.55x) + high (0.25x) — attenuated, produces cyan/orange accents
 *   B = high (0.90x) + mid (0.45x) — dominant cool tone
 *
 * The max channel is normalized to 255 so color represents frequency
 * balance while bar height (computed separately) represents amplitude.
 */
export function pioneerColor(low: number, mid: number, high: number): PioneerRGB {
  // sqrt compression for Pioneer-like dynamics
  const lAmp = Math.sqrt(low);
  const mAmp = Math.sqrt(mid);
  const hAmp = Math.sqrt(high);

  // Map bands to RGB channels
  let r = lAmp * 1.15;
  let g = mAmp * 0.55 + hAmp * 0.25;
  let b = hAmp * 0.90 + mAmp * 0.45;

  // Normalize so max channel = 1.0
  const maxCh = Math.max(r, g, b, 0.001);
  r /= maxCh;
  g /= maxCh;
  b /= maxCh;

  return {
    r: Math.min(255, Math.round(r * 255)),
    g: Math.min(255, Math.round(g * 255)),
    b: Math.min(255, Math.round(b * 255)),
  };
}

/**
 * Legacy color mapping: Low→R, Mid→G, High→B ratio-based.
 * Kept for reference and potential A/B comparison.
 */
export function legacyRgbColor(low: number, mid: number, high: number): PioneerRGB {
  const amp = Math.max(low, mid, high);
  if (amp < 0.001) return { r: 0, g: 0, b: 0 };
  return {
    r: Math.min(255, Math.round((low / amp) * 255)),
    g: Math.min(255, Math.round((mid / amp) * 255)),
    b: Math.min(255, Math.round((high / amp) * 255)),
  };
}
