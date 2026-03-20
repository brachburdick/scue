/**
 * EventControls — toggles, confidence slider, and strategy selector.
 *
 * Dev-facing controls for the detector tuning page.
 */

import type { EventType } from "../../types/events";
import { EVENT_COLORS } from "../../types/events";

const ALL_EVENT_TYPES: EventType[] = [
  "kick",
  "snare",
  "clap",
  "hihat",
  "riser",
  "faller",
  "stab",
];

interface EventControlsProps {
  visibleTypes: Set<EventType>;
  onToggleType: (type: EventType) => void;
  minConfidence: number;
  onConfidenceChange: (value: number) => void;
}

export function EventControls({
  visibleTypes,
  onToggleType,
  minConfidence,
  onConfidenceChange,
}: EventControlsProps) {
  return (
    <div className="space-y-4">
      {/* Event type toggles */}
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-2">Event Types</h3>
        <div className="flex flex-wrap gap-2">
          {ALL_EVENT_TYPES.map((type) => {
            const active = visibleTypes.has(type);
            const color = EVENT_COLORS[type];
            return (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className={`px-3 py-1 rounded-full text-xs font-mono transition-all ${
                  active
                    ? "ring-2 ring-offset-1 ring-offset-slate-900"
                    : "opacity-40 hover:opacity-60"
                }`}
                style={{
                  backgroundColor: active ? color + "33" : "transparent",
                  color: color,
                  border: `1px solid ${color}`,
                  boxShadow: active ? `0 0 0 2px ${color}44` : undefined,
                }}
              >
                {type}
              </button>
            );
          })}
        </div>
      </div>

      {/* Confidence slider */}
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-2">
          Min Confidence: {(minConfidence * 100).toFixed(0)}%
        </h3>
        <input
          type="range"
          min={0}
          max={100}
          value={minConfidence * 100}
          onChange={(e) => onConfidenceChange(Number(e.target.value) / 100)}
          className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
        />
        <div className="flex justify-between text-xs text-slate-500 mt-1">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}
