/** Progress indicators for strata analysis jobs (single-track and batch). */

import { useEffect, useRef } from "react";
import { useStrataJobStatus, useStrataBatchStatus } from "../../api/strata";
import type { StrataTier } from "../../types/strata";

const TIER_LABELS: Record<StrataTier, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
  live: "Live",
  live_offline: "Live Offline",
};

/** Estimated seconds per stage for standard tier.
 *  Stage 1 (load): ~1s, Stage 2 (demucs): ~60s, Stage 3 (per-stem): ~10s,
 *  Stage 4 (transitions): ~3s, Stage 5 (assembly): ~1s.
 *  Total: ~75s. Demucs dominates at ~80% of wall time.
 */
const STAGE_DURATIONS: Record<number, number> = {
  1: 1,
  2: 60,
  3: 10,
  4: 3,
  5: 1,
};

const DEFAULT_STAGE_DURATION = 5;

/** Cumulative duration up to (but not including) a given step.
 *  Used to weight progress bar by estimated wall time, not step count.
 *  Step 1 start = 0%, Step 2 start = 1/75 ≈ 1%, Step 3 start = 61/75 ≈ 81%.
 */
function durationWeightedPercent(currentStep: number, totalSteps: number): number {
  let totalDuration = 0;
  let completedDuration = 0;
  for (let s = 1; s <= totalSteps; s++) {
    const d = STAGE_DURATIONS[s] ?? DEFAULT_STAGE_DURATION;
    totalDuration += d;
    if (s < currentStep) completedDuration += d;
  }
  if (totalDuration === 0) return 0;
  return Math.round((completedDuration / totalDuration) * 100);
}

function estimateRemaining(currentStep: number, totalSteps: number): string | null {
  if (currentStep <= 0 || currentStep > totalSteps) return null;
  let remaining = 0;
  // Current stage partially done — estimate halfway through
  const currentDuration = STAGE_DURATIONS[currentStep] ?? DEFAULT_STAGE_DURATION;
  remaining += currentDuration * 0.5;
  for (let s = currentStep + 1; s <= totalSteps; s++) {
    remaining += STAGE_DURATIONS[s] ?? DEFAULT_STAGE_DURATION;
  }
  if (remaining < 5) return "< 5s";
  if (remaining < 60) return `~${Math.round(remaining)}s`;
  const mins = Math.round(remaining / 60);
  return `~${mins}m`;
}

/** Shows progress bar for a single strata analysis job. */
export function StrataJobProgress({
  jobId,
  tier,
  onComplete,
  onCancel,
}: {
  jobId: string;
  tier: StrataTier;
  onComplete?: () => void;
  onCancel?: () => void;
}) {
  const { data: job } = useStrataJobStatus(jobId);

  if (!job) {
    return (
      <div className="h-48 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
        <div className="w-4 h-4 rounded-full bg-blue-500 animate-pulse" />
        <span className="text-sm text-gray-300">Starting {TIER_LABELS[tier]} analysis...</span>
      </div>
    );
  }

  const isDone = job.status === "complete" || job.status === "failed";
  const pct = job.total_steps > 0 ? durationWeightedPercent(job.current_step, job.total_steps) : 0;

  // Notify parent on completion
  if (isDone && onComplete) {
    setTimeout(onComplete, 0);
  }

  if (job.status === "failed") {
    return (
      <div className="h-48 flex flex-col items-center justify-center bg-red-950 rounded border border-red-800 gap-2">
        <p className="text-sm text-red-300">
          {TIER_LABELS[tier]} analysis failed
        </p>
        <p className="text-xs text-red-400">{job.error ?? "Unknown error"}</p>
      </div>
    );
  }

  if (job.status === "complete") {
    return null; // Parent will show results via refetch
  }

  const eta = estimateRemaining(job.current_step, job.total_steps);

  return (
    <div className="h-48 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
      <span className="text-sm text-gray-300">
        Analyzing {TIER_LABELS[tier]}...
      </span>

      {/* Progress bar */}
      <div className="w-64">
        <div className="w-full bg-gray-800 rounded-full h-2 mb-2">
          <div
            className="h-2 rounded-full bg-blue-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {job.current_step_name || "Preparing..."}
          </span>
          <span className="text-xs text-gray-600">
            {pct}%{eta ? ` \u2022 ${eta}` : ""}
          </span>
        </div>
      </div>

      {/* Cancel button */}
      {onCancel && (
        <button
          onClick={onCancel}
          className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          Cancel
        </button>
      )}
    </div>
  );
}

