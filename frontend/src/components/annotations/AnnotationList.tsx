/**
 * AnnotationList — sortable table of ground truth annotations.
 * Click to select/scroll-to on timeline, delete button per row.
 */

import type { AnnotationSource, GroundTruthEvent } from "../../types/groundTruth";
import type { EventType } from "../../types/events";
import { EVENT_COLORS } from "../../types/events";

const SOURCE_BADGES: Record<AnnotationSource, { label: string; className: string }> = {
  predicted: { label: "P", className: "bg-slate-600 text-slate-300" },
  corrected: { label: "C", className: "bg-yellow-700 text-yellow-200" },
  manual: { label: "M", className: "bg-cyan-800 text-cyan-300" },
};

interface AnnotationListProps {
  annotations: GroundTruthEvent[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
  onDelete: (index: number) => void;
  visibleTypes: Set<EventType>;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

export function AnnotationList({
  annotations,
  selectedIndex,
  onSelect,
  onDelete,
  visibleTypes,
}: AnnotationListProps) {
  if (annotations.length === 0) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-4 text-center text-sm text-slate-500">
        No annotations yet. Click on the waveform to place events.
      </div>
    );
  }

  return (
    <div className="bg-slate-800/50 rounded-lg overflow-hidden">
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-slate-500 uppercase tracking-wider">
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Time</th>
              <th className="px-3 py-2 text-left">Duration</th>
              <th className="px-3 py-2 text-center">Src</th>
              <th className="px-3 py-2 text-right w-10" />
            </tr>
          </thead>
          <tbody>
            {annotations.map((a, i) => {
              const isSelected = selectedIndex === i;
              const isHidden = !visibleTypes.has(a.type);
              if (isHidden) return null;
              const color = EVENT_COLORS[a.type] ?? "#ffffff";
              return (
                <tr
                  key={`${a.type}-${a.timestamp}-${i}`}
                  onClick={() => onSelect(i)}
                  className={`cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-slate-700/60"
                      : "hover:bg-slate-800/80"
                  }`}
                >
                  <td className="px-3 py-1.5">
                    <span className="flex items-center gap-1.5">
                      <span
                        className="inline-block w-2 h-2 rounded-full"
                        style={{ backgroundColor: color }}
                      />
                      <span className={isSelected ? "text-white font-medium" : "text-slate-300"}>
                        {a.type}
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-slate-400 font-mono">
                    {formatTime(a.timestamp)}
                  </td>
                  <td className="px-3 py-1.5 text-slate-500 font-mono">
                    {a.duration ? `${a.duration.toFixed(2)}s` : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    {a.source && (
                      <span
                        className={`inline-block w-4 text-center rounded text-[10px] font-bold leading-4 ${SOURCE_BADGES[a.source].className}`}
                        title={a.source}
                      >
                        {SOURCE_BADGES[a.source].label}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(i);
                      }}
                      className="text-slate-600 hover:text-red-400 transition-colors"
                      title="Delete annotation"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
