import { useState } from "react";
import { useLibraryDetect, useLibraryScan, useLibraryScanStatus } from "../../api/ingestion";
import { useBridgeStore } from "../../stores/bridgeStore";
import type { LibraryMatchedTrack, LibraryUnmatchedTrack, LibraryScanResult } from "../../types/ingestion";

function MatchedTable({ tracks }: { tracks: LibraryMatchedTrack[] }) {
  if (tracks.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Matched ({tracks.length})
      </h4>
      <div className="overflow-auto rounded border border-gray-800" style={{ maxHeight: 300 }}>
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-gray-800 bg-gray-900">
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Title
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Fingerprint
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400 w-24">
                Method
              </th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((track) => (
              <tr
                key={track.file_path}
                className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
              >
                <td className="px-3 py-2 text-gray-300 truncate max-w-[300px]" title={track.file_path}>
                  {track.title}
                </td>
                <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                  {track.fingerprint}
                </td>
                <td className="px-3 py-2 text-gray-500 text-xs">
                  {track.match_method}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UnmatchedTable({ tracks }: { tracks: LibraryUnmatchedTrack[] }) {
  if (tracks.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Unmatched ({tracks.length})
      </h4>
      <div className="overflow-auto rounded border border-gray-800" style={{ maxHeight: 300 }}>
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-gray-800 bg-gray-900">
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Title
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                File
              </th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((track) => {
              const stem = track.file_path.split("/").pop() ?? track.file_path;
              return (
                <tr
                  key={track.file_path}
                  className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                >
                  <td className="px-3 py-2 text-gray-300 truncate max-w-[300px]">
                    {track.title}
                  </td>
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs truncate max-w-[300px]" title={track.file_path}>
                    {stem}
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

function ScanSummary({ result }: { result: LibraryScanResult }) {
  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-400">
        {result.total_tracks} tracks found, {result.matched} matched, {result.unmatched} unmatched
        {result.already_linked > 0 && (
          <span className="text-gray-600"> ({result.already_linked} already linked)</span>
        )}
      </div>
      <MatchedTable tracks={result.matched_tracks} />
      <UnmatchedTable tracks={result.unmatched_tracks} />
    </div>
  );
}

export function LibraryTab() {
  const isStartingUp = useBridgeStore((s) => s.isStartingUp);
  const [forceRescan, setForceRescan] = useState(false);

  const { data: detected, isLoading: detecting, error: detectError } = useLibraryDetect(!isStartingUp);
  const { data: scanStatus } = useLibraryScanStatus(!isStartingUp && !!detected);
  const scanMutation = useLibraryScan();

  const handleScan = () => {
    scanMutation.mutate({ path: detected?.path ?? null, force_rescan: forceRescan });
  };

  if (isStartingUp) {
    return <div className="text-gray-500 text-sm animate-pulse">Connecting...</div>;
  }

  if (detecting) {
    return <div className="text-gray-500 text-sm">Detecting rekordbox library...</div>;
  }

  if (detectError || !detected) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900/50 p-4">
        <p className="text-gray-400 text-sm">No rekordbox library detected.</p>
        <p className="text-gray-600 text-xs mt-1">
          Expected at ~/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/
        </p>
      </div>
    );
  }

  // Resolve the best scan result: mutation result (just completed) or cached status
  const scanResult: LibraryScanResult | null =
    scanMutation.data ??
    (scanStatus && scanStatus.status === "complete" ? scanStatus : null);

  return (
    <div className="space-y-4">
      <div className="rounded border border-gray-800 bg-gray-900/50 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-300">
              Library found: <span className="text-gray-400 font-mono text-xs">{detected.path}</span>
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {detected.dat_count} DAT files available
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={forceRescan}
                onChange={(e) => setForceRescan(e.target.checked)}
                className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
              />
              Force Rescan
            </label>
            <button
              onClick={handleScan}
              disabled={scanMutation.isPending}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors"
            >
              {scanMutation.isPending ? "Scanning..." : "Scan Library"}
            </button>
          </div>
        </div>

        {scanMutation.isPending && (
          <div className="mt-3">
            <div className="w-full bg-gray-800 rounded-full h-1.5">
              <div className="h-1.5 rounded-full bg-blue-500 animate-pulse w-1/2" />
            </div>
          </div>
        )}

        {scanMutation.isError && (
          <p className="text-red-400 text-xs mt-2">
            Scan failed: {scanMutation.error.message}
          </p>
        )}
      </div>

      {scanResult && <ScanSummary result={scanResult} />}
    </div>
  );
}
