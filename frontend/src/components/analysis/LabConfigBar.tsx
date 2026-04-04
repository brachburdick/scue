/** Lab mode configuration bar — variant preset selection + substep overrides. */

import { useState } from "react";
import type { SubstepId, VariantsResponse } from "../../types/strata";

const SUBSTEP_LABELS: Record<SubstepId, string> = {
  transition_detection: "Transitions",
  energy_trend: "Energy Trend",
  fill_detection: "Fills",
};

const SUBSTEP_IDS: SubstepId[] = ["transition_detection", "energy_trend", "fill_detection"];

interface LabConfigBarProps {
  variants: VariantsResponse | undefined;
  baseVariant: string;
  onBaseVariantChange: (v: string) => void;
  compareVariant: string | null;
  onCompareVariantChange: (v: string | null) => void;
  overrides: Partial<Record<SubstepId, string>>;
  onOverridesChange: (o: Partial<Record<SubstepId, string>>) => void;
  onRunVariant: () => void;
  onReset: () => void;
  isAnalyzing: boolean;
  hasTrack: boolean;
}

export function LabConfigBar({
  variants,
  baseVariant,
  onBaseVariantChange,
  compareVariant,
  onCompareVariantChange,
  overrides,
  onOverridesChange,
  onRunVariant,
  onReset,
  isAnalyzing,
  hasTrack,
}: LabConfigBarProps) {
  const [showOverrides, setShowOverrides] = useState(false);
  const presetNames = variants ? Object.keys(variants.presets) : ["default"];

  const hasOverrides = Object.keys(overrides).length > 0;

  return (
    <div className="bg-gray-950 border border-gray-800 rounded p-3 flex flex-col gap-2">
      {/* Main row: presets + actions */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Base variant */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Base:</span>
          <select
            value={baseVariant}
            onChange={(e) => onBaseVariantChange(e.target.value)}
            className="bg-gray-900 border border-gray-700 text-sm text-white rounded px-2 py-1 focus:outline-none focus:border-blue-500"
          >
            {presetNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>

        <span className="text-gray-600 text-xs font-medium">vs</span>

        {/* Compare variant */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Compare:</span>
          <select
            value={compareVariant ?? ""}
            onChange={(e) => onCompareVariantChange(e.target.value || null)}
            className="bg-gray-900 border border-gray-700 text-sm text-white rounded px-2 py-1 focus:outline-none focus:border-purple-500"
          >
            <option value="">None</option>
            {presetNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>

        <div className="flex-1" />

        {/* Overrides toggle */}
        <button
          onClick={() => setShowOverrides(!showOverrides)}
          className={`text-xs px-2 py-1 rounded transition-colors ${
            hasOverrides
              ? "bg-amber-900/40 text-amber-300 border border-amber-700"
              : "text-gray-500 hover:text-gray-300 border border-gray-800 hover:border-gray-700"
          }`}
        >
          {showOverrides ? "Hide" : "Overrides"}{hasOverrides ? " *" : ""}
        </button>

        {/* Run button */}
        <button
          onClick={onRunVariant}
          disabled={isAnalyzing || !hasTrack}
          className={`px-3 py-1 text-sm rounded transition-colors ${
            isAnalyzing || !hasTrack
              ? "bg-blue-800 text-blue-400 cursor-not-allowed"
              : "bg-blue-600 text-white hover:bg-blue-500"
          }`}
        >
          {isAnalyzing ? "Running..." : "Run Variant"}
        </button>

        {/* Reset */}
        <button
          onClick={onReset}
          className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
          title="Reset to preset defaults"
        >
          Reset
        </button>
      </div>

      {/* Overrides row (collapsible) */}
      {showOverrides && variants && (
        <div className="flex items-center gap-4 pt-1 border-t border-gray-800">
          {SUBSTEP_IDS.map((substepId) => {
            const strategies = variants.available_strategies[substepId] ?? [];
            const presetDefault = variants.presets[baseVariant]?.[substepId] ?? strategies[0] ?? "";
            const currentValue = overrides[substepId] ?? presetDefault;
            const isOverridden = substepId in overrides;

            return (
              <div key={substepId} className="flex items-center gap-1.5">
                <span className={`text-xs ${isOverridden ? "text-amber-400" : "text-gray-500"}`}>
                  {SUBSTEP_LABELS[substepId]}:
                </span>
                <select
                  value={currentValue}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val === presetDefault) {
                      const next = { ...overrides };
                      delete next[substepId];
                      onOverridesChange(next);
                    } else {
                      onOverridesChange({ ...overrides, [substepId]: val });
                    }
                  }}
                  className={`bg-gray-900 border text-xs rounded px-1.5 py-0.5 focus:outline-none ${
                    isOverridden
                      ? "border-amber-700 text-amber-300"
                      : "border-gray-700 text-gray-400"
                  }`}
                >
                  {strategies.map((s) => (
                    <option key={s} value={s}>
                      {s}{s === presetDefault ? " (preset)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
