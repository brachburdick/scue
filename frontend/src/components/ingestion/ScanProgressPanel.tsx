import type { HardwareScanStatus } from "../../types/ingestion";

interface ScanProgressPanelProps {
  progress: HardwareScanStatus;
  onStop: () => void;
  onDismiss: () => void;
  isStopping: boolean;
}

export function ScanProgressPanel({ progress, onStop, onDismiss, isStopping }: ScanProgressPanelProps) {
  const pct = progress.total > 0 ? (progress.scanned / progress.total) * 100 : 0;
  const isTerminal = progress.status === "completed" || progress.status === "failed";

  return (
    <div className="rounded border border-gray-800 bg-gray-900/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-gray-300">
          {isTerminal ? "Scan Complete" : "Scan Progress"}
        </h4>
        {isTerminal ? (
          <button
            onClick={onDismiss}
            className="text-gray-500 hover:text-gray-300 transition-colors p-1"
            title="Dismiss"
          >
            ✕
          </button>
        ) : (
          <button
            onClick={onStop}
            disabled={isStopping || progress.status !== "scanning"}
            className="px-3 py-1 text-xs font-medium rounded bg-red-600/80 hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors"
          >
            {isStopping ? "Stopping..." : "Stop Scan"}
          </button>
        )}
      </div>

      <div className="w-full bg-gray-800 rounded-full h-2">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>
          {progress.scanned}/{progress.total} tracks scanned
          {progress.errors > 0 && (
            <span className="text-red-400 ml-1">({progress.errors} errors)</span>
          )}
          {progress.skipped > 0 && (
            <span className="text-yellow-400 ml-1">({progress.skipped} skipped)</span>
          )}
        </span>
        <span>{Math.round(pct)}%</span>
      </div>

      {Object.keys(progress.deck_progress).length > 0 && (
        <div className="space-y-1">
          {Object.entries(progress.deck_progress).map(([deck, dp]) => (
            <div key={deck} className="flex items-center gap-2 text-xs">
              <span className="text-gray-500 w-14 shrink-0">Deck {deck}:</span>
              <span className={dp.status === "scanning" ? "text-blue-400" : "text-gray-500"}>
                {dp.status === "scanning" && dp.current_track
                  ? `scanning "${dp.current_track}"`
                  : dp.status}
              </span>
              {dp.total > 0 && (
                <span className="text-gray-600 ml-auto">
                  {dp.scanned}/{dp.total}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {progress.status === "completed" && (
        <p className="text-green-400 text-xs">Scan complete.</p>
      )}
      {progress.status === "failed" && (
        <p className="text-red-400 text-xs">Scan failed.</p>
      )}
    </div>
  );
}