/** Shows progress for a batch strata analysis. */
export function StrataBatchProgress({
  batchId,
  onComplete,
  onCancel,
}: {
  batchId: string;
  onComplete?: () => void;
  onCancel?: () => void;
}) {
  const { data: batch } = useStrataBatchStatus(batchId);
  const completeFired = useRef(false);

  // Backend sets status="complete" when processing finishes, even if all jobs failed.
  // Derive visual state from actual counts, not just the status string.
  const isFinished = batch?.status === "complete" || batch?.status === "failed";
  const isRunning = batch?.status === "running" || batch?.status === "pending";
  const failedCount = batch?.failed ?? 0;
  const completedCount = batch?.completed ?? 0;
  const processed = completedCount + failedCount;
  const pct = (batch?.total ?? 0) > 0 ? Math.round((processed / batch!.total) * 100) : 0;
  const isCancelled = isFinished && (batch?.jobs.some((j) => j.error === "Cancelled by user") ?? false);
  const isPureSuccess = isFinished && failedCount === 0;
  const hasFailures = isFinished && failedCount > 0;

  // Find the currently running job for detail display
  const activeJob = batch?.jobs.find((j) => j.status === "running");

  // Auto-dismiss only on pure success (all completed, none failed).
  // Failures/cancellations stay visible so the user can see what happened.
  useEffect(() => {
    if (isPureSuccess && onComplete && !completeFired.current) {
      completeFired.current = true;
      onComplete();
    }
  }, [isPureSuccess, onComplete]);

  if (!batch) {
    return (
      <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm text-gray-300">Starting batch analysis...</span>
        </div>
      </div>
    );
  }

  const barColor = isCancelled
    ? "bg-yellow-500"
    : hasFailures
      ? completedCount > 0 ? "bg-amber-500" : "bg-red-500"
      : isPureSuccess
        ? "bg-green-500"
        : "bg-blue-500";

  return (
    <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800 space-y-2">
      {/* Header row */}
      <div className="flex justify-between items-center text-xs text-gray-400">
        <span>
          {isCancelled
            ? <span className="text-yellow-400">Cancelled — {completedCount}/{batch.total} completed</span>
            : isPureSuccess
              ? <span className="text-green-400">Complete — {completedCount} succeeded</span>
              : hasFailures
                ? <span className="text-red-400">{completedCount > 0 ? `Done — ${completedCount} succeeded, ${failedCount} failed` : `Failed — ${failedCount} failed`}</span>
                : `Analyzing: ${activeJob?.current_step_name || "..."}`}
        </span>
        <div className="flex items-center gap-3">
          <span>{processed}/{batch.total} ({pct}%)</span>
          {isRunning && onCancel && (
            <button
              onClick={onCancel}
              className="px-2 py-0.5 text-xs font-medium rounded bg-red-900/50 hover:bg-red-800 text-red-300 border border-red-800 transition-colors"
            >
              Stop
            </button>
          )}
          {isFinished && !isPureSuccess && onComplete && (
            <button
              onClick={onComplete}
              className="px-2 py-0.5 text-xs font-medium rounded bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 transition-colors"
            >
              Dismiss
            </button>
          )}
        </div>
      </div>

      {/* Overall progress bar */}
      <div className="w-full bg-gray-800 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Per-step progress for active job */}
      {isRunning && activeJob && activeJob.current_step_name && (
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{activeJob.current_step_name}</span>
            <span>{activeJob.current_step}/{activeJob.total_steps}</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1">
            <div
              className="h-1 rounded-full bg-cyan-500 transition-all"
              style={{ width: `${activeJob.total_steps > 0 ? (activeJob.current_step / activeJob.total_steps) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Error summary — group failures by reason */}
      {hasFailures && (() => {
        const errorGroups: Record<string, number> = {};
        for (const job of batch.jobs) {
          if (job.status === "failed" && job.error) {
            // Normalize errors that differ only by fingerprint
            const key = job.error.replace(/[a-f0-9]{12,}/, "…");
            errorGroups[key] = (errorGroups[key] ?? 0) + 1;
          }
        }
        return (
          <div className="flex flex-col gap-1 text-xs text-gray-500">
            {Object.entries(errorGroups).map(([reason, count]) => (
              <div key={reason} className="flex items-start gap-1.5">
                <span className="text-red-400/70 flex-shrink-0">×{count}</span>
                <span className="truncate" title={reason}>{reason}</span>
              </div>
            ))}
          </div>
        );
      })()}
    </div>
  );
}
