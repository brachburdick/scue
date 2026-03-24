/** Waveform rendering preset types — mirrors backend WaveformRenderParams. */

export interface WaveformRenderParams {
  // Frequency band weighting
  normalization: "global" | "per_band" | "weighted";
  lowGain: number;
  midGain: number;
  highGain: number;
  frequencyWeighting: "none" | "a_weight" | "k_weight" | "pink_tilt";
  lowCrossover: number;
  highCrossover: number;

  // Amplitude scaling
  amplitudeScale: "linear" | "sqrt" | "log" | "gamma";
  gamma: number;
  logStrength: number;
  noiseFloor: number;
  peakNormalize: boolean;

  // Color mapping
  colorMode: "rgb_blend" | "three_band_overlap" | "mono_blue";
  lowColor: string;
  midColor: string;
  highColor: string;
  saturation: number;
  brightness: number;
  minBrightness: number;
}

export interface WaveformPreset {
  id: string;
  name: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  params: WaveformRenderParams;
}

export interface WaveformPresetsResponse {
  activePresetId: string;
  presets: WaveformPreset[];
}

export const DEFAULT_RENDER_PARAMS: WaveformRenderParams = {
  normalization: "global",
  lowGain: 1.0,
  midGain: 1.0,
  highGain: 1.0,
  frequencyWeighting: "none",
  lowCrossover: 200,
  highCrossover: 2500,
  amplitudeScale: "linear",
  gamma: 1.0,
  logStrength: 10,
  noiseFloor: 0.001,
  peakNormalize: true,
  colorMode: "rgb_blend",
  lowColor: "#ff0000",
  midColor: "#00ff00",
  highColor: "#0000ff",
  saturation: 1.0,
  brightness: 1.0,
  minBrightness: 0.0,
};
