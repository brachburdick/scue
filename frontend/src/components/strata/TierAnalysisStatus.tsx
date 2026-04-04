/** Progress indicators for strata analysis jobs (single-track and batch). */

import { useState, useEffect, useRef } from "react";
import { useStrataJobStatus, useStrataBatchStatus } from "../../api/strata";
import type { StrataTier, StrataJobStatus } from "../../types/strata";

const TIER_LABELS: Record<StrataTier, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
  live: "Live",
  live_offline: "Live Offline",
};

/** Estimated seconds per stage for tier-only analysis (5 steps).
 *  Stage 1 (load): ~1s, Stage 2 (demucs): ~60s, Stage 3 (per-stem): ~10s,
 *  Stage 4 (transitions): ~3s, Stage 5 (assembly): ~1s.
 */
const TIER_STAGE_DURATIONS: Record<number, number> = {
  1: 1,
  2: 60,
  3: 10,
  4: 3,
  5: 1,
};

/** Estimated seconds per stage when base analysis is needed (15 steps).
 *  Steps 1-10: base analysis, steps 11-15: tier analysis.
 */
const BASE_PLUS_TIER_DURATIONS: Record<number, number> = {
  1: 1,    // fingerprint
  2: 8,    // features extraction
  3: 5,    // structure analysis
  4: 2,    // boundary detection
  5: 1,    // merge boundaries
  6: 1,    // snap to grid
  7: 2,    // classify sections
  8: 1,    // confidence scoring
  9: 3,    // event detection
  10: 3,   // waveform computation
  11: 1,   // tier: load
  12: 60,  // tier: demucs (standard) or energy (quick)
  13: 10,  // tier: per-stem / patterns
  14: 3,   // tier: transitions
  15: 1,   // tier: assembly
};

const DEFAULT_STAGE_DURATION = 5;

function getStageDurations(needsBase: boolean): Record<number, number> {
  return needsBase ? BASE_PLUS_TIER_DURATIONS : TIER_STAGE_DURATIONS;
}

/** Cumulative duration up to (but not including) a given step. */
function durationWeightedPercent(
  currentStep: number,
  totalSteps: number,
  needsBase: boolean = false,
): number {
  const durations = getStageDurations(needsBase);
  let totalDuration = 0;
  let completedDuration = 0;
  for (let s = 1; s <= totalSteps; s++) {
    const d = durations[s] ?? DEFAULT_STAGE_DURATION;
    totalDuration += d;
    if (s < currentStep) completedDuration += d;
  }
  if (totalDuration === 0) return 0;
  return Math.round((completedDuration / totalDuration) * 100);
}

function estimateRemaining(
  currentStep: number,
  totalSteps: number,
  needsBase: boolean = false,
): string | null {
  if (currentStep <= 0 || currentStep > totalSteps) return null;
  const durations = getStageDurations(needsBase);
  let remaining = 0;
  const currentDuration = durations[currentStep] ?? DEFAULT_STAGE_DURATION;
  remaining += currentDuration * 0.5;
  for (let s = currentStep + 1; s <= totalSteps; s++) {
    remaining += durations[s] ?? DEFAULT_STAGE_DURATION;
  }
  if (remaining < 5) return "< 5s";
  if (remaining < 60) return `~${Math.round(remaining)}s`;
  const mins = Math.round(remaining / 60);
  return `~${mins}m`;
}

