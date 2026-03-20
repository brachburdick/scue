import { useState } from "react";
import { TrackPicker } from "../components/analysis/TrackPicker";
import { AnalysisViewer } from "../components/analysis/AnalysisViewer";

export function AnalysisViewerPage() {
  const [fingerprint, setFingerprint] = useState<string | null>(null);

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Analysis Viewer</h1>
      <TrackPicker selectedFingerprint={fingerprint} onSelect={setFingerprint} />
      {fingerprint ? (
        <AnalysisViewer fingerprint={fingerprint} />
      ) : (
        <div className="mt-4 h-40 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-500 text-sm">Select a track above to view analysis</p>
        </div>
      )}
    </div>
  );
}
