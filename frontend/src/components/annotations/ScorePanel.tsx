/**
 * ScorePanel — displays precision/recall/F1 per event type
 * from the eval harness scoring endpoint.
 */

import { EVENT_COLORS } from "../../types/events";
import type { ScoreResponse } from "../../types/groundTruth";

interface ScorePanelProps {
  scoreData: ScoreResponse | null;
  isScoring: boolean;
  onScore: () => void;
  hasAnnotations: boolean;
  hasDetectedEvents: boolean;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export function ScorePanel({
  scoreData,
  isScoring,
  onScore,
  hasAnnotations,
  hasDetectedEvents,
}: ScorePanelProps) {
  const canScore = hasAnnotations && hasDetectedEvents;

  return (
    <div className="bg-slate-800/50 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-300">Eval Scores</h3>
        <button
          onClick={onScore}
          disabled={isScoring || !canScore}
          className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
            canScore
              ? "bg-cyan-600 hover:bg-cyan-500 text-white"
              : "bg-slate-700 text-slate-500 cursor-not-allowed"
          }`}
        >
          {isScoring ? "Scoring..." : "Run Eval"}
        </button>
      </div>

      {!canScore && !scoreData && (
        <p className="text-xs text-slate-500">
          {!hasAnnotations
            ? "Add annotations first, then run eval."
            : "No detected events to compare against."}
        </p>
      )}

      {scoreData && (
        <div className="space-y-1">
          <div className="grid grid-cols-7 gap-1 text-[10px] text-slate-500 uppercase tracking-wider px-1">
            <span className="col-span-2">Type</span>
            <span className="text-right">Prec</span>
            <span className="text-right">Recall</span>
            <span className="text-right">F1</span>
            <span className="text-right">TP</span>
            <span className="text-right">FP/FN</span>
          </div>
          {Object.entries(scoreData.scores)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([eventType, sc]) => {
              const color = EVENT_COLORS[eventType as keyof typeof EVENT_COLORS] ?? "#888";
              return (
                <div
                  key={eventType}
                  className="grid grid-cols-7 gap-1 text-xs px-1 py-0.5 rounded hover:bg-slate-700/30"
                >
                  <span className="col-span-2 flex items-center gap-1.5">
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-slate-300">{eventType}</span>
                  </span>
                  <span className="text-right text-slate-400 font-mono">{pct(sc.precision)}</span>
                  <span className="text-right text-slate-400 font-mono">{pct(sc.recall)}</span>
                  <span className={`text-right font-mono font-medium ${
                    sc.f1 >= 0.8 ? "text-green-400" : sc.f1 >= 0.5 ? "text-yellow-400" : "text-red-400"
                  }`}>
                    {pct(sc.f1)}
                  </span>
                  <span className="text-right text-slate-500 font-mono">{sc.true_positives}</span>
                  <span className="text-right text-slate-500 font-mono">
                    {sc.false_positives}/{sc.false_negatives}
                  </span>
                </div>
              );
            })}
          <div className="border-t border-slate-700 mt-2 pt-2 text-[10px] text-slate-500">
            Ground truth: {scoreData.total_ground_truth} | Detected: {scoreData.total_detected}
          </div>
        </div>
      )}
    </div>
  );
}
