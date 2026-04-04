/** Compact analysis status badge for the TopBar.
 *
 * Shows batch/single analysis progress, completion, and failure states.
 * Reads from analysisProgressStore (fed by WS analysis_progress messages).
 */

import { useState, useRef, useEffect } from "react";
import { useAnalysisProgressStore } from "../../stores/analysisProgressStore";
import { useCancelStrataBatch } from "../../api/strata";

export function AnalysisStatusBadge() {
  const activeBatch = useAnalysisProgressStore((s) => s.activeBatch);
  const completionMessage = useAnalysisProgressStore((s) => s.completionMessage);
  const completionStatus = useAnalysisProgressStore((s) => s.completionStatus);
  const dismiss = useAnalysisProgressStore((s) => s.dismiss);

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dropdownOpen]);

  // Close dropdown when batch finishes
  useEffect(() => {
    if (!activeBatch) setDropdownOpen(false);
  }, [activeBatch]);

  // Idle — render nothing
  if (!activeBatch && !completionMessage) return null;

  // Completion message (auto-fading or persistent for errors)
  if (!activeBatch && completionMessage) {
    const isSuccess = completionStatus === "complete";
    const isFailed = completionStatus === "failed";
    return (
      <div className="flex items-center gap-1.5">
        <button
          onClick={dismiss}
          className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-opacity ${
            isSuccess
              ? "bg-green-900/50 text-green-300 border border-green-800"
              : isFailed
                ? "bg-red-900/50 text-red-300 border border-red-800"
                : "bg-yellow-900/50 text-yellow-300 border border-yellow-800"
          }`}
        >
          <span>{completionMessage}</span>
          {!isSuccess && <span className="text-[10px] opacity-60">&times;</span>}
        </button>
      </div>
    );
  }

  // Active analysis
  if (!activeBatch) return null;

  const { kind, tier, completed, failed, total, current_track, batch_id } = activeBatch;
  const processed = completed + failed;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

  if (kind === "single") {
    return (
      <div className="flex items-center gap-1.5 rounded-full bg-gray-800 px-2.5 py-1">
        <Spinner />
        <span className="text-xs text-gray-300 max-w-[160px] truncate">
          Analyzing: {current_track?.title ?? "track"} ({tier})
        </span>
      </div>
    );
  }

  // Batch
  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setDropdownOpen(!dropdownOpen)}
        className="flex items-center gap-2 rounded-full bg-gray-800 px-2.5 py-1 hover:bg-gray-700 transition-colors"
      >
        <Spinner />
        <span className="text-xs text-gray-300">
          Batch: {processed}/{total} {tier}
        </span>
        <MiniProgressBar pct={pct} />
        <span className="text-[10px] text-gray-500">{pct}%</span>
      </button>

      {dropdownOpen && (
        <BatchDropdown
          activeBatch={activeBatch}
          batchId={batch_id}
          onClose={() => setDropdownOpen(false)}
        />
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg
      className="w-3 h-3 animate-spin text-blue-400 flex-shrink-0"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

function MiniProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-16 bg-gray-700 rounded-full h-1.5">
      <div
        className="h-1.5 rounded-full bg-blue-500 transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function BatchDropdown({
  activeBatch,
  batchId,
  onClose,
}: {
  activeBatch: NonNullable<ReturnType<typeof useAnalysisProgressStore.getState>["activeBatch"]>;
  batchId?: string;
  onClose: () => void;
}) {
  const cancelMutation = useCancelStrataBatch();
  const { completed, failed, total, tier, current_track } = activeBatch;
  const processed = completed + failed;

  return (
    <div className="absolute right-0 top-full mt-1 w-72 rounded-lg border border-gray-700 bg-gray-900 shadow-xl z-50 p-3 space-y-2">
      {/* Summary */}
      <div className="flex justify-between text-xs text-gray-400">
        <span>
          {tier} analysis — {processed}/{total}
        </span>
        {failed > 0 && (
          <span className="text-red-400">{failed} failed</span>
        )}
      </div>

      {/* Overall progress */}
      <div className="w-full bg-gray-800 rounded-full h-1.5">
        <div
          className="h-1.5 rounded-full bg-blue-500 transition-all"
          style={{ width: `${total > 0 ? Math.round((processed / total) * 100) : 0}%` }}
        />
      </div>

      {/* Current track detail */}
      {current_track && (
        <div className="text-xs text-gray-500 space-y-1">
          <div className="flex items-center gap-1.5">
            <span className="text-blue-400 animate-pulse">&#x25CF;</span>
            <span className="truncate">{current_track.title}</span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>{current_track.step_name}</span>
            <span>
              {current_track.step}/{current_track.total_steps}
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1">
            <div
              className="h-1 rounded-full bg-cyan-500 transition-all"
              style={{
                width: `${current_track.total_steps > 0 ? Math.round((current_track.step / current_track.total_steps) * 100) : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end pt-1 border-t border-gray-800">
        {batchId && (
          <button
            onClick={() => {
              cancelMutation.mutate(batchId);
              onClose();
            }}
            disabled={cancelMutation.isPending}
            className="px-2 py-0.5 text-xs font-medium rounded bg-red-900/50 hover:bg-red-800 text-red-300 border border-red-800 transition-colors disabled:opacity-50"
          >
            {cancelMutation.isPending ? "Cancelling..." : "Cancel Batch"}
          </button>
        )}
      </div>
    </div>
  );
}
