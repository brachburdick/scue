import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAnalyzeStore } from "../../stores/analyzeStore";
import {
  scanDirectory,
  startBatchAnalysis,
  useJobStatus,
  getLastScanPath,
} from "../../api/analyze";
import { FolderBrowser } from "../shared/FolderBrowser";

export function AnalyzePanel() {
  const store = useAnalyzeStore();
  const { data: job, error: jobError } = useJobStatus(store.jobId);
  const queryClient = useQueryClient();
  const [browserOpen, setBrowserOpen] = useState(false);
  const [showErrors, setShowErrors] = useState(false);

  // Pre-fill scan path from last used path on mount
  useEffect(() => {
    if (!store.scanPath) {
      getLastScanPath()
        .then((resp) => {
          if (resp.path) store.setScanPath(resp.path);
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh track list when job completes
  useEffect(() => {
    if (!job) return;
    const isDone = job.status === "complete" || job.status === "complete_with_errors";
    if (isDone) {
      queryClient.invalidateQueries({ queryKey: ["tracks"] });
      queryClient.invalidateQueries({ queryKey: ["folder-contents"] });
      // Only auto-dismiss on clean complete (no errors)
      if (job.status === "complete" && job.failed === 0) {
        const timer = setTimeout(() => store.reset(), 2000);
        return () => clearTimeout(timer);
      }
    }
  }, [job?.status, job?.failed, queryClient, store]);

  const handleScan = async () => {
    if (!store.scanPath.trim()) return;
    store.setIsScanning(true);
    store.setScanError(null);
    try {
      const result = await scanDirectory(store.scanPath.trim());
      store.setScanResult(result);
    } catch (e) {
      store.setScanError(e instanceof Error ? e.message : String(e));
    } finally {
      store.setIsScanning(false);
    }
  };

  const handleAnalyze = async () => {
    if (!store.scanResult) return;
    const paths = store.scanResult.new_files.map((f) => f.path);
    try {
      const { job_id } = await startBatchAnalysis(
        paths,
        false,
        store.scanResult.scan_root,
        store.destinationFolder,
      );
      store.setJobId(job_id);
    } catch (e) {
      store.setScanError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleReset = () => {
    store.reset();
    setShowErrors(false);
  };

  // Phase 3: Job running or complete (or errored)
  if (store.jobId && (job || jobError)) {
    // Handle polling errors (e.g. server restart, lost job)
    if (jobError && !job) {
      return (
        <div className="mb-6 rounded border border-red-800 bg-red-900/20 p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-red-400">
              Analysis job lost — the server may have restarted.
            </span>
            <button
              onClick={handleReset}
              className="text-xs text-gray-400 hover:text-gray-200"
            >
              Dismiss
            </button>
          </div>
        </div>
      );
    }

    if (!job) return null;

    const pct = job.total > 0 ? Math.round((job.completed / job.total) * 100) : 0;
    const isDone =
      job.status === "complete" ||
      job.status === "complete_with_errors" ||
      job.status === "failed";

    const hasErrors = job.failed > 0;
    const failedFiles = job.results?.filter((r) => r.status === "error") ?? [];

    // Per-step progress within the current file
    const stepPct = job.total_steps > 0
      ? Math.round((job.current_step / job.total_steps) * 100)
      : 0;

    return (
      <div
        className={`mb-6 rounded border p-4 ${
          hasErrors && isDone
            ? "border-amber-800 bg-amber-900/10"
            : "border-gray-800 bg-gray-900/50"
        }`}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">
            {isDone
              ? hasErrors
                ? `Done — ${job.completed} succeeded, ${job.failed} failed`
                : `Done — ${job.completed} tracks analyzed`
              : `Analyzing: ${job.current_file ?? "..."}`}
          </span>
          {isDone && (
            <button
              onClick={handleReset}
              className="text-xs text-gray-400 hover:text-gray-200"
            >
              Dismiss
            </button>
          )}
        </div>

        {/* Per-file progress bar */}
        <div className="w-full bg-gray-800 rounded-full h-2 mb-1">
          <div
            className={`h-2 rounded-full transition-all ${
              hasErrors ? "bg-amber-500" : "bg-blue-500"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {job.completed + job.failed}/{job.total} ({pct}%)
          </span>

          {/* Per-step indicator for current file */}
          {!isDone && job.current_step > 0 && (
            <span className="text-xs text-gray-500">
              Step {job.current_step}/{job.total_steps}: {job.current_step_name}
            </span>
          )}
        </div>

        {/* Per-step mini progress bar */}
        {!isDone && job.current_step > 0 && (
          <div className="w-full bg-gray-800 rounded-full h-1 mt-1.5">
            <div
              className="h-1 rounded-full bg-cyan-600 transition-all"
              style={{ width: `${stepPct}%` }}
            />
          </div>
        )}

        {/* Error details (expandable) */}
        {isDone && hasErrors && (
          <div className="mt-3">
            <button
              onClick={() => setShowErrors(!showErrors)}
              className="text-xs text-amber-400 hover:text-amber-300"
            >
              {showErrors ? "Hide" : "Show"} {failedFiles.length} error
              {failedFiles.length !== 1 ? "s" : ""}
            </button>
            {showErrors && (
              <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
                {failedFiles.map((f) => (
                  <div key={f.path} className="text-xs text-gray-400 font-mono">
                    <span className="text-red-400">{f.filename}</span>
                    {f.error && (
                      <span className="text-gray-500 ml-2">— {f.error}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Phase 2: Scan results
  if (store.scanResult) {
    const { total_files, already_analyzed, new_files } = store.scanResult;
    return (
      <div className="mb-6 rounded border border-gray-800 bg-gray-900/50 p-4">
        <p className="text-sm mb-3">
          Found <strong>{total_files}</strong> audio file{total_files !== 1 ? "s" : ""}.{" "}
          {already_analyzed > 0 && (
            <span className="text-gray-400">
              {already_analyzed} already analyzed.
            </span>
          )}
        </p>

        {/* Destination folder picker */}
        {new_files.length > 0 && (
          <div className="mb-3 flex items-center gap-2">
            <label className="text-xs text-gray-400 whitespace-nowrap">
              Destination folder:
            </label>
            <input
              type="text"
              placeholder="(root)"
              value={store.destinationFolder}
              onChange={(e) => store.setDestinationFolder(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500 w-60"
            />
          </div>
        )}

        {new_files.length > 0 ? (
          <button
            onClick={handleAnalyze}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded"
          >
            Analyze {new_files.length} New Track{new_files.length !== 1 ? "s" : ""}
          </button>
        ) : (
          <p className="text-gray-400 text-sm">All tracks already analyzed.</p>
        )}
        <button
          onClick={handleReset}
          className="ml-3 text-xs text-gray-400 hover:text-gray-200"
        >
          Change path
        </button>
      </div>
    );
  }

  // Phase 1: Path input
  return (
    <div className="mb-6">
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Directory or file path..."
          value={store.scanPath}
          onChange={(e) => store.setScanPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleScan()}
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-gray-500"
        />
        <button
          onClick={() => setBrowserOpen(true)}
          className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-sm rounded"
        >
          Browse
        </button>
        <button
          onClick={handleScan}
          disabled={store.isScanning || !store.scanPath.trim()}
          className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-sm rounded"
        >
          {store.isScanning ? "Scanning..." : "Scan"}
        </button>
      </div>
      {store.scanError && (
        <p className="text-red-400 text-xs mt-1">{store.scanError}</p>
      )}
      <FolderBrowser
        open={browserOpen}
        onSelect={(path) => {
          store.setScanPath(path);
          setBrowserOpen(false);
        }}
        onClose={() => setBrowserOpen(false)}
      />
    </div>
  );
}
