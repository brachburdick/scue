/**
 * AnnotationToolbar — event type selector, snap control, placement mode,
 * undo/redo, and save button.
 */

import type { EventType } from "../../types/events";
import type { SnapResolution, PlacementMode } from "../../types/groundTruth";
import { EVENT_COLORS } from "../../types/events";

const ALL_TYPES: EventType[] = ["kick", "snare", "clap", "hihat", "riser", "faller", "stab"];
const SNAP_OPTIONS: { value: SnapResolution; label: string }[] = [
  { value: "16th", label: "16th" },
  { value: "32nd", label: "32nd" },
  { value: "64th", label: "64th" },
  { value: "off", label: "Off" },
];

const TONAL_TYPES = new Set<EventType>(["riser", "faller", "stab"]);

interface AnnotationToolbarProps {
  activeType: EventType;
  onTypeChange: (type: EventType) => void;
  placementMode: PlacementMode;
  onModeChange: (mode: PlacementMode) => void;
  snapResolution: SnapResolution;
  onSnapChange: (snap: SnapResolution) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  isSaving: boolean;
  isDirty: boolean;
  annotationCount: number;

  /** Detector overlay toggle */
  showDetectorOverlay: boolean;
  onToggleDetectorOverlay: () => void;

  /** Event type visibility toggles */
  visibleTypes: Set<EventType>;
  onToggleTypeVisibility: (type: EventType) => void;
}

export function AnnotationToolbar({
  activeType,
  onTypeChange,
  placementMode,
  onModeChange,
  snapResolution,
  onSnapChange,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onSave,
  isSaving,
  isDirty,
  annotationCount,
  showDetectorOverlay,
  onToggleDetectorOverlay,
  visibleTypes,
  onToggleTypeVisibility,
}: AnnotationToolbarProps) {
  return (
    <div className="bg-slate-800/50 rounded-lg p-4 space-y-4">
      {/* Event type selector */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
          Event Type
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ALL_TYPES.map((type) => {
            const isActive = activeType === type;
            const isVisible = visibleTypes.has(type);
            const color = EVENT_COLORS[type];
            return (
              <div key={type} className="flex items-center gap-0.5">
                <input
                  type="checkbox"
                  checked={isVisible}
                  onChange={() => onToggleTypeVisibility(type)}
                  className="w-3 h-3 rounded border-slate-600 bg-slate-700 text-cyan-500 focus:ring-0 cursor-pointer"
                  title={`${isVisible ? "Hide" : "Show"} ${type} events`}
                />
                <button
                  onClick={() => {
                    onTypeChange(type);
                    // Auto-switch placement mode based on event type
                    if (TONAL_TYPES.has(type)) {
                      onModeChange("region");
                    } else {
                      onModeChange("point");
                    }
                  }}
                  className={`px-3 py-1.5 text-xs font-medium rounded transition-all ${
                    isActive
                      ? "ring-2 ring-offset-1 ring-offset-slate-900 text-white"
                      : "text-slate-400 hover:text-slate-200 opacity-50 hover:opacity-70"
                  } ${!isVisible ? "line-through opacity-30" : ""}`}
                  style={{
                    backgroundColor: isActive ? color + "30" : "transparent",
                    borderColor: color,
                    ringColor: color,
                    ...(isActive ? { boxShadow: `0 0 0 2px ${color}` } : {}),
                  }}
                >
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-1.5"
                    style={{ backgroundColor: color }}
                  />
                  {type}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Placement mode + Snap */}
      <div className="flex items-center gap-6">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
            Mode
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => onModeChange("point")}
              className={`px-2.5 py-1 text-xs rounded ${
                placementMode === "point"
                  ? "bg-slate-600 text-white"
                  : "text-slate-400 hover:bg-slate-700"
              }`}
            >
              Point
            </button>
            <button
              onClick={() => onModeChange("region")}
              className={`px-2.5 py-1 text-xs rounded ${
                placementMode === "region"
                  ? "bg-slate-600 text-white"
                  : "text-slate-400 hover:bg-slate-700"
              }`}
            >
              Region
            </button>
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
            Snap
          </div>
          <select
            value={snapResolution}
            onChange={(e) => onSnapChange(e.target.value as SnapResolution)}
            className="bg-slate-700 text-slate-200 text-xs rounded px-2 py-1 border border-slate-600"
          >
            {SNAP_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Undo / Redo */}
        <div className="flex gap-1">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            className="px-2 py-1 text-xs rounded text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Undo (Ctrl+Z)"
          >
            Undo
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            className="px-2 py-1 text-xs rounded text-slate-400 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Redo (Ctrl+Shift+Z)"
          >
            Redo
          </button>
        </div>

        {/* Detector overlay toggle */}
        <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={showDetectorOverlay}
            onChange={onToggleDetectorOverlay}
            className="rounded border-slate-600 bg-slate-700 text-cyan-500 focus:ring-cyan-500"
          />
          Show detectors
        </label>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Count + Save */}
        <span className="text-xs text-slate-500">{annotationCount} annotations</span>
        <button
          onClick={onSave}
          disabled={isSaving || !isDirty}
          className={`px-4 py-1.5 text-xs font-medium rounded transition-colors ${
            isDirty
              ? "bg-cyan-600 hover:bg-cyan-500 text-white"
              : "bg-slate-700 text-slate-500 cursor-not-allowed"
          }`}
        >
          {isSaving ? "Saving..." : isDirty ? "Save" : "Saved"}
        </button>
      </div>
    </div>
  );
}
