/**
 * ParameterControls — three-column grid of tunable waveform rendering parameters.
 *
 * Exposes frequency weighting, amplitude scaling, and color mapping controls.
 * Changes fire immediately into the parent via onParamChange.
 */

import type { WaveformRenderParams } from "../../types/waveformPreset";

interface Props {
  params: WaveformRenderParams;
  onParamChange: (partial: Partial<WaveformRenderParams>) => void;
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  unit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  unit?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-slate-400 w-28 shrink-0">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 h-1 accent-cyan-500"
      />
      <span className="text-xs text-slate-500 w-14 text-right font-mono">
        {value.toFixed(step < 1 ? (step < 0.01 ? 3 : 2) : 0)}
        {unit ?? ""}
      </span>
    </div>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-slate-400 w-28 shrink-0">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-slate-800 text-sm text-white border border-slate-700 rounded px-2 py-0.5"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-slate-400 w-28 shrink-0">{label}</label>
      <button
        onClick={() => onChange(!value)}
        className={`px-2 py-0.5 text-xs rounded ${
          value
            ? "bg-cyan-600 text-white"
            : "bg-slate-700 text-slate-400"
        }`}
      >
        {value ? "On" : "Off"}
      </button>
    </div>
  );
}

function ColorInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-slate-400 w-28 shrink-0">{label}</label>
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-8 h-6 rounded border border-slate-700 bg-transparent cursor-pointer"
      />
      <span className="text-xs text-slate-500 font-mono">{value}</span>
    </div>
  );
}

function PanelHeader({ title }: { title: string }) {
  return <h3 className="text-sm font-medium text-white mb-3">{title}</h3>;
}

export function ParameterControls({ params, onParamChange }: Props) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Frequency Band Weighting */}
      <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
        <PanelHeader title="Frequency Weighting" />
        <Select
          label="Normalization"
          value={params.normalization}
          options={[
            { value: "global", label: "Global" },
            { value: "per_band", label: "Per Band" },
            { value: "weighted", label: "Weighted" },
          ]}
          onChange={(v) => onParamChange({ normalization: v as WaveformRenderParams["normalization"] })}
        />
        <Slider
          label="Low Gain"
          value={params.lowGain}
          min={0}
          max={3}
          step={0.05}
          onChange={(v) => onParamChange({ lowGain: v })}
        />
        <Slider
          label="Mid Gain"
          value={params.midGain}
          min={0}
          max={3}
          step={0.05}
          onChange={(v) => onParamChange({ midGain: v })}
        />
        <Slider
          label="High Gain"
          value={params.highGain}
          min={0}
          max={3}
          step={0.05}
          onChange={(v) => onParamChange({ highGain: v })}
        />
        <Select
          label="Freq Weighting"
          value={params.frequencyWeighting}
          options={[
            { value: "none", label: "None" },
            { value: "a_weight", label: "A-Weight" },
            { value: "k_weight", label: "K-Weight" },
            { value: "pink_tilt", label: "Pink Tilt" },
          ]}
          onChange={(v) => onParamChange({ frequencyWeighting: v as WaveformRenderParams["frequencyWeighting"] })}
        />
        <Slider
          label="Low Crossover"
          value={params.lowCrossover}
          min={80}
          max={500}
          step={10}
          onChange={(v) => onParamChange({ lowCrossover: v })}
          unit=" Hz"
        />
        <Slider
          label="High Crossover"
          value={params.highCrossover}
          min={1000}
          max={8000}
          step={100}
          onChange={(v) => onParamChange({ highCrossover: v })}
          unit=" Hz"
        />
        {(params.lowCrossover !== 200 || params.highCrossover !== 2500) && (
          <div className="text-xs text-amber-400 mt-1">
            Re-analyze required for accurate crossover changes
          </div>
        )}
      </div>

      {/* Amplitude Scaling */}
      <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
        <PanelHeader title="Amplitude Scaling" />
        <Select
          label="Scale"
          value={params.amplitudeScale}
          options={[
            { value: "linear", label: "Linear" },
            { value: "sqrt", label: "Square Root" },
            { value: "log", label: "Logarithmic" },
            { value: "gamma", label: "Gamma" },
          ]}
          onChange={(v) => onParamChange({ amplitudeScale: v as WaveformRenderParams["amplitudeScale"] })}
        />
        {params.amplitudeScale === "gamma" && (
          <Slider
            label="Gamma"
            value={params.gamma}
            min={0.1}
            max={1.0}
            step={0.05}
            onChange={(v) => onParamChange({ gamma: v })}
          />
        )}
        {params.amplitudeScale === "log" && (
          <Slider
            label="Log Strength"
            value={params.logStrength}
            min={1}
            max={100}
            step={1}
            onChange={(v) => onParamChange({ logStrength: v })}
          />
        )}
        <Slider
          label="Noise Floor"
          value={params.noiseFloor}
          min={0}
          max={0.1}
          step={0.001}
          onChange={(v) => onParamChange({ noiseFloor: v })}
        />
        <Toggle
          label="Peak Normalize"
          value={params.peakNormalize}
          onChange={(v) => onParamChange({ peakNormalize: v })}
        />
      </div>

      {/* Color Mapping */}
      <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
        <PanelHeader title="Color Mapping" />
        <Select
          label="Color Mode"
          value={params.colorMode}
          options={[
            { value: "rgb_blend", label: "RGB Blend" },
            { value: "three_band_overlap", label: "3-Band Overlap" },
            { value: "mono_blue", label: "Mono Blue" },
          ]}
          onChange={(v) => onParamChange({ colorMode: v as WaveformRenderParams["colorMode"] })}
        />
        <ColorInput
          label="Low Color"
          value={params.lowColor}
          onChange={(v) => onParamChange({ lowColor: v })}
        />
        <ColorInput
          label="Mid Color"
          value={params.midColor}
          onChange={(v) => onParamChange({ midColor: v })}
        />
        <ColorInput
          label="High Color"
          value={params.highColor}
          onChange={(v) => onParamChange({ highColor: v })}
        />
        <Slider
          label="Saturation"
          value={params.saturation}
          min={0}
          max={2}
          step={0.05}
          onChange={(v) => onParamChange({ saturation: v })}
        />
        <Slider
          label="Brightness"
          value={params.brightness}
          min={0}
          max={2}
          step={0.05}
          onChange={(v) => onParamChange({ brightness: v })}
        />
        <Slider
          label="Min Brightness"
          value={params.minBrightness}
          min={0}
          max={0.3}
          step={0.01}
          onChange={(v) => onParamChange({ minBrightness: v })}
        />
      </div>
    </div>
  );
}
