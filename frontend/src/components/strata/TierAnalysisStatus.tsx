/** Progress indicators for strata analysis jobs (single-track and batch). */

import { useStrataJobStatus, useStrataBatchStatus } from "../../api/strata";
import type { StrataTier } from "../../types/strata";

const TIER_LABELS: Record<StrataTier, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
};

/** Estimated seconds remaining per stage for standard tier.
 *  Stage 1 (load): ~1s, Stage 2 (demucs): ~60s, Stage 3 (per-stem): ~10s,
 *  Stage 4 (transitions): ~3s, Stage 5 (assembly): ~1s.
 */
const STAGE_DURATIONS: Record<number, number> = {
  1: 1,
  2: 60,
  3: 10,
  4: 3,
  5: 1,
};

function estimateRemaining(currentStep: number, totalSteps: number): string | null {
  if (currentStep <= 0 || currentStep > totalSteps) return null;
  let remaining = 0;
  // Sum durations of remaining stages (current stage partially done, estimate half)
  const currentDuration = STAGE_DURATIONS[currentStep] ?? 5;
  remaining += currentDuration * 0.5; // assume halfway through current
  for (let s = currentStep + 1; s <= totalSteps; s++) {
    remaining += STAGE_DURATIONS[s] ?? 5;
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
  const pct = job.total_steps > 0 ? Math.round((job.current_step / job.total_steps) * 100) : 0;

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
}: {
  batchId: string;
  onComplete?: () => void;
}) {
  const { data: batch } = useStrataBatchStatus(batchId);

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

  const isDone = batch.status === "complete" || batch.status === "failed";
  const pct = batch.total > 0 ? Math.round((batch.completed / batch.total) * 100) : 0;

  if (isDone && onComplete) {
    setTimeout(onComplete, 0);
  }

  return (
    <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-300">
          {isDone
            ? `Batch complete \u2014 ${batch.completed} succeeded${batch.failed > 0 ? `, ${batch.failed} failed` : ""}`
            : `Analyzing: ${batch.completed + batch.failed}/${batch.total} tracks`}
        </span>
        {!isDone && <span className="text-xs text-gray-500">{pct}%</span>}
      </div>
      <div className="w-full bg-gray-800 rounded-full h-2 mb-2">
        <div
          className={`h-2 rounded-full transition-all ${
            batch.failed > 0 ? "bg-amber-500" : "bg-blue-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {/* Per-job status list */}
      <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
        {batch.jobs.map((job) => (
          <div key={job.job_id} className="flex items-center gap-2 text-xs">
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${
                job.status === "complete"
                  ? "bg-green-500"
                  : job.status === "failed"
                    ? "bg-red-500"
                    : job.status === "running"
                      ? "bg-blue-500 animate-pulse"
                      : "bg-gray-600"
              }`}
            />
            <span className="text-gray-400 font-mono truncate">
              {job.fingerprint.slice(0, 12)}
            </span>
            <span className="text-gray-500">{job.tier}</span>
            <span className="text-gray-500 ml-auto">
              {job.status === "running" && job.current_step_name
                ? job.current_step_name
                : job.status === "failed"
                  ? job.error?.slice(0, 40) ?? "failed"
                  : job.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