function phaseLabel(job: StrataJobStatus): string {
  if (job.needs_base && job.phase === "base") return "Analyzing audio...";
  return `Running ${TIER_LABELS[job.tier] ?? job.tier}...`;
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
  const completeFired = useRef(false);

  const isDone = job?.status === "complete" || job?.status === "failed";

  useEffect(() => {
    if (isDone && onComplete && !completeFired.current) {
      completeFired.current = true;
      onComplete();
    }
  }, [isDone, onComplete]);

  if (!job) {
    return (
      <div className="h-48 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
        <div className="w-4 h-4 rounded-full bg-blue-500 animate-pulse" />
        <span className="text-sm text-gray-300">Starting {TIER_LABELS[tier]} analysis...</span>
      </div>
    );
  }

  const pct = job.total_steps > 0 ? durationWeightedPercent(job.current_step, job.total_steps, job.needs_base) : 0;

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
    return null;
  }

  const eta = estimateRemaining(job.current_step, job.total_steps, job.needs_base);

  return (
    <div className="h-48 flex flex-col items-center justify-center bg-gray-950 rounded border border-gray-800 gap-3">
      <span className="text-sm text-gray-300">
        {phaseLabel(job)}
      </span>

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

function JobStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "complete":
      return <span className="text-green-400">&#x2713;</span>;
    case "failed":
      return <span className="text-red-400">&#x2717;</span>;
    case "running":
      return <span className="text-blue-400 animate-pulse">&#x25CF;</span>;
    default:
      return <span className="text-gray-600">&#x25CB;</span>;
  }
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
  const [expanded, setExpanded] = useState(false);

  const isFinished = batch?.status === "complete" || batch?.status === "failed";
  const isRunning = batch?.status === "running" || batch?.status === "pending";
  const failedCount = batch?.failed ?? 0;
  const completedCount = batch?.completed ?? 0;
  const processed = completedCount + failedCount;
  const pct = (batch?.total ?? 0) > 0 ? Math.round((processed / batch!.total) * 100) : 0;
  const isCancelled = isFinished && (batch?.jobs.some((j) => j.error === "Cancelled by user") ?? false);
  const isPureSuccess = isFinished && failedCount === 0;
  const hasFailures = isFinished && failedCount > 0;

  const activeJob = batch?.jobs.find((j) => j.status === "running");
  const needsBaseCount = batch?.jobs.filter((j) => j.needs_base).length ?? 0;

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
                : activeJob
                  ? <span>{phaseLabel(activeJob)}{activeJob.title ? ` — ${activeJob.title}` : ""}</span>
                  : "Analyzing..."}
        </span>
        <div className="flex items-center gap-3">
          <span>{processed}/{batch.total} ({pct}%)</span>
          {needsBaseCount > 0 && isRunning && (
            <span className="text-gray-600">{needsBaseCount} need audio</span>
          )}
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
              style={{ width: `${activeJob.total_steps > 0 ? durationWeightedPercent(activeJob.current_step, activeJob.total_steps, activeJob.needs_base) : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Per-track list (collapsible) */}
      {batch.jobs.length > 1 && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
          >
            {expanded ? "\u25BC" : "\u25B6"} {batch.jobs.length} tracks
          </button>
          {expanded && (
            <div className="mt-1 max-h-40 overflow-y-auto space-y-0.5">
              {batch.jobs.map((job) => (
                <div key={job.job_id} className="flex items-center gap-2 text-xs text-gray-500 py-0.5">
                  <JobStatusIcon status={job.status} />
                  <span className="truncate flex-1" title={job.title || job.fingerprint.slice(0, 16)}>
                    {job.title || job.fingerprint.slice(0, 16)}
                  </span>
                  {job.status === "running" && (
                    <span className="text-gray-600 flex-shrink-0">
                      {job.needs_base && job.phase === "base" ? "audio" : job.tier} — {job.current_step_name}
                    </span>
                  )}
                  {job.status === "failed" && job.error && (
                    <span className="text-red-400/70 truncate flex-shrink-0 max-w-[200px]" title={job.error}>
                      {job.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Error summary — group failures by reason */}
      {hasFailures && !expanded && (() => {
        const errorGroups: Record<string, number> = {};
        for (const job of batch.jobs) {
          if (job.status === "failed" && job.error) {
            const key = job.error.replace(/[a-f0-9]{12,}/, "\u2026");
            errorGroups[key] = (errorGroups[key] ?? 0) + 1;
          }
        }
        return (
          <div className="flex flex-col gap-1 text-xs text-gray-500">
            {Object.entries(errorGroups).map(([reason, count]) => (
              <div key={reason} className="flex items-start gap-1.5">
                <span className="text-red-400/70 flex-shrink-0">&times;{count}</span>
                <span className="truncate" title={reason}>{reason}</span>
              </div>
            ))}
          </div>
        );
      })()}
    </div>
  );
}
